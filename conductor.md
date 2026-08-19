# Conductor Archive Listener 問題分析

## 環境

| 項目 | 值 | 對應模組 / 實作 |
|---|---|---|
| DB | MariaDB | `conductor.db.type=mysql` → `mysql-persistence` / `MySQLExecutionDAO` |
| Queue | Redis | `conductor.queue.type=redis_standalone` → `redis-persistence` / `DynoQueueDAO` |
| Index | Elasticsearch 7 | `conductor.elasticsearch.version` 預設 `7` → `es7-persistence` / `ElasticSearchRestDAOV7` |
| 設定 | **只有** `conductor.workflow-status-listener.type=archive`，其餘全部預設 | |

參考範本：`docker/server/config/config-mysql.properties`

「其餘全部預設」推導出的關鍵值：

| 屬性 | 預設值 | 出處 |
|---|---|---|
| `conductor.app.taskIndexingEnabled` | `true` | `core/.../config/ConductorProperties.java:94` |
| `conductor.app.asyncIndexingEnabled` | `false`（同步索引） | `ConductorProperties.java:100` |
| `conductor.workflow-status-listener.archival.ttlDuration` | `0` | `.../archive/ArchivingWorkflowListenerProperties.java:61` |
| → 因此選用的 listener | `ArchivingWorkflowStatusListener`（**立即執行、無 try/catch**） | `.../archive/ArchivingWorkflowListenerConfiguration.java:37` |

版本基準：本 repo `v3.22.0-alpha1`（commit `7f6653a7f`）。所有行號對應此版本。

---

## 0. 背景：`removeWorkflow` 到底做了什麼

### 觸發條件

只有 workflow definition 設了 `workflowStatusListenerEnabled: true` 才會觸發歸檔。

| 檔案 | 行號 | 說明 |
|---|---|---|
| `core/.../core/listener/WorkflowStatusListener.java` | 20-36 | `onWorkflowXxxIfEnabled` 檢查 `isWorkflowStatusListenerEnabled()` |
| `core/.../core/execution/WorkflowExecutorOps.java` | 550 | workflow 完成時觸發 |
| `core/.../core/execution/WorkflowExecutorOps.java` | 699 | workflow 終止時觸發（緊接在 `:698` 的 `cancelNonTerminalTasks` 之後） |

### Listener 的選用

| 檔案 | 行號 | 說明 |
|---|---|---|
| `.../archive/ArchivingWorkflowListenerConfiguration.java` | 25 | `@ConditionalOnProperty(havingValue = "archive")` |
| 同上 | 31-38 | `ttlDuration > 0` → TTL 版；`archivalType=S3` → S3 版；否則 → 預設版（**本案**） |
| `.../archive/ArchivingWorkflowStatusListener.java` | 42, 49 | 預設版，同步呼叫 `removeWorkflow(id, true)`，**無 try/catch** |
| `.../archive/ArchivingWithTTLWorkflowStatusListener.java` | 56 | constructor 直接 warn「TTL is no longer supported」 |
| 同上 | 83-90, 97-104 | `delayArchiveSeconds > 0` 走延遲排程，否則立即執行 |
| 同上 | 124-134 | 延遲路徑的 `run()` **有** try/catch，例外只記 log |
| `.../archive/ArchivingWorkflowListenerProperties.java` | 115-122 | `getWorkflowArchivalDelay()`：`archival.delaySeconds` → `conductor.app.asyncUpdateDelaySeconds` → 60 |

### 主流程

`core/src/main/java/com/netflix/conductor/core/dal/ExecutionDAOFacade.java:338-378`

```
339  workflow = getWorkflowModelFromDataStore(workflowId, true)   // 讀出 workflow + tasks
341  executionDAO.removeWorkflow(workflowId)                      // ★ DB 全刪（含所有 task）
343  removeWorkflowIndex(workflow, archiveWorkflow)               // 寫 conductor_workflow 的 rawJSON
348  for each task:
352      removeTaskIndex(...)                                     // 寫 conductor_task 的 archived 標記
362      queueDAO.remove(task queue, taskId)                      // Redis
374  queueDAO.remove("_deciderQueue", workflowId)                 // Redis
```

