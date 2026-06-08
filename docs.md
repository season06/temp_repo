# monitor.py 架構說明

本文件用「架構圖 + 情境帶入」的方式說明 `monitor.py` 的執行邏輯。

情境:2 個 release 同時監控
- **release-1**:佇列有 2 個任務 `task-a1`、`task-a2`(依序觸發,無依賴)
- **release-2**:佇列只有 1 個任務 `task-b1`,但觸發後會 cascade 出依賴任務 `task-b2`(`task-b1 → task-b2`)

---

## 1. 整體架構(asyncio 並發模型)

`run_orchestration()` 用 `asyncio.gather` 同時跑「每個 release 一條 runner 協程」+「一條 render 協程」,共享一份 `tasks` 字典:

```
                      run_orchestration(runners, tasks, api, writer)
                                       │  asyncio.gather
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                               ▼                              ▼
┌────────────────┐            ┌────────────────┐            ┌────────────────────┐
│ ReleaseRunner  │            │ ReleaseRunner  │            │   render_loop()    │
│   release-1    │            │   release-2    │            │  每 2s 重畫一次     │
│ queue:[a1,a2]  │            │ queue:[b1]     │            └─────────┬──────────┘
│ active / done  │            │ active / done  │                      │
└───────┬────────┘            └───────┬────────┘                      │ 讀取
        │ 讀寫                         │ 讀寫                          │
        └──────────────┬──────────────┴──────────────┬───────────────┘
                       ▼                              ▼
              ┌───────────────────────────────────────────────┐
              │   tasks: dict[int, Task]   (共享狀態,無鎖)     │
              │   單執行緒 asyncio,await 才會切換,故安全       │
              └───────────────────────────────────────────────┘
                       │ 透過 api 介面 (seam)
                       ▼
              MockApi (mock_api.json)  /  AzureApi (Azure REST)
```

關鍵點:
- **一個 release = 一條協程**,彼此用 `await` 真正並行。
- **render 是獨立心跳**,不跟 runner 協調,固定 2 秒重畫。
- **seam 介面**只有兩個方法:`trigger_task(release_id, task_id)`、`get_task_info(release_id, task_id, task_name)`,可在 `MockApi` 與 `AzureApi` 間替換。

---

## 2. 單一 runner 內部的呼叫鏈

```
ReleaseRunner.run(tasks, api)
  └─ for name in trigger_queue:               # 佇列「依序」處理
       ├─ tid = _resolve_name(name)
       ├─ api.trigger_task(release_id, tid)   # 觸發(失敗→標 Error,跳下一個)
       └─ _wait_chain_terminal(tid, tasks, api)
            └─ while not chain_terminal(tid):  # 一直輪詢直到整條鏈 terminal
                 ├─ _poll_chain(tid, tasks, api)
                 │    └─ poll_task(task, release_id, api)   # 對 root + 已知 dep 各輪詢一次
                 │         └─ fetch_task_update(api, ...)   # 包 try/except→Error
                 │              └─ api.get_task_info(...)    # 回傳 status + dependency_*
                 │         └─ 若發現新 dependency → 加進 tasks,納入輪詢
                 └─ asyncio.sleep(2)
```

`chain_terminal` 會沿著 `root → dependency → dependency …` 整條走,**全部**都在終止狀態
(`TERMINATE_STATUSES`,例如 `succeeded / failed / canceled`)才算 terminal,才能換下一個佇列任務。

---

## 3. 兩種「等待」的差異

| release | trigger_queue | 依賴關係 | 等待的原因 |
|---|---|---|---|
| release-1 (rid=1) | `[task-a1, task-a2]` | 無 | **佇列序列化**:a1 整條 terminal 後才觸發 a2 |
| release-2 (rid=2) | `[task-b1]` | `task-b1 → task-b2` | **依賴序列化**:佇列只有 b1,但 cascade 出的 b2 也要等到 terminal |

假設 id:`task-a1=11, task-a2=12, task-b1=21, task-b2=22`。

---

## 4. 並發時間軸

```
時間 ──────────────────────────────────────────────────────────────▶

release-1 runner:
  T0  trigger a1 ──▶ 輪詢 a1 ......................... a1=Succeeded
  T3                                                   trigger a2 ──▶ 輪詢 ... a2=Succeeded ─▶ done
                    └ a1 terminal 後才觸發 a2(queue 序列化)

release-2 runner:   (與 release-1 同時進行)
  T0  trigger b1 ──▶ 輪詢 b1 ─▶ get_task_info 回傳 dependency=b2
                     發現 b2 → 加進 tasks,一起輪詢
                     等 b1 與 b2「整條鏈」都 terminal ─▶ done
                    └ queue 只有 b1,但 cascade 出的 b2 也要等

render_loop:  每 2s 同時重畫 release-1 + release-2(不管 runner 進度)
```

---

## 5. 終端輸出演進(`render_monitoring` 格式)

**T0** — 兩個 release 各觸發第一個任務:

```
=== release-1 ===
  task-a1 : InProgress ◀ active
  task-a2 : Pending
=== release-2 ===
  task-b1 : InProgress ◀ active
    |_task-b2 : InProgress        ← 輪詢 b1 時發現的 cascade,縮排展開
```

**T1** — release-1 的 a1 完成、換觸發 a2;release-2 的 b1 完成、等 b2:

```
=== release-1 ===
  task-a1 : Succeeded
  task-a2 : InProgress ◀ active   ← a1 整條 terminal 後才換到 a2
=== release-2 ===
  task-b1 : Succeeded ◀ active
    |_task-b2 : InProgress         ← b1 雖完成,但 runner 仍卡在等 b2
```

**T2** — 全部 terminal,兩條 runner 都 done,程式結束:

```
=== release-1 ===
  task-a1 : Succeeded
  task-a2 : Succeeded
=== release-2 ===
  task-b1 : Succeeded
    |_task-b2 : Succeeded
```

---

## 重點整理

- **並行**:release 之間靠 asyncio 協程同時推進;**序列**:單一 release 內的佇列任務一次一個。
- **依賴展開**:dependency 不是事先宣告,而是輪詢 `get_task_info` 時動態發現,加入共享 `tasks` 後一起輪詢與顯示。
- **完成判定**:runner 的某個佇列任務要「root + 整條 cascade 鏈」皆 terminal 才前進;整個程式在所有 runner 都 done 時結束。
- **render 解耦**:畫面是固定 2 秒的獨立心跳,只讀共享狀態,不影響觸發/輪詢邏輯。
