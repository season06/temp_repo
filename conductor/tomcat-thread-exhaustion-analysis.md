# Conductor Tomcat Busy Thread 耗盡問題分析

## 環境

| 項目 | 值 | 對應模組 / 實作 |
|---|---|---|
| DB | MariaDB | `conductor.db.type=mysql` → `mysql-persistence` / `MySQLExecutionDAO` |
| Queue | Redis (standalone) | `conductor.queue.type=redis_standalone` → `redis-persistence` / `RedisStandaloneConfiguration` |
| Index | Elasticsearch 7 | `conductor.elasticsearch.version` 預設 `7` → `es7-persistence` / `ElasticSearchRestDAOV7` |
| 設定 | 以預設值為主 | |

版本基準：本 repo `v3.22.0-alpha1`（commit `7f6653a7f`）。所有行號對應此版本。

本文與 `archive-listener-analysis.md` 無直接關聯，是獨立的系統面問題。

---

## 現象

Conductor server 的 Tomcat busy thread 成長到 100%（預設上限 200），且**負載退去後沒有正常釋放**。

「不會自我恢復」這個特徵很重要——它把候選原因分成兩類：

- **會恢復的**：下游慢，但有超時，最終會拋例外放掉執行緒
- **不會恢復的**：某處是無限期阻塞，一旦進去就出不來

後者才符合觀察到的症狀。

---

## 0. 架構前提：編排引擎跑在 HTTP 請求執行緒上

這是理解整個問題的關鍵。Conductor 的 REST 層**不是**「接請求、丟給背景執行緒」的薄層。

### 對應程式碼邏輯

```java
// core/.../core/execution/WorkflowExecutorOps.java:884-886   （updateTask 的最後）
if (!isLazyEvaluateWorkflow(workflowInstance.getWorkflowDefinition(), task)) {
    decide(workflowId);
}
```

而 `isLazyEvaluateWorkflow`（`WorkflowExecutorOps.java:961-986`）的最後一行：

```java
// :984-985
return workflowTasks.stream().noneMatch(t -> t.getTaskReferenceName().equals(taskRefName))
        && task.getStatus().isSuccessful();
```

一般 task 必然存在於 workflow def 中 → `noneMatch` 為 `false` → 整個方法回傳 `false` → **`decide()` 同步執行**。

lazy evaluation 只在兩種情況生效：
1. task 屬於某個 FORK 分支，且有 JOIN 在等它（`:979-982`）
2. task 根本不在 def 裡（`:984`）

**結論：絕大多數 worker 的 task update 都會在 Tomcat 執行緒上同步跑完一次完整的 `decide()`。**

### 一次 `POST /api/tasks` 在同一條執行緒上做的事

| # | 動作 | 出處 | 打到哪 |
|---|---|---|---|
| 1 | `getWorkflowModel` + `getTaskModel` | `WorkflowExecutorOps.java:719` 起 | MariaDB |
| 2 | external payload 下載（若有設定） | `ExecutionDAOFacade` | S3 |
| 3 | `executionDAOFacade.updateTask` | `ExecutionDAOFacade.java:516-517` | MariaDB **+ 同步 ES index** |
| 4 | `addTaskExecLog` | `ExecutionDAOFacade.java:644` | ES（`asyncIndexingEnabled=false` 時同步） |
| 5 | `queueDAO.remove` / `postpone` | `WorkflowExecutorOps.java:744` 起 | Redis |
| 6 | **`decide()`** | `WorkflowExecutorOps.java:885` → `:1021-1041` | MariaDB + Redis + ES |

第 6 步的 `decide()` 內容包含：取執行鎖、**讀取整個 workflow 含所有 task**、評估狀態、排程新 task（DB 寫入 + Redis push）、inline 執行 `isAsync() == false` 的 system task（SWITCH / JOIN / INLINE / JSON_JQ_TRANSFORM 等）。

第 3 步的同步 ES 索引：

```java
// ExecutionDAOFacade.java:516-517
if (!properties.isAsyncIndexingEnabled() && properties.isTaskIndexingEnabled()) {
    indexDAO.indexTask(new TaskSummary(taskModel.toTask()));
}
```

兩者預設都是會走進去的（`ConductorProperties.java:94` `taskIndexingEnabled=true`、`:100` `asyncIndexingEnabled=false`）。

---

## 1. 資源池配比：200 : 10 : 10 : 10

| 池 | 大小 | 來源 |
|---|---|---|
| Tomcat worker thread | **200** | Spring Boot 預設 |
| HikariCP（MariaDB） | **10** | Spring Boot 預設（`server/src/main/resources/application.properties:162` 的設定是註解掉的） |
| Jedis（Redis） | **10** | `redis-persistence/.../config/RedisProperties.java:72` `maxConnectionsPerHost` |
| ES RestClient | **10 / route，30 total** | RestClient 預設；`ElasticSearchV7Configuration.java` 未覆寫 |