重點：**`archiveWorkflow` 這個 flag 對 DB 完全沒有影響，DB 一律硬刪**。它只影響 index 是「標記保留」還是「刪除」。

### 實際刪除的 table

`mysql-persistence/.../dao/MySQLExecutionDAO.java:287-305`

Transaction 1（原子）：

| Table | 程式碼位置 |
|---|---|
| `workflow_def_to_workflow` | `:789-801` |
| `workflow` | `:665-668` |
| `workflow_pending` | `:692-701` |

Transaction 外，逐一 task（每個 task 各自一個 transaction，`:209-227`）：

| Table | 程式碼位置 |
|---|---|
| `task_scheduled` | `:837-848` |
| `workflow_to_task` | `:762-773` |
| `task_in_progress` | `:877-883` |
| `task` | `:729-732` |

Queue 端由 Redis 的 `DynoQueueDAO` 處理（task queue + `_deciderQueue`），**不涉及 `queue_message` table**（那是 postgres/mysql queue 模式才有的）。

**不會刪的**：`meta_workflow_def` / `meta_task_def` / `event_execution` / `poll_data`，以及 external payload storage 上的大 payload。

### Index 端（`archiveWorkflow=true`）

| 對象 | 行為 | 程式碼位置 |
|---|---|---|
| workflow doc | 寫入 `rawJSON`（整份 WorkflowModel，含 tasks）+ `archived=true`，**不刪 doc** | `ExecutionDAOFacade.java:380-400`（386-389） |
| task doc | 只寫 `archived=true`，**不存 rawJSON** | `ExecutionDAOFacade.java:540-561`（546-550） |
| 讀回 | DB 找不到時 fallback 去 index 撈 `rawJSON` 還原 | `ExecutionDAOFacade.java:156-179`（160） |

---

## 現象 1：ES 持續噴 `document_missing_exception`（index = `conductor_task`）

**這是目前需要優先消除的 log 噪音來源。**

### 已排除的原因

| 假設 | 排除依據 |
|---|---|
| index 不存在 | 錯誤是 `document_missing_exception` 而非 `index_not_found_exception` |
| `conductor.app.taskIndexingEnabled=false` | 為預設值 `true`（`ConductorProperties.java:94`） |
| `conductor.app.asyncIndexingEnabled=true` 的競態 | 為預設值 `false`（`ConductorProperties.java:100`） |

### 可能原因（已確認）

同步索引模式下，task 只有**一個**地方會被寫進 ES —— `updateTask`。而 `createTasks` 完全沒有索引動作。所以**任何「建立之後從未被 update 過」的 task，在 ES 裡根本沒有 document**。

典型來源是 `DeciderService` 建立時就直接進終態的 system task（SWITCH / FORK / JOIN 等）：它們在 `decide()` 裡因為 `NON_TERMINAL_TASK.test(task)` 為 false 而不會被加進 `tasksToBeUpdated`，於是從頭到尾沒有任何一次 `updateTask`。

歸檔時 `removeTaskIndex` 假設每個 task 都有 doc，直接發 `UpdateRequest`（無 upsert）→ 必然 `document_missing_exception`。

### 對應程式碼邏輯

| 檔案 | 行號 | 內容 |
|---|---|---|
| `core/.../dal/ExecutionDAOFacade.java` | 436-439 | `createTasks()` 只呼叫 `executionDAO.createTasks(tasks)`，**沒有** `indexDAO.indexTask` |
| `core/.../execution/WorkflowExecutorOps.java` | 1493 | `scheduleTask()` 建立 task 走的就是上面那條 |
| `core/.../execution/WorkflowExecutorOps.java` | 1076-1092 | `decide()` 只把執行過的 async=false system task 放進 `tasksToBeUpdated` |
| `core/.../dal/ExecutionDAOFacade.java` | 516-518 | 唯一的同步索引點：`if (!isAsyncIndexingEnabled() && isTaskIndexingEnabled()) indexDAO.indexTask(...)` |
| `core/.../dal/ExecutionDAOFacade.java` | 540-561 | `removeTaskIndex()` 無條件呼叫 `indexDAO.updateTask(...)`；**沒有**檢查 `isTaskIndexingEnabled()`（對比 `:516` 有檢查） |
| `es7-persistence/.../index/ElasticSearchRestDAOV7.java` | 935 | `new UpdateRequest(taskIndexName, taskId)` — partial update，doc 不存在就失敗 |
| 同上 | 950 | `Monitors.recordESIndexTime("update_task", ...)` — log 中 `update_task` 字樣的來源 |
| 同上 | 953-956 | `catch (Exception e) { logger.error(...); Monitors.error(className, "update"); }` — **例外被吞掉，但同時產生 error log 與 error metric** |

