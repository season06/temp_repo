# Decider 與 Sweeper 機制

> 對象：Conductor 初學者
> 範圍：`core/execution`、`core/reconciliation`，以及 `workflow-event-listener` 的歸檔交互
> 所有行號對應目前工作目錄的原始碼，升級版本後請重新核對。

---

## 先記住這一句

| | **DeciderService**（大腦） | **WorkflowSweeper**（心跳） |
|---|---|---|
| 是什麼 | 一個純粹的決策函式 | 一個背景執行緒 |
| 做什麼 | 給它 workflow 的當前狀態，算出「接下來該排哪些 task、哪些 task 要更新、workflow 是否結束」 | 定期把還在跑的 workflow 撈出來丟給大腦重新評估，確保沒有流程卡死 |
| 不做什麼 | 不寫資料庫、不推佇列 | 不做任何決策 |
| 位置 | `core/execution/DeciderService.java` | `core/reconciliation/WorkflowSweeper.java` |

---

## 為什麼會需要這兩個東西

Conductor 是 **orchestration engine**：workflow 的定義與執行狀態全部存在資料庫，worker 只做兩件事 —— 從佇列 poll task、把結果回報回來。worker 完全不知道自己是流程裡的第幾步，也不知道下一步是誰。

所以 server 必須在某些時刻「重新讀取 workflow 的完整狀態，推進狀態機」。這個動作叫 **decide**。問題變成：**什麼時候該 decide？**

**一、有事情發生的時候（事件驅動）**
worker 回報 task 完成、workflow 剛被啟動、使用者按下 retry/rerun、有人打 REST API。這些路徑都會同步地直接呼叫 `decide()`。

**二、什麼事都沒發生的時候（時間驅動）**
task 逾時了嗎？領走工作的 worker 掛了、永遠不會回報？佇列訊息在 Redis 重啟時掉了？`WAIT` task 的時間到了沒？這些狀況**不會有人來通知你**。這就是 Sweeper 存在的唯一理由。

```
        事件驅動                                  純運算              副作用
  worker 回報 task 結果 ─┐
  startWorkflow/retry  ─┼─→ decide(workflowId) ─→ DeciderService ─→ WorkflowExecutorOps
  PUT /{id}/decide     ─┘    ① 取鎖，搶不到就放棄     .decide()          排 task 進佇列
                             ② 從 DAO 讀 workflow        ↓               寫回資料庫
        時間驅動                     ↑              DeciderOutcome       執行同步系統 task
  _deciderQueue                      │              ├ tasksToBeScheduled endExecution()
        ↓ 每 500ms pop 一批          │              ├ tasksToBeUpdated        │
  WorkflowReconciler                 │              └ isComplete              │
        ↓                            │                                        │
  WorkflowSweeper.sweep() ───────────┘                                        │
                                     └──── stateChanged == true，再 decide 一次 ┘
```

---

## Part 1 — Decider：算出下一步

### 回傳值就是它的全部意義

`core/src/main/java/com/netflix/conductor/core/execution/DeciderService.java:930`

```java
public static class DeciderOutcome {
    List<TaskModel> tasksToBeScheduled;   // 接下來要排的 task
    List<TaskModel> tasksToBeUpdated;     // 狀態要寫回 DB 的 task
    boolean isComplete;                   // workflow 是否已經結束
    TaskModel terminateTask;
}
```

> **DeciderService 本身不寫資料庫、不推佇列、不呼叫 worker。** 它是純運算。這個「決策邏輯」與「副作用」分離的設計是整個 core 模組最重要的一條線 —— 因為決策是純的，所以可以被安全地重複執行任意次，而這正是 Sweeper 敢無腦重掃的前提。

### 它的演算法

展開 `DeciderService.java:112-300`：

