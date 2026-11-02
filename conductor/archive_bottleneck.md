# Archive 啟動後的系統瓶頸與可監控指標

> 問題：當 archive 啟動後，可能發生的系統瓶頸會出現在哪？原生的 conductor exporter 是否有指標可監控？
>
> 相關文件：`archive-listener-analysis.md`（歸檔本身的三個現象）、`tomcat-thread-exhaustion-analysis.md`（執行緒耗盡的候選原因 A–G）、`decider-sweeper-mechanism.md`（「與 archive listener 的交互」一節）。
>
> 版本基準：本 repo `v3.22.0-alpha1`（commit `7f6653a7f`）。所有行號對應此版本。

---

## Archival

**archival.ttlDuration**

- 宣告：ArchivingWorkflowListenerProperties.java:61，Duration.ZERO，@DurationUnit(SECONDS)
- 原意：歸檔後讓 workflow 在主存儲再活 TTL 秒才過期，而不是立刻刪 —— 走 ExecutionDAOFacade.removeWorkflowWithExpiry（:402）→ Redis EXPIRE（RedisExecutionDAO.java:450）。MySQL/MariaDB 根本沒實作，直接丟 UnsupportedOperationException（MySQLExecutionDAO.java:312）。
- 現狀：語意已死。ArchivingWithTTLWorkflowStatusListener.java:41 把它讀進 archiveTTLSeconds，但這個欄位全程沒有任何讀取點；constructor :56 直接 log "Workflow removal with TTL is no longer supported... workflows will be removed immediately"，而 onWorkflowCompleted（:89、:125）呼叫的是 removeWorkflow(id, true)，不是 removeWorkflowWithExpiry。該 TTL 方法在整個 repo 已無生產呼叫點。
- 它現在唯一的實際作用是 ArchivingWorkflowListenerConfiguration.java:31 的分支開關：

┌─────────────┬─────────┬────────────────────────────────────────┬────────────────────────────────────────┐
│ ttlDuration │  type   │            得到的 listener             │                歸檔行為                │
├─────────────┼─────────┼────────────────────────────────────────┼────────────────────────────────────────┤
│ 0（預設）   │ DEFAULT │ ArchivingWorkflowStatusListener        │ 同步、無延遲，跑在觸發它的那條執行緒上 │
├─────────────┼─────────┼────────────────────────────────────────┼────────────────────────────────────────┤
│ >0          │ DEFAULT │ ArchivingWithTTLWorkflowStatusListener │ TTL 被忽略，但啟用 delay queue         │
├─────────────┼─────────┼────────────────────────────────────────┼────────────────────────────────────────┤
│ 0           │ S3      │ ArchivingWorkflowToS3                  │ 先寫 S3，也有 delay queue              │
└─────────────┴─────────┴────────────────────────────────────────┴────────────────────────────────────────┘

**archival.delaySeconds**

- 讀取：ArchivingWorkflowListenerProperties.java:115-121，預設 60
- fallback 寫的是 conductor.app.asyncUpdateDelaySeconds —— 這個 key 不存在（ConductorProperties 的欄位是 asyncUpdateDelay，:142），而 Environment.getProperty 是字面查找、不走 relaxed
  binding。所以除非你刻意用那個拼法，實際預設恆為 60。
- >0 時把 removeWorkflow 包成 DelayArchiveWorkflow 丟進 ScheduledThreadPoolExecutor(delayQueueWorkerThreadCount) 延後執行（:84）；=0 則同步刪（:89）。
- 兩個效果，對你們重要的是第二個：
  a. 延後：避免 workflow 剛終結時 client 還在 getWorkflow / 最後一次 index update 還沒落地就被刪掉。
  b. 換執行緒：把 1+N 次 MariaDB transaction、1+N 次 ES 寫、N+1 次 Redis 從 Tomcat  這就是 tomcat-thread-exhaustion-analysis.md 那條路徑的直接解法（bulkhead）。
                                                                                                                                              議值