### 影響評估

**不造成資料遺失。** 例外被吞掉不影響流程，且 workflow 的 `rawJSON`（含完整 tasks）已成功寫進 `conductor_workflow` —— 這就是為什麼 UI 上仍看得到該 workflow 的歷史紀錄。

實際影響只有兩項，且都是噪音層面：
1. 每個未索引的 task 產生一筆 ERROR log（含 stack trace）
2. 每筆同時打一次 `Monitors.error(className, "update")` metric

在「設定為 `archive` 的 workflow def」數量大時，這會等比例放大到 monitor stack。

### 可能解法

#### 解法 1（建議）：讓 ES DAO 把 404 視為非錯誤

`indexDAO.updateTask` 在整個 codebase **只有一個呼叫點** —— `ExecutionDAOFacade.java:546` 的歸檔路徑（可用 `grep -rn "indexDAO.updateTask" core/src/main` 驗證）。而在一個不存在的 doc 上設 `archived=true` 本來就是語意上的 no-op，沒有任何資訊遺失。因此把 404 降級處理的影響範圍為零。

`es7-persistence/.../index/ElasticSearchRestDAOV7.java:953-956`：

```java
// import org.elasticsearch.ElasticsearchStatusException;
// import org.elasticsearch.rest.RestStatus;

} catch (ElasticsearchStatusException e) {
    if (e.status() == RestStatus.NOT_FOUND) {
        // task 從未被索引（例如建立時即為終態的 system task）；
        // 在不存在的 doc 上標記 archived 本就是 no-op
        logger.debug(
                "Task document not indexed, skipping archive marker: {} of workflow: {}",
                taskId, workflowId);
    } else {
        logger.error("Failed to update task: {} of workflow: {}", taskId, workflowId, e);
        Monitors.error(className, "update");
    }
} catch (Exception e) {
    logger.error("Failed to update task: {} of workflow: {}", taskId, workflowId, e);
    Monitors.error(className, "update");
}
```

同時消除 error log 與 error metric，不改變任何行為，不增加 ES 寫入量。

#### 解法 2：從根本讓每個 task 都有 doc

在 `ExecutionDAOFacade.createTasks`（`:436-439`）加上與 `:516` 相同條件的 `indexDAO.indexTask(...)`。

- 優點：順帶修好「部分 task 在 ES 完全搜不到」這個既有缺口
- 缺點：每個 task 多一次同步 ES 寫入，寫入量上升

#### 解法 3：關閉 task 索引

設 `conductor.app.taskIndexingEnabled=false`，**並** patch `removeTaskIndex`（`:540`）加上 `isTaskIndexingEnabled()` 判斷與 `:516` 對齊。

- 優點：噪音歸零，ES 寫入量大幅下降
- 缺點：task 層級搜尋整個失效（UI 的 task 查詢頁面會空）

#### 不建議

直接把 `com.netflix.conductor.es7.dao.index.ElasticSearchRestDAOV7` 的 log level 調高——會連真正的索引錯誤一起吃掉。

---

## 現象 2：workflow table 資料消失，但 task / workflow_to_task 仍在

### 觀察

- workflow status 變 TERMINATED 後，`workflow` table 的列很快消失
- `task`、`workflow_to_task` 等 table 的列仍然存在
- log 中可見 `Archiving workflow <id> on termination`
- ES 中該 workflow 仍在（UI 可見）

### 關鍵結構事實

`removeWorkflow` 的 task 刪除**不在 workflow 刪除的 transaction 內**：

`mysql-persistence/.../MySQLExecutionDAO.java:287-305`