1. **是新的 workflow 嗎？** 未處理 task 清單是空的 → `startWorkflow()` 排出第一個 task（`:104`）
2. **已經是終止狀態或 PAUSED？** 直接回傳空 outcome（`:117`、`:128`）
3. **檢查 workflow 層級逾時** —— `checkWorkflowTimeout()`（`:126`）
4. **逐一走過每個 pending task**（`:168`）：
   - 檢查 task timeout / poll timeout / response timeout，逾時就標記 `TIMED_OUT`（`:187-193`）
   - task 失敗了？依 retry 設定產生新的 retry task（`:204`）
   - task 已完成？標記 `executed = true`，再依 workflow definition 找出**下一個** task 加入排程（`:217-231`）
5. **沒有東西可排了？** 檢查 workflow 是否整體完成 —— `checkForWorkflowCompletion()`（`:257`）

注意第 4 步：**「下一個 task 是誰」是每次 decide 當場從 workflow definition 重新推導的**，不是預先展開好的執行計畫。這也是為什麼 `SWITCH`、`DO_WHILE`、`FORK_JOIN_DYNAMIC` 這些動態結構能運作。

### 副作用由誰執行

`core/src/main/java/com/netflix/conductor/core/execution/WorkflowExecutorOps.java:1021`

```java
public WorkflowModel decide(String workflowId) {
    if (!executionLockService.acquireLock(workflowId)) return null;  // 搶不到鎖就放棄
    try {
        WorkflowModel workflow = executionDAOFacade.getWorkflowModel(workflowId, true);
        return decide(workflow);
    } finally { executionLockService.releaseLock(workflowId); }
}
```

真正幹活的是 private 的 `decide(workflow)`（`:1049`）：

- 呼叫 `deciderService.decide()` 拿到 outcome
- `outcome.isComplete` → `endExecution()` 結束整個 workflow
- `scheduleTask()` → 把 task 寫進資料庫，**並推進 task 專屬的佇列**，worker 才 poll 得到
- 同步的系統 task（`SWITCH`、`INLINE`、`SET_VARIABLE`）就地直接執行（`:1082`）

然後是很容易被忽略的一行（`:1094`）：

```java
if (stateChanged) {
    return decide(workflow);   // 遞迴：只要狀態有變，就再算一輪
}
```

**decide 不是只跑一次。** 只要這一輪造成狀態改變，就立刻再評估一次，直到狀態穩定。這就是為什麼一連串同步的 `SWITCH → SET_VARIABLE → INLINE` 會在同一次呼叫裡全部跑完。

### 鎖：不等、不排隊、搶不到就走

`ExecutionLockService.java:43-47` 的註解：

> 因為 decide 可以從多個入口觸發、又會被 sweeper 週期性觸發，**不要阻塞等鎖 —— 同一個 workflow 上 decide 的執行順序並不重要**。

搶不到鎖就直接返回。因為 decide 是冪等的，而且 Sweeper 保證等一下還會再來一次 —— 錯過一次沒有任何損失。

這個鎖**預設是關閉的**（`ConductorProperties.java:70`，`workflowExecutionLockEnabled = false`），單機部署用不到；多節點部署才需要搭配 `redis-lock` 模組打開。

---

## Part 2 — Sweeper：讓決策準時發生

### 核心資料結構：decider queue

`core/src/main/java/com/netflix/conductor/core/utils/Utils.java:25`

```java
public static final String DECIDER_QUEUE = "_deciderQueue";
```

**每一個正在執行中的 workflow，在這個佇列裡都有恰好一則訊息，內容就是它的 workflowId。** workflow 一被建立就推進去 —— `ExecutionDAOFacade.java:250`：

```java
public String createWorkflow(WorkflowModel workflowModel) {
    externalizeWorkflowData(workflowModel);
    executionDAO.createWorkflow(workflowModel);
    // Add to decider queue
    queueDAO.push(DECIDER_QUEUE, workflowModel.getWorkflowId(),
                  workflowModel.getPriority(),
                  properties.getWorkflowOffsetTimeout().getSeconds());  // 預設延遲 30 秒
    ...
}
```

> 這個佇列的關鍵性質是 **visibility timeout（unack）語意**，跟 AWS SQS 一樣：pop 出來的訊息**不會消失**，只是暫時隱形；除非明確呼叫 `remove`，否則隱形時間一到它會**自己回到佇列裡**。整個 Sweeper 機制都建立在這個性質上。