200 條執行緒前面擋著三個大小為 10 的池。**任何一個下游變慢，Tomcat 執行緒堆積是必然結果，而不是異常。**

因此：**Tomcat busy thread 100% 在 Conductor 幾乎不是 thread leak，而是執行緒全部 park 在下游資源池上。** 它是最末端的症狀指標，看到它滿的時候真正的瓶頸已經飽和很久了。

---

## 候選原因 A（頭號嫌疑）：Jedis 連線池耗盡時無限阻塞

**這是唯一一個「不會自我恢復」的候選，直接對應「沒有正常被釋放」。**

### 對應程式碼邏輯

```java
// redis-persistence/.../config/RedisStandaloneConfiguration.java:43-45
JedisPoolConfig config = new JedisPoolConfig();
config.setMinIdle(2);
config.setMaxTotal(properties.getMaxConnectionsPerHost());   // 預設 10
// ← 從頭到尾沒有呼叫 setMaxWaitMillis
```

看起來就是為這個情境準備的參數，實際上沒有被套用到 standalone 路徑：

```
$ grep -rn "getMaxTimeoutWhenExhausted" --include=*.java .
redis-persistence/.../config/DynomiteClusterConfiguration.java:44
```

| 屬性 / 位置 | 值 | 說明 |
|---|---|---|
| `RedisProperties.java:72` `maxConnectionsPerHost` | `10` | Jedis pool `maxTotal` |
| `RedisProperties.java:78` `maxTimeoutWhenExhausted` | `800ms` | **只有 `DynomiteClusterConfiguration.java:44` 使用** |
| `RedisStandaloneConfiguration.java:43-45` | — | 只設 `minIdle` / `maxTotal` |
| `RedisClusterConfiguration.java:51` | — | 同樣只設 `maxTotal` |
| `RedisSentinelConfiguration.java:50` | — | 同樣只設 `maxTotal` |

Jedis 版本 `3.3.0`（`dependencies.gradle:41`）。其 `JedisPoolConfig` 建構子只覆寫 `testWhileIdle` / `minEvictableIdleTimeMillis` / `timeBetweenEvictionRunsMillis` / `numTestsPerEvictionRun`，**沒有覆寫 `maxWait`**。繼承自 commons-pool2 的 `BaseObjectPoolConfig` 預設為：

- `blockWhenExhausted = true`
- `maxWaitMillis = -1`（無限等待）

### 結論

**一旦 10 條 Redis 連線全數借出，第 11 條之後的執行緒會在 `GenericObjectPool.borrowObject` 上無限期阻塞。**

需要區分清楚的一點：**單一 Redis 操作是有超時的**（`Protocol.DEFAULT_TIMEOUT` = 2000ms，見 `RedisStandaloneConfiguration.java:51-73` 的 `getJedisPool`）。沒有超時的是**「借連線」這個動作本身**。

所以只要有任何一個持有者卡住（網路抖動、Redis 主從切換、單一慢指令、或單純併發超過 10），後續請求就會雪崩式堆積，且**負載退去後不會自行恢復**。

### 可能解法

**(1) 短期：把池開大到與併發量匹配**

```properties
conductor.redis.maxConnectionsPerHost=100
conductor.redis.maxIdleConnections=50
```

這只是提高門檻，**無限阻塞的行為仍然存在**。

**(2) 根本解：讓 standalone 路徑與 Dynomite 路徑行為一致**

```java
// redis-persistence/.../config/RedisStandaloneConfiguration.java:43-45
JedisPoolConfig config = new JedisPoolConfig();
config.setMinIdle(2);
config.setMaxTotal(properties.getMaxConnectionsPerHost());
config.setMaxWaitMillis(properties.getMaxTimeoutWhenExhausted().toMillis());  // ← 新增
```

池滿時快速失敗 → worker 收到 5xx 並重試 → 執行緒立即歸還。

**把「無限阻塞」換成「快速失敗」，是這裡唯一能讓系統自我恢復的改動。**
（`RedisClusterConfiguration.java:51` 與 `RedisSentinelConfiguration.java:50` 有同樣問題，若有使用需一併處理。）

---

## 候選原因 B：ES 全域索引鎖

### 對應程式碼邏輯

```java
// es7-persistence/.../index/ElasticSearchRestDAOV7.java:1250-1257
bulkRequests.get(docType).getBulkRequest().add(request);
if (bulkRequests.get(docType).getBulkRequest().numberOfActions() >= this.indexBatchSize) {
    indexBulkRequest(docType);
}

// :1261
private synchronized void indexBulkRequest(String docType) { ... }   // 內含阻塞式 ES HTTP 呼叫
```