conductor.workflow-status-listener.type=archive                                                                                               僅為啟用 delay queue 路徑；TTL 語意已失效，設大值沒有任何作用
conductor.workflow-status-listener.archival.ttlDuration=1s
conductor.workflow-status-listener.archival.delaySeconds=60
conductor.workflow-status-listener.archival.delayQueueWorkerThreadCount=5
ttlDuration=1s —— 取最小非零值。它不代表「資料多留 1 秒」，純粹是開關。別設 3600s後看配置的人誤判資料還在。啟動時會出現那行誤導性的 no longer supportedwarning，屬預期。                                                                                                                           delaySeconds=60（保持預設）—— 下限別低於 conductor.app.asyncUpdateDelay（60s）： d，短命 workflow 的最後一次 index update 本身延後60s（ExecutionDAOFacade.java:297-306），歸檔若更早寫入 rawJSON 會被那次 update 蓋掉。上限也別拉大：delay queue 是無界 queue，@PreDestroy 只 awaitTermination(delaySeconds)（:66），重啟時排在後面的歸檔會被 shutdownNow 丟棄 ariaDB 不再被歸檔（不是資料遺失，是洩漏）。60s 下的 in-flight 量約為 60 × 歸檔速率。
- delayQueueWorkerThreadCount=5（保持預設，先別調高）—— 每條歸檔執行緒各自會佔一條 HikariCP 連線，而池只有 10。調到 10 等於讓歸檔有機會吃光整個 DB 池，瓶頸會從 Tomcat 轉嫁到所有 DB 操作。要提吞吐的順序是：先加大 Hikari，再調這個；ES 側的天花板是 RestClient 預設 archV7Configuration.java:53-79 沒有自訂）。

---

## A. 瓶頸在哪

先算一次歸檔的實際成本。`removeWorkflow(id, true)` 對一個有 **N 個 task** 的 workflow：

| 下游 | 次數 | 說明 |
|---|---|---|
| MariaDB | **1 + N 個 transaction** | 1 次讀（workflow + 全部 task）、1 個 transaction 刪 3 張表、每個 task 各自一個 transaction 刪 4 張表（`MySQLExecutionDAO.java:287-305`） |
| Elasticsearch | **1 + N 次寫入** | 1 次 `updateWorkflow` 寫整份 `rawJSON`、每個 task 1 次 `updateTask` |
| Redis | **N + 1 次** | 每個 task queue remove、最後 1 次 `_deciderQueue` remove |

而這些全部**同步跑在觸發它的那條執行緒上** —— worker 的 `POST /api/tasks` 走 Tomcat 執行緒，sweeper 走 sweeper 執行緒。

依「最先撞到」排序：

| # | 瓶頸 | 原因 | 為什麼是它先 |
|---|---|---|---|
| 1 | **ES 全域索引鎖** | `indexBulkRequest` 是 `private synchronized`，且 `indexBatchSize=1` | 歸檔的 1+N 次 ES 寫入在**整個 DAO 實例層級序列化**，與執行緒數無關。即 tomcat 分析的候選 B，被歸檔直接放大 N 倍 |
| 2 | **Jedis 池（10，無 `maxWait`）** | N+1 次 Redis 操作 | 即 tomcat 分析的候選 A。**唯一不會自我恢復**的一個 |
| 3 | **HikariCP（10）** | 1+N 個 transaction，且 task 迴圈在 transaction 外逐一送 | 30s 後會拋例外，會恢復但很慢 |
| 4 | **ES 單一文件過大** | `rawJSON` = 整份 WorkflowModel 含所有 task 的 input/output | 大 workflow 是 MB 級單筆寫入，直接推高 `update_workflow` 的 p99 |
| 5 | **Tomcat / sweeper 執行緒** | 以上四項的末端症狀 | sweeper 額外受 `WorkflowReconciler.java:77` 的 `.get()` 屏障影響 —— 一次慢歸檔拖慢整批 |

**關鍵放大係數是 N。** task 數大的 workflow，歸檔成本是線性增長的，而三個下游池都固定是 10。

---

## B. exporter 有沒有指標

Exporter 預設就是開的：`conductor.metrics-prometheus.enabled=true`（`server/src/main/resources/application.properties:125`），端點 `/actuator/prometheus`（`:126`）。所有 `Monitors` 指標帶 `class="WorkflowMonitor"` tag。

### 有指標（可直接監控）