### 外層迴圈：WorkflowReconciler

`core/src/main/java/com/netflix/conductor/core/reconciliation/WorkflowReconciler.java:61`

```java
@Scheduled(fixedDelayString = "${conductor.sweep-frequency.millis:500}")
public void pollAndSweep() {
    List<String> workflowIds =
            queueDAO.pop(DECIDER_QUEUE, sweeperThreadCount, sweeperWorkflowPollTimeout);
    CompletableFuture.allOf(
            workflowIds.stream().map(workflowSweeper::sweepAsync)
                       .toArray(CompletableFuture[]::new)
    ).get();   // 等這一批全部掃完，才進下一輪
}
```

每 500ms 撈一批（批次大小預設 `CPU 核心數 × 2`），丟進專屬執行緒池平行處理（`SchedulerConfiguration.java:56`，固定大小 = `sweeperThreadCount`）。

注意最後那個 `.get()`：**這一批沒掃完，下一輪不會開始** —— 單一個慢掃描會拖慢整個節點的 sweep 節奏，這在效能調查時是常見線索。

### 單次清掃：sweep() 的四個動作

`core/src/main/java/com/netflix/conductor/core/reconciliation/WorkflowSweeper.java:79`

```java
if (!executionLockService.acquireLock(workflowId)) return;
workflow = executionDAOFacade.getWorkflowModel(workflowId, true);

workflowRepairService.verifyAndRepairWorkflowTasks(workflow);   // ① 修復
workflow = workflowExecutor.decide(workflow.getWorkflowId());   // ② 決策

if (workflow.getStatus().isTerminal()) {
    queueDAO.remove(DECIDER_QUEUE, workflowId);                 // ③ 結束了 → 移出佇列
    return;
}
...
unack(workflow, workflowOffsetWithJitter(...));                 // ④ 沒結束 → 安排下次
```

步驟 ② 就是 Part 1 的 Decider。真正屬於 Sweeper 的智慧在 ①、③、④。

步驟 ③ 值得特別留意：**「移出佇列」是 workflow 生命週期的真正終點** —— 只要訊息還在 `_deciderQueue` 裡，這個 workflow 就會被永遠掃下去。

### ① Repair：修補資料庫與佇列的不一致

資料庫說某個 task 是 `SCHEDULED`，但 task 佇列裡的那則訊息掉了（Redis 重啟、網路分割、程式在兩次寫入之間崩潰）。結果是 —— **worker 永遠 poll 不到它，workflow 永久卡死**。資料庫與佇列是兩個獨立儲存，它們之間沒有交易保證。

`WorkflowRepairService.java:141` 專門處理這件事：

- 處於 `SCHEDULED` 的 task，在它的佇列裡有訊息嗎？沒有就補推一則（`:145-146`）
- sub-workflow 已結束，但父層 `SUB_WORKFLOW` task 還停在 `IN_PROGRESS`？把狀態同步過來（`:154-165`）
- workflow 還在跑卻不在 `_deciderQueue` 裡？重新推回去（`:170-180`）

這個服務是 **opt-in** 的：`conductor.workflow-repair-service.enabled=true`，因為它要求底層佇列實作支援 `containsMessage()`。`WorkflowSweeper` 的建構子用 `Optional<WorkflowRepairService>` 接它（`:59`），沒開就跳過。

### ④ unack：Sweeper 最巧妙的部分

天真的實作是「每 30 秒把每個 workflow 都掃一次」。但如果某個 task 的 `responseTimeout` 是 2 小時，這 2 小時內的 240 次掃描全是白工 —— 每次都要讀資料庫、跑完整 decide、什麼都不會改變。在幾十萬併行 workflow 的規模下，這個成本是災難性的。

Conductor 的做法是：**根據這個 workflow 現在正在等什麼，反推出「下次最早什麼時候需要再看它」**，然後用 `setUnackTimeout` 讓訊息剛好隱形那麼久。

