● 我用 5 個輪詢週期帶你走一遍。情境設定:

  - release-1 的 root 是 task-a (id=101)
  - task-a 相依 task-b (id=102)
  - task-b 無相依

  ▎ 註:這支腳本只「觀察」狀態,不負責決定誰先誰後 — 順序由 Azure 端決定,腳本只是每 2 秒去 API 抓快照後重畫畫面。

  ---
  🟢 初始狀態 (進入 main 前)

  tasks = {}                # 唯一的真相來源,空的
  writer = LiveWriter()     # 內部 _previous_line_count = 0

  進迴圈。

  ---
  🔁 Cycle 1 — 兩個都 NotStarted(首次發現 task-b)

  API 回傳:
  - 101 → NotStarted, dep=(102, "task-b")
  - 102 → NotStarted, dep=None
  
  流程:

  1. get_release_info()
     → [Release(id=1, name="release-1", root_task_id=101, root_task_name="task-a")]

  2. poll_active_tasks(releases, tasks)
     ├─ setdefault 101 → 新增 tasks[101] = Task("task-a", status="Waiting")
     ├─ worklist = [task_a]
     │
     ├─ pop task_a:
     │    poll_task(task_a)
     │      ├─ is_terminate("Waiting") → False
     │      ├─ fetch_task_update(101) → TaskUpdate("NotStarted", 102, "task-b")
     │      ├─ task_a.status="NotStarted", dep_id=102, dep_name="task-b"
     │      └─ return Task(102, "task-b")            ← 發現新依賴
     │    new_dep.id=102 不在 tasks → tasks[102] = Task("task-b", "Waiting")
     │    worklist.append(task_b)
     │
     └─ pop task_b:
          poll_task(task_b)
            ├─ fetch_task_update(102) → TaskUpdate("NotStarted", None, None)
            ├─ task_b.status="NotStarted"
            └─ return None

  3. render_monitoring(releases, tasks)
     → "release-1 - task-a : NotStarted"
       "            |_task-b : NotStarted"

  4. writer.write(output)
     → 直接寫(_previous=0),寫完 _previous=2

  5. all_tasks_terminated → False (兩個都 NotStarted)
  6. sleep(2)

  重點:這一輪做了「發現圖」的工作 — task-b 是被 task-a 的 polling 結果帶出來的。

  ---
  🔁 Cycle 2 — task-b 開始進行

  API 回傳:
  - 101 → NotStarted (還被 b 卡住)
  - 102 → InProgress

  poll_active_tasks:
    setdefault 101 → 已存在,略過
    worklist = [task_a, task_b]    ← 來自 tasks.values()

    pop task_b (worklist.pop 是 LIFO):
      fetch → TaskUpdate("InProgress", None, None)
      task_b.status="InProgress"

    pop task_a:
      fetch → TaskUpdate("NotStarted", 102, "task-b")
      task_a.status="NotStarted"  (沒變)
      return Task(102, ...)   ← 102 已在 tasks 中,不入列

  render:
    "release-1 - task-a : NotStarted"
    "            |_task-b : InProgress"

  writer.write:
    _previous=2,送 \x1b[2F 把 cursor 上移 2 行,重畫
    _previous 維持 2

  all_terminated → False

  重點:tasks dict 同時是「已知集合」與「狀態存放處」— 重複發現的 dep 直接被 if new_dep.id not in tasks 擋掉,不需要額外的 polled_tasks set。

  ---
  🔁 Cycle 3 — task-b 完成

  API 回傳:
  - 101 → NotStarted
  - 102 → Successed

  poll_active_tasks:
    pop task_b:
      is_terminate("InProgress") → False
      fetch → TaskUpdate("Successed", None, None)
      task_b.status="Successed"     ← 首次進入終態

    pop task_a:
      fetch → TaskUpdate("NotStarted", 102, "task-b")
      (狀態無變化)

  render:
    "release-1 - task-a : NotStarted"
    "            |_task-b : Successed"

  all_terminated:
    task_a.status="NotStarted" → 非終態 → False

  重點:雖然 task-b 已終態,但 task-a 還沒,整體還不能結束。

  ---
  🔁 Cycle 4 — task-a 開始(b 解鎖了 a)

  API 回傳:
  - 101 → InProgress
  - 102 → Successed

  poll_active_tasks:
    pop task_b:
      is_terminate("Successed") → True   ← 直接 return None,不打 API
      (這就是 poll_task 開頭那個守衛的價值:終態任務不再產生流量)

    pop task_a:
      fetch → TaskUpdate("InProgress", 102, "task-b")
      task_a.status="InProgress"

  render:
    "release-1 - task-a : InProgress"
    "            |_task-b : Successed"

  all_terminated → False (task_a 還在 InProgress)

  重點:poll_task 第一行的 if is_terminate_status(task.status): return None 在這裡省下一次無謂的 API 呼叫。

  ---
  🔁 Cycle 5 — task-a 完成,迴圈結束

  API 回傳:
  - 101 → Successed
  - 102 → Successed

  poll_active_tasks:
    pop task_b: 終態 → skip
    pop task_a:
      fetch → TaskUpdate("Successed", 102, "task-b")
      task_a.status="Successed"     ← 進入終態

  render:
    "release-1 - task-a : Successed"
    "            |_task-b : Successed"

  writer.write → 重畫

  all_tasks_terminated:
    all(is_terminate_status(t.status) for t in tasks.values())
    = all([True, True])
    = True                          ← break!

  main() 結束

  ---
  📊 整體心智模型

                    ┌─────────────────────────────────────┐
                    │  tasks: dict[int, Task]             │
     每 cycle ─────▶│  ├─ 101 (task-a) → dep_id=102       │ ◀───── render 順著
                    │  └─ 102 (task-b) → dep_id=None       │       dep_id 鏈印
                    └─────────────────────────────────────┘
                              ▲
                              │  poll_active_tasks 走訪
                              │  ├─ 終態的 task → skip(省 API)
                              │  └─ 非終態 → fetch + mutate
                              │      └─ 若回傳新 dep → 加入 tasks 並排隊
                              │
                    ┌─────────────────────────────────────┐
                    │  Azure API (mock_api.json)          │
                    └─────────────────────────────────────┘

  每個 cycle 三步:
  1. 走訪 — 對 tasks 內所有非終態 task 各呼叫一次 API
  2. 重畫 — LiveWriter 把上一輪輸出用 ANSI 蓋掉
  3. 檢查結束 — 全終態就 break,否則 sleep 2 秒再來

  整支腳本沒有任何「task A 要等 task B 完成才開始」這種邏輯 — 那是 Azure 那邊的事。腳本純粹當一面鏡子。