`indexBatchSize` 預設為 **1**（`es7-persistence/.../config/ElasticSearchProperties.java:42`），代表**每一次 `indexTask` 都會立刻觸發 flush**——用了 bulk API 的開銷卻沒有 bulk 的效益。

而 `indexBulkRequest` 是 `private synchronized`，**整個 DAO 實例層級的鎖，且該鎖是跨越那次阻塞式 ES HTTP 呼叫持有的**。

### 影響

所有執行緒的 task 索引在此**全域序列化**，與執行緒數無關。若 ES 的 p99 為 20ms，理論上限即為 50 次索引/秒。超過的部分全部堆積在這個 monitor 上。

配合前述「`updateTask` 走在 Tomcat 執行緒上」（`ExecutionDAOFacade.java:516-517`），這代表 **worker 的 task update 直接撞在這個全域鎖上**。

### 可能解法

```properties
conductor.elasticsearch.indexBatchSize=50
```

有排程 flusher 兜底（`ElasticSearchRestDAOV7.java:51`、`:196`，每 30 秒一次），延遲上限可控。

或直接關閉 task 索引（若不需要 task 層級搜尋）：

```properties
conductor.app.taskIndexingEnabled=false
```

---

## 候選原因 C：ES 沒有有效的超時設定

### 對應程式碼邏輯

```java
// es7-persistence/.../config/ElasticSearchV7Configuration.java:58-60
builder.setRequestConfigCallback(
        requestConfigBuilder -> requestConfigBuilder.setConnectionRequestTimeout(...));
```

只設定了 `connectionRequestTimeout`，而該屬性預設為 `-1`（`ElasticSearchProperties.java:67` `restClientConnectionRequestTimeout`），等於這段設定實際上沒有生效。

socket timeout 未覆寫 → 走 RestClient 預設 **30 秒**。

### 影響

ES 一慢，每個涉及索引或搜尋的請求最多佔用執行緒 30 秒。會恢復，但很慢。搜尋類端點（`GET /api/workflow/search`、UI 輪詢）尤其明顯。

### 可能解法

明確設定 socket timeout。這是防止「索引/搜尋故障升級成 API 故障」的斷路器。

---

## 候選原因 D：HikariCP 連線池耗盡

| 項目 | 值 |
|---|---|
| pool size | 10（Spring 預設，`application.properties:162` 為註解） |
| `connectionTimeout` | 30s（Spring 預設） |

DB 一慢，執行緒堆積在 `HikariPool.getConnection`。30 秒後拋例外，**會恢復**。

### 可能解法

```properties
spring.datasource.hikari.maximum-pool-size=50
```

並監控 `hikaricp_connections_pending`。

---

## 候選原因 E：long-poll 的正常佔用（容量問題，非 bug）

### 對應程式碼邏輯

```java
// core/.../service/ExecutionService.java:60
private static final int MAX_POLL_TIMEOUT_MS = 5000;

// :102
if (timeoutInMilliSecond > MAX_POLL_TIMEOUT_MS) {
    throw new IllegalArgumentException("Long Poll Timeout value cannot be more than 5 seconds");
}

// :111
taskIds = queueDAO.pop(queueName, count, timeoutInMilliSecond);
```

`GET /api/tasks/poll/batch/{tasktype}` 的 `timeout` 參數預設 100ms（`rest/.../controllers/TaskResource.java:80`），上限 5 秒，**期間阻塞請求執行緒**。

### 影響

穩態下被 long-poll 佔用的執行緒數 ≈ `worker 數 × 每個 worker 的 poll 併發數`。如果這個數字接近 200，就沒有餘裕處理 `updateTask`。

這不是 bug，是**必須納入容量規劃的固定成本**。

### 可能解法

- 調高 `server.tomcat.threads.max`（400–500）
- 或縮短 worker 的 poll timeout / 降低 poll 併發

---

## 候選原因 F：分散式執行鎖爭用

### 對應程式碼邏輯

| 位置 | 呼叫 | 等待上限 |
|---|---|---|
| `WorkflowExecutorOps.java:1024`（`decide`） | `acquireLock(workflowId)` | `lockTimeToTry` = **500ms**，失敗直接 return |
| `WorkflowExecutorOps.java:591`（`terminateWorkflow`） | `acquireLock(id, 60000)` | **60 秒** |
| `WorkflowExecutorOps.java:1249`（`pauseWorkflow`） | `acquireLock(id, 60000)` | **60 秒** |
| `WorkflowExecutorOps.java:1901`（`createAndEvaluate`） | `acquireLock(id)` | 500ms，失敗拋 `TransientException` |

相關預設值（`core/.../config/ConductorProperties.java`）：