```java
withTransaction(connection -> {              // transaction 1，原子
    removeWorkflowDefToWorkflowMapping(connection, workflow);   // :789
    removeWorkflow(connection, workflowId);                     // :665  DELETE FROM workflow
    removePendingWorkflow(connection, ...);                     // :692
});
removed = true;

for (TaskModel task : workflow.getTasks()) { // 迴圈在 transaction 外
    if (!removeTask(task.getTaskId())) {     // :209  每個 task 各自一個 transaction
        removed = false;
    }
}
```

所以「workflow 沒了、task 還在」在結構上是做得到的，而且沒有任何回滾或補償機制。

### 可能原因 A：刪除後被重新寫入（「復活」）

寫入語句在 task 側和 workflow 側是**不對稱**的：

| 對象 | 語句 | 程式碼位置 | 目標列不存在時 |
|---|---|---|---|
| `task` | `UPDATE ... WHERE task_id=?`，`rowsUpdated == 0` 就 `INSERT ... ON DUPLICATE KEY UPDATE` | `MySQLExecutionDAO.java:703-727` | **重新建立** |
| `workflow_to_task` | `SELECT EXISTS(...)`，不存在就 `INSERT IGNORE` | `MySQLExecutionDAO.java:734-758` | **重新建立** |
| `workflow` | `UPDATE workflow SET json_data=? WHERE workflow_id=?`（無 insert fallback） | `MySQLExecutionDAO.java:652-663` | **保持消失** |

因此：**任何在歸檔之後才抵達的 `executionDAOFacade.updateTask(task)`，都會把 `task` 與 `workflow_to_task` 兩張表的列重建，而同時間對 `workflow` 表的寫入是純 UPDATE、命中 0 列。** 這正好產生觀察到的狀態。

`executionDAOFacade.updateTask`（`ExecutionDAOFacade.java:497-530`）**沒有任何 workflow 是否還存在的檢查**。

可能的延遲寫入來源：

| 來源 | 程式碼位置 | 說明 |
|---|---|---|
| `updateParentWorkflowTask` | `WorkflowExecutorOps.java:649` | 子 workflow 比父 workflow 晚結束時，回頭更新父的 SUB_WORKFLOW task |
| `cancelNonTerminalTasks` | `WorkflowExecutorOps.java:1205` | sweeper 重跑 `decide()` 時；`decide` 對 terminal + unsuccessful 的 workflow 會呼叫它（`:1049-1053`） |
| sweeper 的 ES fallback | `ExecutionDAOFacade.java:160` + `WorkflowSweeper.java:94` | workflow 已不在 DB，但 `rawJSON` 在 ES → `getWorkflowModel` 成功還原 → `decide()` 繼續對它動作 |

> 註：本案 `archiveWorkflow=true` 且 workflow 歸檔成功（UI 可見），所以 ES fallback 這條路徑是**通的**，sweeper 確實有可能把已刪除的 workflow 撈回來繼續處理。

### 可能原因 B：task 迴圈根本沒跑完

- `workflow.getTasks()` 為空 → 迴圈不執行
- 迴圈中途拋例外 → 剩餘 task 全部殘留（`MySQLExecutionDAO.java:297-303` 無 try/catch）
- `removeTask` 遇到 `getTask()` 回 null 時**直接 return false 且不刪 `workflow_to_task`**（`:211-215`），造成孤兒 mapping 永久殘留

相關讀取路徑：

| 檔案 | 行號 | 內容 |
|---|---|---|
| `MySQLExecutionDAO.java` | 328-340 | `getWorkflow(id, true)` → `readWorkflow` + `getTasksForWorkflow` |
| `MySQLExecutionDAO.java` | 260-274 | `SELECT task_id FROM workflow_to_task WHERE workflow_id = ?` |
| `MySQLExecutionDAO.java` | 562-578 | `SELECT json_data FROM task WHERE task_id IN (...) AND json_data IS NOT NULL` |

> 註：`AND json_data IS NOT NULL` 會靜默過濾掉列，但 schema 對 `task.json_data` 有 `NOT NULL` 約束（`mysql-persistence/src/main/resources/db/migration/V1__initial_schema.sql:99`），所以此路徑不可能發生。

### 決定性的判別方式（尚未執行）

`task_scheduled` 這張表**只有** `createTasks` 會寫入（`MySQLExecutionDAO.java:121`），`updateTask` 永遠不會重建它。這是區分 A 和 B 的乾淨訊號。