```
假設 task 的 responseTimeout = 120s

天真做法（固定每 30 秒）：
  0s ──── 30s ──── 60s ──── 90s ──── 121s
   ↑       ↑        ↑        ↑        ↑
  掃      白工      白工      白工    才有用      → 掃了 5 次

Conductor（unack(responseTimeout + 1)）：
  0s ═══════════ 訊息隱形 121 秒 ═══════════ 121s
   ↑                                          ↑
  掃完算出 121s                          自動浮回佇列   → 掃了 2 次
```

`+1` 秒的用意是讓 Sweeper 剛好在逾時發生**之後**醒來，這樣 Decider 一跑就能立刻判定 `TIMED_OUT` 並處理 —— 早一秒醒來就得再等一整輪。

`unack()`（`WorkflowSweeper.java:127`）走過 task 清單，遇到第一個未完成的 task 就決定延後多久：

| 當前第一個未完成的 task | 下次檢查時間 | 理由 |
|---|---|---|
| `IN_PROGRESS` 的 `WAIT`，有 timeout | 剛好等到 wait 時間到 | 那一刻之前不可能有任何變化 |
| `IN_PROGRESS` 的 `WAIT`／`HUMAN`，無 timeout | `workflowOffsetTimeout` | 無從預測，用預設值定期關心 |
| `IN_PROGRESS` 的一般 task | `responseTimeoutSeconds + 1` | worker 最晚該在這時候回報 |
| `SCHEDULED`，taskDef 有 pollTimeout | `pollTimeoutSeconds + 1` | 最晚該在這時候被領走 |
| `SCHEDULED`，其餘情況 | workflow timeout `+ 1` | 退而求其次，用 workflow 層級的界線 |

最後統一 clamp 在 `maxPostponeDurationSeconds`（預設 1 小時，`:148-152`）—— 再怎麼確定不會有事，也不容許超過一小時不看一眼。

### Jitter：避免驚群效應

`WorkflowSweeper.java:190`

```java
long range  = workflowOffsetTimeout / 3;
long jitter = new Random().nextInt((int) (2 * range + 1)) - range;
return workflowOffsetTimeout + jitter;   // 30s → 隨機落在 20~40s
```

如果一次啟動一萬個 workflow，沒有 jitter 的話它們會在 30 秒後**同時**湧回佇列，瞬間把 sweeper 執行緒池打爆，然後在下一輪又同時湧回來 —— 這個尖峰會自我維持。加了 ±⅓ 的隨機偏移就把負載攤平了。

### Expedite：插隊通道

`WorkflowExecutorOps.java:1809`

```java
private void expediteLazyWorkflowEvaluation(String workflowId) {
    if (queueDAO.containsMessage(DECIDER_QUEUE, workflowId))
        queueDAO.postpone(DECIDER_QUEUE, workflowId, EXPEDITED_PRIORITY, 0);  // 優先度 10、延遲 0
    else
        queueDAO.push(DECIDER_QUEUE, workflowId, EXPEDITED_PRIORITY, 0);
}
```

當某個事件確定需要立刻重新評估（例如 sub-workflow 剛結束、父層需要繼續往下走），就把訊息的隱形時間歸零、優先度拉到 `EXPEDITED_PRIORITY = 10`，讓它在下一輪 pop 就被撈到 —— 不用乾等 unack 自然到期。這是在「時間驅動」機制上開的一個「事件驅動」後門。

---

## 把兩者串起來走一遍

假設 workflow 是 `taskA → taskB`：

**1. startWorkflow**（事件驅動）
`ExecutionDAOFacade.createWorkflow()` 寫入資料庫，並 `push` 一則訊息到 `_deciderQueue`（延遲 30 秒）。接著直接呼叫 `decide()`：DeciderService 發現沒有任何未處理 task → `startWorkflow()` → 排出 taskA。Ops 把 taskA 以 `SCHEDULED` 寫入資料庫，並推進 taskA 的佇列。