| 屬性 | 預設 | 行號 |
|---|---|---|
| `workflowExecutionLockEnabled` | `false` | `:70` |
| `lockLeaseTime` | `60000ms` | `:73` |
| `lockTimeToTry` | `500ms` | `:78` |

### 影響

**預設是關閉的**（搭配 `noop_lock`）。若曾為了正確性開啟，則 terminate / pause 類請求可阻塞達 60 秒。

### 可能解法

確認 `conductor.app.workflow-execution-lock-enabled` 是否被誤開。若確實需要，注意 `:591` 與 `:1249` 的 60 秒硬編碼值。

---

## 候選原因 G：`decide()` 本身慢

`decide()` 需要讀取「整個 workflow + 所有 task」（`WorkflowExecutorOps.java:1029`），並 inline 執行所有同步 system task。

大型 workflow（數百個 task）、大 payload 的 `JSON_JQ_TRANSFORM`、複雜 `INLINE` script，全部都在 Tomcat 執行緒上跑，**沒有時間上限**。

### 可能解法

拆小 workflow；把重運算移出 system task。

---

## 決定性證據：thread dump

**不要用調參數的方式逐一嘗試。** 在 busy thread 偏高的當下直接取樣：

```bash
jcmd <pid> Thread.print > /tmp/dump1.txt
sleep 5
jcmd <pid> Thread.print > /tmp/dump2.txt   # 兩份比對，確認是「卡住」而非「忙碌」

# 統計 http-nio 執行緒停在哪
grep -A3 '"http-nio' /tmp/dump1.txt | grep "at " | sort | uniq -c | sort -rn | head -20
```

### 判別對照表

| 停在這個 stack frame | 根因 | 對策 |
|---|---|---|
| `GenericObjectPool.borrowObject` + `redis.clients.jedis` | **候選 A**：Jedis 池耗盡無限阻塞 | 補 `setMaxWaitMillis` + 調大池 |
| `ElasticSearchRestDAOV7.indexBulkRequest`（狀態 `BLOCKED`） | **候選 B**：全域索引鎖 | 調大 `indexBatchSize` |
| `RestClient.performRequest` / socket read（`TIMED_WAITING`） | **候選 C**：ES 慢 | 設 socket timeout；查 ES |
| `HikariPool.getConnection` | **候選 D**：DB 池耗盡 | 調大 `maximum-pool-size` |
| `RedisDynoQueue.pop` / `ExecutionService.poll` | **候選 E**：long-poll 正常佔用 | 重算容量 |
| `ExecutionLockService.acquireLock` | **候選 F**：分散式鎖爭用 | 檢查是否誤開 |
| `DeciderService` / `evaluate` | **候選 G**：編排本身慢 | 拆小 workflow |

執行緒狀態 `BLOCKED`（等 monitor）／ `WAITING`（無限等待）／ `TIMED_WAITING`（有超時的等待）三者的分布，就能把範圍收斂到一兩個候選。

**特別注意**：若大量執行緒處於 `WAITING` 且 stack 含 `borrowObject`，即可直接確認候選 A。

---

## 附錄：優先處理順序

| # | 動作 | 理由 |
|---|---|---|
| 1 | **取 thread dump 定位** | 不要猜。5 分鐘可定案 |
| 2 | **`RedisStandaloneConfiguration` 補 `setMaxWaitMillis`** | 唯一能讓系統自我恢復的改動 |
| 3 | 調大三個池（Redis / Hikari / Tomcat） | 提高門檻，爭取時間 |
| 4 | 設定 ES socket timeout | 防止下游故障向上蔓延 |
| 5 | 調大 `conductor.elasticsearch.indexBatchSize` | 解除全域鎖的爭用 |
| 6 | 加上請求層級超時 | Tomcat 預設無請求超時 |
| 7 | 監控三個池的飽和度 | 見下 |

### 應監控的指標

現況下 Tomcat busy thread 是**唯一可見的指標**，但它是最末端的症狀。真正該監控的是三個池的飽和度——它們在壞掉之前會先漲：

| 指標 | 意義 |
|---|---|
| `hikaricp_connections_pending` | DB 池排隊中的執行緒數 |
| Jedis pool active / idle | Redis 池飽和度（**候選 A 的早期訊號**） |
| `tomcat_threads_busy` | 末端症狀，用於確認而非診斷 |
| ES p99 index / search latency | 候選 B、C 的上游訊號 |

---

## 附註：與 archive 的關係

本問題與 `archive-listener-analysis.md` 描述的歸檔問題**沒有直接因果關係**，但兩者共用同一組資源池。歸檔在高流量下會額外消耗 MariaDB 連線與 ES 連線（詳見該文件的「高流量負擔」討論），因此會**壓縮這裡的餘裕**，讓上述任一候選更早觸發。