| 瓶頸 | 指標 | 出處 |
|---|---|---|
| 歸檔速率 | `workflow_archived_total{workflowName, workflowStatus}` | `Monitors.java:563` |
| **ES 歸檔延遲（最有用）** | `update_workflow{docType="workflow"}` timer<br>`update_task{docType=""}` timer | `ElasticSearchRestDAOV7.java:869`、`:950` |
| ES 錯誤（含現象 1 的噪音） | `workflow_server_error_total{class="ElasticSearchRestDAOV7", methodName="update"}` | ES DAO `:955` |
| decider queue 積壓 | `_deciderQueue` gauge | `WorkflowReconciler.java:96-97` |
| decide 耗時（**已被歸檔污染**） | `workflow_decision` timer | `Monitors.java:194` |
| DB 池 | `hikaricp_connections_pending` / `_active` | Spring Boot actuator，非 conductor |
| Tomcat | `tomcat_threads_busy_threads`、`http_server_requests_seconds` | 同上 |

`update_workflow` 和 `update_task` 這兩個 timer 幾乎是為歸檔量身訂做的 —— 在 `asyncIndexingEnabled=false` 且沒有其他 `indexDAO.updateWorkflow` 呼叫點的情況下，它們的 rate 就等於歸檔 rate，p99 就是歸檔的 ES 成本。**這是最該先接上去的一組。**

### 沒有指標（缺口）

| 缺口 | 影響 |
|---|---|
| MySQL/Postgres DAO 完全沒有 `dao_requests` / `dao_payload_size` | 只有 `redis-persistence`（`BaseDynoDAO.java:92`）和 `cassandra-persistence` 有埋。**MariaDB 這一側的歸檔負載在 conductor 指標裡完全不可見**，只能靠 `hikaricp_*` 與 DB 端 |
| Jedis 連線池沒有任何 micrometer binding | 即 tomcat 分析的候選 A —— 唯一不會自我恢復的瓶頸，恰好是唯一沒有指標的。只能靠 thread dump |
| `removeWorkflow` 主路徑沒有 error metric | `Monitors.recordDaoError("executionDao","removeWorkflow")` 只存在於 `removeWorkflowWithExpiry`（`ExecutionDAOFacade.java:411`，TTL 路徑）。預設 listener 走的 `:338 removeWorkflow` **整條路徑零 error metric** → 現象 3（歸檔失敗靜默遺失資料）無法用指標監控，只能 grep `Failed to update workflow` |
| 歸檔本身沒有專屬 timer | 只能從 `workflow_decision` 的變化間接推 |
| `workflow_archival_delay_queue_size` gauge 預設不會有值 | 只有 `ArchivingWithTTLWorkflowStatusListener` 才會打。若採用 `delaySeconds` 方案，這個 gauge 就變成很好的積壓指標 |

---

## 最小監控組合

```promql
# 1. 歸檔 ES 成本（最先飽和的地方）
histogram_quantile(0.99, rate(update_workflow_seconds_bucket[5m]))
histogram_quantile(0.99, rate(update_task_seconds_bucket[5m]))

# 2. 歸檔速率 vs decide 耗時 —— 兩者同步上升即確認歸檔是主因
rate(workflow_archived_total[5m])
histogram_quantile(0.99, rate(workflow_decision_seconds_bucket[5m]))

# 3. ES 錯誤（現象 1 的噪音量，也是現象 3 的近似訊號）
rate(workflow_server_error_total{class="ElasticSearchRestDAOV7"}[5m])

# 4. DB 池排隊（MariaDB 側唯一可見的訊號）
hikaricp_connections_pending

# 5. sweeper 是否跟得上
_deciderQueue
```

指標名稱以實際 `/actuator/prometheus` 輸出為準 —— micrometer 會做 snake case 正規化，timer 會展開成 `_seconds_count` / `_sum` / `_bucket`，`_deciderQueue` 這種底線開頭的名稱可能被改寫。

---

## 建議補的埋點

兩個都很小：

1. `ExecutionDAOFacade.removeWorkflow` 的 `:341-346` 加一個 try/catch + `Monitors.recordDaoError` —— 讓現象 3 從「只能 grep log」變成可告警。
2. 同一段包一個 timer —— 讓歸檔成本脫離 `workflow_decision` 的混淆。