**2. worker 領走 taskA**（事件驅動）
worker poll 到 taskA，回報 `IN_PROGRESS`。

**3. Sweeper 醒來看一眼**（時間驅動）
`sweep()`：repair 檢查沒問題 → decide 跑完發現沒有任何變化 → `unack(responseTimeout + 1)`。這一輪什麼也沒改變，但它確認了「這個 workflow 還活著」，並精準訂好下次該來的時間。

**4. worker 回報 taskA COMPLETED**（事件驅動）
`updateTask` → `decide()`：DeciderService 看到 taskA 進入終止狀態 → 標記 `executed` → `getNextTask()` 找出 taskB → 排程並推進佇列。

**5. taskB 完成**（事件驅動）
`decide()`：沒有東西可排了，`checkForWorkflowCompletion()` 通過 → `isComplete = true` → `endExecution()` → workflow 變成 `COMPLETED`。

**6. Sweeper 最後一次醒來**（時間驅動）
`status.isTerminal()` → `queueDAO.remove(DECIDER_QUEUE, workflowId)`。訊息從此消失，這個 workflow 再也不會被掃到。

> **那如果第 4 步的 worker 掛了呢？**
> 那個事件永遠不會到來，第 4、5、6 步都不會發生。但 Sweeper 會在第 3 步算好的 `responseTimeout + 1` 秒後準時醒來，Decider 的 `isResponseTimedOut()`（`DeciderService.java:785`）判定逾時 → 標記 `TIMED_OUT` → 依設定觸發 retry，或讓 workflow 失敗。
> **這一句就是 Sweeper 全部的價值。**

---

## 與 archive listener 的交互

設定 `conductor.workflow-status-listener.type=archive`（且 workflow def 有 `workflowStatusListenerEnabled: true`）之後，歸檔與前面講的 decide / sweep 是**雙向耦合**的 —— 不只 sweeper 會碰到已歸檔的 workflow，歸檔本身就跑在 `decide()` 裡面。

> 相關的問題分析見 `archive-listener-analysis.md` 與 `tomcat-thread-exhaustion-analysis.md`。本節只講機制上的交互點。

### 1. archive 是 decide() 的一部分，不是背景工作

完整呼叫鏈，全部同步、全程持著 execution lock：

```
decide(workflowId)                              WorkflowExecutorOps.java:1021  ← 取鎖
  └ decide(workflow)                                                    :1049
      └ endExecution()                                                  :1063
          └ completeWorkflow()                                       :492/:495
              └ workflowStatusListener.onWorkflowCompletedIfEnabled()    :550
                  └ ArchivingWorkflowStatusListener.onWorkflowCompleted()
                      └ executionDAOFacade.removeWorkflow(id, true)      :338
```

所以整份歸檔 —— MariaDB 刪 workflow + 每個 task 各自一個 transaction、ES 寫 `rawJSON`、每個 task 一次 ES update、每個 task 一次 Redis remove、最後 `_deciderQueue` remove —— **全部發生在 `decide()` 內部**。對一個有 N 個 task 的 workflow，成本是 `1 + N` 個 DB transaction、`1 + N` 次 ES 寫入、`N + 1` 次 Redis 操作。

這條路徑有兩個入口，後果不同：

| 入口 | 執行緒 | 後果 |
|---|---|---|
| worker 的 `POST /api/tasks` → `updateTask` → `:885 decide()` | Tomcat `http-nio` | 歸檔的所有 I/O 疊在同一次 HTTP 請求內 |
| Sweeper → `WorkflowSweeper.java:94 decide()` | sweeper pool（`CPU × 2`） | `WorkflowReconciler.java:77` 的 `.get()` 是屏障，一次慢歸檔拖慢整批 sweep |

**診斷陷阱**：`Monitors.recordWorkflowDecisionTime`（`WorkflowSweeper.java:95`、`WorkflowExecutorOps.java:1039`）把歸檔時間算進 `workflow_decision` 指標。這個指標變長時不一定是編排慢。

### 2. `_deciderQueue` 的清除是歸檔的最後一步