```sql
SELECT
 (SELECT count(*) FROM workflow_to_task wt
    LEFT JOIN workflow w ON w.workflow_id = wt.workflow_id
    WHERE w.workflow_id IS NULL)  AS orphan_workflow_to_task,
 (SELECT count(*) FROM task_scheduled ts
    LEFT JOIN workflow w ON w.workflow_id = ts.workflow_id
    WHERE w.workflow_id IS NULL)  AS orphan_task_scheduled;
```

| 結果 | 結論 |
|---|---|
| `orphan_workflow_to_task > 0` 且 `orphan_task_scheduled = 0` | **原因 A（復活）** |
| 兩者皆 > 0 | **原因 B（沒刪到）** |

輔助查詢 —— `created_on` 若晚於 log 中 `Archiving workflow <id> on termination` 的時間，即坐實原因 A：

```sql
SELECT wt.workflow_id, t.task_id, t.created_on, t.modified_on,
       JSON_UNQUOTE(JSON_EXTRACT(t.json_data, '$.taskType')) AS task_type,
       JSON_UNQUOTE(JSON_EXTRACT(t.json_data, '$.status'))   AS status
FROM workflow_to_task wt
JOIN task t ON t.task_id = wt.task_id
LEFT JOIN workflow w ON w.workflow_id = wt.workflow_id
WHERE w.workflow_id IS NULL
ORDER BY t.created_on DESC LIMIT 20;
```

若 `task_type` 集中在 `SUB_WORKFLOW`，延遲寫入來源即為 `updateParentWorkflowTask`。

### 可能解法

**針對原因 A（復活）**

1. **延遲歸檔**（設定即可，最低成本）。切到延遲版 listener，讓遲到的寫入先落地：
   ```properties
   conductor.workflow-status-listener.archival.ttlDuration=1s
   conductor.workflow-status-listener.archival.delaySeconds=90
   ```
   `ttlDuration > 0` 只是用來讓 `ArchivingWorkflowListenerConfiguration.java:31` 選到 `ArchivingWithTTLWorkflowStatusListener`；TTL 本身在 MariaDB 無作用（`MySQLExecutionDAO.java:311-315` 直接丟 `UnsupportedOperationException`，但該 listener 走的是 `removeWorkflow` 而非 `removeWorkflowWithExpiry`，所以不會踩到）。真正生效的是 `delaySeconds`。
   附帶好處：延遲版把 `removeWorkflow` 包在 try/catch 裡（`ArchivingWithTTLWorkflowStatusListener.java:124-134`），歸檔例外不會再往上拋進 `terminateWorkflow`。
   註：這只縮小 race window，無法根除。

2. **在 `updateTask` 加防護**（根治）。`ExecutionDAOFacade.java:497` 或 `MySQLExecutionDAO.insertOrUpdateTaskData`（`:703`）改成不做 insert fallback，或先確認 workflow 仍存在才寫入。需評估對正常流程的影響。

3. **定期清理孤兒列**（止血）：
   ```sql
   DELETE t FROM task t
     JOIN workflow_to_task wt ON wt.task_id = t.task_id
     LEFT JOIN workflow w ON w.workflow_id = wt.workflow_id
     WHERE w.workflow_id IS NULL;
   DELETE wt FROM workflow_to_task wt
     LEFT JOIN workflow w ON w.workflow_id = wt.workflow_id
     WHERE w.workflow_id IS NULL;
   ```

**針對原因 B（沒刪到）**

4. 把 task 刪除迴圈納入同一個 transaction（`MySQLExecutionDAO.java:290-303`）。
5. 修 `removeTask` 的 `task == null` 分支（`:211-215`），即使 task 不存在也要刪掉 `workflow_to_task` mapping。

---

## 現象 3（潛在風險，目前未觸發）：歸檔失敗會靜默遺失資料

### 可能原因

`ExecutionDAOFacade.java:341` 先刪 DB，`:343` 才寫 index。而 `:342` 的 try 只 catch `JsonProcessingException`，且 ES DAO 內部又把所有例外吞掉。程式碼註解寫「DO NOT archive async, since if archival errors out, workflow data will be lost」，但實際順序已經是先刪 DB。