`ExecutionDAOFacade.java:338-378` 的順序：

```
:341  executionDAO.removeWorkflow()          ← DB 沒了
:343  removeWorkflowIndex()                  ← 可拋 TransientException
:348  for each task: removeTaskIndex()       ← 可拋 TransientException
:374  queueDAO.remove(DECIDER_QUEUE, id)     ← 最後才清
```

兩個後果：

- **窗口期**：`:341` 到 `:374` 之間，DB 已無此 workflow，但 workflowId 還在 `_deciderQueue`。窗口長度 ≈ 1 次 ES 寫入 + N×(ES update + Redis remove)，task 多或 ES 慢時可達秒級。
- **例外殘留**：`:343` 或 `:352` 一旦拋出（`:345`、`:354` 都是 `TransientException`），`:374` 永遠不會執行 → **workflowId 永久留在 `_deciderQueue`**。`ArchivingWorkflowStatusListener` 沒有 try/catch，例外會一路往上拋穿 `completeWorkflow` → `decide()`。

### 3. 順序陷阱：完成路徑會讓 task 復活

```java
// WorkflowExecutorOps.java:465-498  endExecution()
workflow = completeWorkflow(workflow);   // :495 → :550 → 歸檔 → DB 刪光
cancelNonTerminalTasks(workflow);        // :497 → :1205 executionDAOFacade.updateTask(task)
```

**歸檔在前，`cancelNonTerminalTasks` 在後。** `:1205` 的 `updateTask` 打在剛被 `:341` 刪掉的列上，而 MySQL 的 task 寫入有 insert fallback（`MySQLExecutionDAO.java:703-727`）→ `task` 與 `workflow_to_task` 被重建；同時間沒有任何對 `workflow` 表的寫入，該列維持消失。

終止路徑的順序是反的，所以不受影響：

| 路徑 | 順序 | 是否會復活 |
|---|---|---|
| `endExecution` / 完成 | `:495` 歸檔 → `:497` cancelNonTerminalTasks | **會** |
| `terminateWorkflow` / 終止 | `:698` cancelNonTerminalTasks → `:699` 歸檔 | 不會（歸檔時 task 已全部終態） |

最典型的觸發情境是 workflow 裡有 `TERMINATE` task —— 它讓 workflow 提早完成，兄弟 task 還在跑，`cancelNonTerminalTasks` 就有東西可取消。**判別訊號：孤兒 task 的 status 集中在 `CANCELED`。**

### 4. sweeper 的 ES fallback：撈得回來，但改不了東西

`WorkflowSweeper.java:87` 讀 workflow 走的是 `getWorkflowModelFromDataStore`（`ExecutionDAOFacade.java:156`）：

```java
WorkflowModel workflow = executionDAO.getWorkflow(workflowId, includeTasks);
if (workflow == null) {
    String json = indexDAO.get(workflowId, RAW_JSON_FIELD);   // :160  ← 從 ES 還原
    if (json == null) { throw new NotFoundException(...); }   // :164  ← 只有 ES 也沒有才拋
    workflow = objectMapper.readValue(json, WorkflowModel.class);
}
```

所以在第 2 點的窗口期或殘留情況下，sweeper 會**從 ES 的 `rawJSON` 完整還原一個已刪除的 workflow，不拋 `NotFoundException`**，於是不走 `WorkflowSweeper.java:100` 的清理分支，而是真的對它跑完一次 `decide()`。

不過它改不了什麼：`decide` 對終態 workflow 只會呼叫 `cancelNonTerminalTasks`（`WorkflowExecutorOps.java:1050-1054`，且限不成功的 workflow），而該方法只對**非終態**的 task 呼叫 `updateTask`（`:1178`）—— 歸檔時 task 通常已全部終態，迴圈是空的。

實際代價是**一次同步 ES 查詢 + 一次白跑的 decide**，然後在 `:97` 把訊息從佇列清掉。歸檔量大時，這些 ES 查詢會直接吃掉 sweeper 執行緒與 ES RestClient 連線。

### 5. SUB_WORKFLOW：expedite 會把已歸檔的父 workflow 塞回佇列

子 workflow 結束時（`WorkflowExecutorOps.java:648-656`）：

```java
if (workflow.hasParent()) {
    updateParentWorkflowTask(workflow);                              // :1790 → :1794 updateTask
    expediteLazyWorkflowEvaluation(workflow.getParentWorkflowId());  // :655
}
```

而 `expediteLazyWorkflowEvaluation`（`:1809`）：

```java
if (queueDAO.containsMessage(DECIDER_QUEUE, workflowId))
    queueDAO.postpone(...);
else
    queueDAO.push(DECIDER_QUEUE, workflowId, EXPEDITED_PRIORITY, 0);   // ← 父已歸檔 → 走這裡
```

父 workflow 若已歸檔，訊息早被 `:374` 清掉 → `containsMessage` 為 false → **直接 push 回去**。一個 DB 裡不存在的 workflow 就這樣回到 decider queue，讓 sweeper 去撈 ES。同時 `:1794` 的 `updateTask` 會讓父的 `SUB_WORKFLOW` task 列復活。

`:320`（retry / rerun 的 `updateAndPushParents`）更嚴重：先 `getWorkflowModel(parentWorkflowId, true)`（走 ES fallback）、把狀態設成 `RUNNING`、`updateWorkflow` 寫回（MySQL 純 UPDATE，命中 0 列，workflow 表仍是空的），然後 expedite —— 結果是一個 DB 裡不存在、ES 裡狀態卻是 RUNNING 的殭屍條目留在 decider queue。

**判別訊號：孤兒 task 的 `task_type` 集中在 `SUB_WORKFLOW`。** 與第 3 點的訊號可以並存。

### 6. 警告：archive 開啟時不要打開 repair service

`WorkflowSweeper.java:89-91` 是在 `decide()` **之前**跑 repair 的：

```java
if (workflowRepairService != null) {
    workflowRepairService.verifyAndRepairWorkflowTasks(workflow);   // :91
}
```

對一個從 ES `rawJSON` 還原的已歸檔 workflow：

- `verifyAndRepairTask`（`WorkflowRepairService.java:141-153`）會把 `SCHEDULED` 的 task **重新 push 回 task queue** → worker 領到一個 DB 裡不存在的 task
- `:119` 的 `verifyAndRepairWorkflow(parentWorkflowId)` 會把父 workflow **重新 push 回 `_deciderQueue`**（`:174`）

**repair service 的職責是「讓 queue 追上 DB」，archive 的職責是「讓 DB 消失」，兩者的假設直接衝突。** 在 archive 開啟時打開 repair，會把第 2、5 點的殘留從偶發變成系統性重新製造。它預設是關的（`conductor.workflow-repair-service.enabled=false`），保持這樣。

### 如何觀測

| 想看什麼 | 指標 | 出處 |
|---|---|---|
| 歸檔速率 | `workflow_archived_total{workflowName, workflowStatus}` | `Monitors.java:563` |
| **歸檔的 ES 成本（最有用）** | `update_workflow{docType="workflow"}`、`update_task` timer | `ElasticSearchRestDAOV7.java:869`、`:950` |
| ES 歸檔錯誤 | `workflow_server_error_total{class="ElasticSearchRestDAOV7", methodName="update"}` | ES DAO `:955` |
| sweeper 是否跟得上 | `_deciderQueue` gauge | `WorkflowReconciler.java:96-97` |

缺口有三個，排查時要知道：`mysql-persistence` 完全沒有 `dao_requests` / `dao_payload_size` 埋點（只有 redis 與 cassandra 有），所以 MariaDB 側的歸檔負載在 conductor 指標裡不可見；Jedis 連線池沒有任何 micrometer binding；`ExecutionDAOFacade.removeWorkflow`（`:338`）主路徑**沒有任何 error metric**（`recordDaoError` 只在 TTL 版的 `:411`），歸檔失敗只留 log。

### 緩解方向