因此只要 `indexDAO.updateWorkflow` 失敗，該 workflow 就同時不在 DB 也不在 ES，只留一行 error log。

### 對應程式碼邏輯

| 檔案 | 行號 | 內容 |
|---|---|---|
| `core/.../dal/ExecutionDAOFacade.java` | 341-346 | 先 `executionDAO.removeWorkflow`，後 `removeWorkflowIndex`；try 只 catch `JsonProcessingException` |
| `es7-persistence/.../ElasticSearchRestDAOV7.java` | 848-880 | `updateWorkflow` 的例外同樣被吞掉 |
| `core/.../dal/ExecutionDAOFacade.java` | 402-414 | 對比：`removeWorkflowWithExpiry` 是**先 index 後 DB**，順序才是對的 |
| `core/.../index/NoopIndexDAO.java` | 85 | 若 `conductor.indexing.enabled=false`（`NoopIndexDAOConfiguration.java:22`），`updateWorkflow` 是空實作 → 歸檔等於純刪除 |

> 若日後改用 async 索引模式（`conductor.app.asyncIndexingEnabled=true`）還有額外風險：`ExecutionDAOFacade.java:294-312` 的 `DelayWorkflowUpdate` 會把短命 workflow（< `asyncUpdateShortRunningWorkflowDuration`，預設 30s，`ConductorProperties.java:135`）的 index 寫入延後 `asyncUpdateDelay`（預設 60s，`:142`）。延遲的 `asyncIndexWorkflow` 用 `IndexRequest` 做整份 document 覆蓋，會把歸檔寫入的 `rawJSON` 抹掉。屆時 `archival.delaySeconds` 必須大於 `conductor.app.asyncUpdateDelay`。

### 可能解法

1. 監控 log 中的 `Failed to update workflow`，出現即代表資料遺失。**注意：現象 1 的解法 1 只降級 `updateTask` 的 404，不影響這條偵測。**
2. 把 `ExecutionDAOFacade.removeWorkflow` 改成先歸檔成功再刪 DB（對齊 `removeWorkflowWithExpiry` 的順序）。
3. 讓 ES DAO 的 `updateWorkflow` 在歸檔情境下拋出例外而非吞掉，讓上層能察覺。

---

## 附錄：優先處理順序

| # | 動作 | 目的 | 成本 |
|---|---|---|---|
| 1 | 套用現象 1 的解法 1（ES DAO 404 降級） | **消除 log 噪音**（首要需求） | 一個 catch block |
| 2 | grep log 確認有無 `Failed to update workflow` | 確認現象 3 是否已在發生 | 零 |
| 3 | 執行現象 2 的決定性 SQL | 收斂到原因 A 或 B —— 唯一還沒確定的分岔 | 零 |
| 4 | 依 3 的結果套用對應解法 | 修正 DB 殘留 | 視結果而定 |

---

## 設定 archive 後的監控
建議的優先順序

1. terminationGracePeriodSeconds 調到 90（> delaySeconds + 緩衝）。防止每次部署漏掉一批清理。成本最低、避免的是永久性資料殘留。
2. 跑一次 orphan SQL，確認 worker 的無延遲刪除有沒有把 race 帶回 COMPLETED。有的話，讓 worker 也延遲個 30–60 秒再刪。
3. B 想真的解，只有兩條路：降低 workflow 完成率或 task 數（不現實），或是把清理批次化 + 移到離峰——也就是我上一輪提的外部 cron。cron 的價值不只是解耦，而是你可以控制刪除速率，讓它不跟線上尖峰搶連線池、也讓 InnoDB purge 追得上。現在的 event-driven 模式做不到這件事：清理負載精確地跟工作負載同步尖峰。
4. 監控 recordArchivalDelayQueueSize 和 InnoDB history list length。 前者是 archive backlog 的早期訊號，後者是 B 惡化的早期訊號。兩個都是「壞掉之前會先漲」的指標。
5. 那兩行 not-found 的 ERROR，如果量確實有感，DelayArchiveWorkflow.run() 裡多接一個 catch (NotFoundException e) { LOGGER.debug(...) } 就好——但 ExecutionDAOFacade:162 那行 ERROR 在 throw 之前，得一起改才會乾淨。