把歸檔從 `decide()` 的呼叫堆疊裡搬出去，用延遲版 listener：

```properties
conductor.workflow-status-listener.archival.ttlDuration=1s
conductor.workflow-status-listener.archival.delaySeconds=90
```

`ttlDuration > 0` 只是用來讓 `ArchivingWorkflowListenerConfiguration.java:31` 選到 `ArchivingWithTTLWorkflowStatusListener`；真正生效的是 `delaySeconds`，它走 `ScheduledExecutorService`（`ArchivingWithTTLWorkflowStatusListener.java:83-90`），並且把 `removeWorkflow` 包在 try/catch 裡（`:124-134`）。一次解掉三件事：decide 不再背負歸檔 I/O、第 3 與 5 點的遲到寫入有時間先落地、歸檔例外不再往上拋穿 `decide()`。副作用是 `workflow_archival_delay_queue_size` gauge 開始有值，要盯它會不會積壓。

---

## 設定參數

`ConductorProperties` 的 prefix 是 `conductor.app`。

| Property | 預設值 | 作用 |
|---|---|---|
| `conductor.sweep-frequency.millis` | `500` | Reconciler 兩輪之間的間隔 |
| `conductor.app.sweeper-thread-count` | `CPU × 2` | 每輪撈幾個 workflow，也是執行緒池大小 |
| `conductor.app.sweeper-workflow-poll-timeout` | `2000ms` | 從佇列 pop 時的阻塞等待時間 |
| `conductor.app.workflow-offset-timeout` | `30s` | 沒有更好資訊時的預設重掃間隔（jitter 基準） |
| `conductor.app.max-postpone-duration-seconds` | `3600s` | unack 延後的上限 |
| `conductor.workflow-reconciler.enabled` | `true` | 關掉等於整個 Sweeper 停擺 |
| `conductor.workflow-repair-service.enabled` | `false` | 需要佇列實作支援 `containsMessage()` |
| `conductor.app.workflow-execution-lock-enabled` | `false` | 多節點部署才需要打開 |

調校時最直接的觀察指標是 `WorkflowReconciler.recordQueueDepth()`（`:95`）打出的 `_deciderQueue` 佇列深度。它持續上升代表 sweeper 吃不消 —— 要嘛加 `sweeperThreadCount`，要嘛加節點。

---

## 三個常見誤解

**✕「Sweeper 每 30 秒把所有 workflow 掃一遍。」**
不是。它是一個佇列消費者，每個 workflow 的*下次*檢查時間是根據它當下在等什麼**個別計算**出來的（`unack()`）。等 2 小時的 workflow 就真的 2 小時不會被碰。

**✕「Decider 是一個常駐執行緒。」**
不是。`DeciderService` 是無狀態的純函式，被多個入口呼叫：worker 回報 task、REST `PUT /workflow/{id}/decide`（`WorkflowServiceImpl.java:241`）、retry / rerun / restart，以及 Sweeper。**常駐執行緒是 Sweeper，不是 Decider。**

**✕「一次 decide 只會推進一步。」**
不是。`WorkflowExecutorOps.java:1094` 有遞迴 —— 只要狀態有變就再 decide 一次。所以一串同步的系統 task 會在同一次呼叫裡全部跑完，中間不會回到佇列。

---

## 接下來讀什麼

- `core/src/test/java/.../reconciliation/TestWorkflowSweeper.java` —— `unack()` 各分支的測試，建立直覺最快的路徑
- `core/src/test/java/.../execution/TestDeciderOutcomes.java` —— 各種 workflow 結構下 Decider 的輸出長什麼樣
- `core/.../execution/mapper/` —— 每種 task type 如何從 definition 映射成實際 task，是 `getNextTask()` 的下游
- `core/.../execution/AsyncSystemTaskExecutor.java` —— 非同步系統 task（`SUB_WORKFLOW`、`HTTP`）走的是另一條與 Sweeper 平行的迴圈
- `workflow-event-listener/.../listener/archive/` —— 歸檔的三種 listener 實作，對照上面「與 archive listener 的交互」一節
