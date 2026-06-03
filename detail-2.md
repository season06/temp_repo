  🟢 啟動階段

  async def main():
      releases = await get_release_metadata()    # 從 mock 讀 release pipeline 結構
      runners = [
          ReleaseRunner.from_input("release-1", ["task-a", "task-c"], releases),
          ReleaseRunner.from_input("release-2", ["task-1"],          releases),
      ]
      tasks: dict = {}
      writer = LiveWriter()
      print("===Start===")

      await asyncio.gather(
          runner1.run(tasks),    # ─┐
          runner2.run(tasks),    # ─┼─ 3 個 coroutine 並行
          render_loop(...),      # ─┘
      )

  asyncio.gather 把 3 個 coroutine 一起丟進 event loop。asyncio 是單執行緒 — 它們不會真的「同時跑」,而是在每個 await 點切換。共享的 tasks dict 因此不需要 lock。

  ---
  🔁 T0 — 兩個 runner 同時進入各自的 queue 迴圈

  兩個 runner 互相不知道對方存在。各自跑:

  # runner1
  for name in ["task-a", "task-c"]:
      tid = self._resolve_name(name)        # task-a → 101
      self.active_root_id = 101
      self.triggered.append(101)
      tasks[101] = Task(id=101, name="task-a")
      await trigger_task(101)               # ◀ yield 點:寫 mock_api.json
      ...

  # runner2
  for name in ["task-1"]:
      tid = self._resolve_name(name)        # task-1 → 301
      self.active_root_id = 301
      self.triggered.append(301)
      tasks[301] = Task(id=301, name="task-1")
      await trigger_task(301)               # ◀ yield 點
      ...

  event loop 微觀順序:

  1. runner1 跑到 `await trigger_task(101)` → yield
  2. runner2 跑到 `await trigger_task(301)` → yield
  3. render_loop 跑第一次 render → 印出 → `await sleep(2)` → yield
  4. trigger_task(101) 完成(寫檔) → runner1 進入 _wait_chain_terminal
  5. trigger_task(301) 完成 → runner2 進入 _wait_chain_terminal

  第一次 render 的瞬間,兩個 runner 都剛 setdefault 完 task 但還沒 poll:

  === release-1 ===
    task-a : Waiting ◀ active
    task-c : Pending
  === release-2 ===
    task-1 : Waiting ◀ active

  ---
  🔁 T+2s — 第一輪 poll(兩個 runner 同時)
  
  兩個 runner 各自進入 _wait_chain_terminal → _poll_chain 迴圈。

  runner1._poll_chain(101, tasks):

  worklist = [tasks[101]]   # task-a
  seen = {}

  pop task-a:
    await poll_task(task-a)
      └─ fetch_task_update(101) → {status=InProgress, dep_id=102, dep_name="task-b"}
         (status=InProgress 是因為剛剛 trigger_task 寫的)
      └─ 寫入 task-a: status=InProgress, dep_id=102, dep_name="task-b"
      └─ return Task(102, "task-b")     ← 發現 cascade
    new_dep.id=102 不在 tasks
    └─ tasks[102] = Task(102, "task-b", status="Waiting")
    └─ worklist.append(tasks[102])

  pop task-b:
    await poll_task(task-b)
      └─ fetch_task_update(102) → {status=NotStarted, dep_id=null, ...}
         (task-b 還沒被 trigger,所以還是 NotStarted)
      └─ 寫入 task-b: status=NotStarted
      └─ return None

  runner2._poll_chain(301, tasks):

  worklist = [tasks[301]]

  pop task-1:
    await poll_task(task-1)
      └─ fetch_task_update(301) → {status=InProgress, dep_id=null, ...}
      └─ 寫入 task-1: status=InProgress
      └─ return None

  兩個 runner 都檢查 chain_terminal,都還沒終態 → await sleep(2) 等下一輪。

  render_loop 也醒來重畫:

  === release-1 ===
    task-a : InProgress ◀ active
      |_task-b : NotStarted
  === release-2 ===
    task-1 : InProgress ◀ active

  ▎ 注意:此時兩個 runner 共寫 tasks dict,但因為每個 runner 只操作自己 release 的 task id(101/102 vs 301),不會衝突。render 讀 dict 也是安全的 — asyncio 單執行緒,沒有讀到一半被打斷的可能。

  ---
  🔁 T+4s ... 持續 poll(假設 Azure 端逐步推進)
  
  T+4s: task-a 開始實際跑 → mock_api 改 task-a = "InProgress" (沒變化)
         task-1 還 InProgress
         畫面不變

  T+8s: task-a 完成 → mock_api 改 task-a = "Successed"
                      task-b 開始(Azure 自動 cascade) = "InProgress"

    runner1._poll_chain:
      pop task-a:
        poll_task → status="Successed" (terminal,但是上一輪 task.status 還是 InProgress,
                                         所以 poll_task 不會 skip,會 fetch 並更新)
                    dep_id=102 in tasks → 走 elif branch,把 task-b 加進 worklist
      pop task-b:
        poll_task → status="InProgress"
    chain_terminal(101): task-a Successed → task-b InProgress (非終態) → False ❌
    繼續等。

    runner2 此時可能還在 polling 301。

  render:
  === release-1 ===
    task-a : Successed ◀ active           ← 仍然 active,因為 b 還沒完
      |_task-b : InProgress
  === release-2 ===
    task-1 : InProgress ◀ active

  ---
  🔁 T+12s — runner1 的 cascade 完成,推進 queue

  mock_api 改 task-b = "Successed"

  runner1._poll_chain:
    pop task-a: status="Successed",這次 is_terminate_status("Successed")=True → return None
                (省 1 次 API call)
                但 elif: task.dependency_id=102 in tasks → 把 task-b 加 worklist
    pop task-b: poll_task → status="Successed"
  chain_terminal(101): a Successed → b Successed → 鏈尾 → True ✅

  跳出 _wait_chain_terminal,active_root_id = None
  回到 for 迴圈下一輪:

    name = "task-c"
    tid = 201
    active_root_id = 201
    triggered = [101, 201]
    tasks[201] = Task(201, "task-c", "Waiting")
    await trigger_task(201)           ← mock_api: task-c = "InProgress"
    _wait_chain_terminal(201):
      poll_chain → tasks[201].status = "InProgress", no dep
      chain_terminal(201) → False (InProgress 非終態)
      sleep(2)

  render(可能在 task-c trigger 之後立刻發生):
  === release-1 ===
    task-a : Successed              ← 不再有 active marker
      |_task-b : Successed
    task-c : InProgress ◀ active   ← 新 active
  === release-2 ===
    task-1 : InProgress ◀ active

  ---
  🔁 T+18s — runner2 先完成

  mock_api 改 task-1 = "Successed"

  runner2._poll_chain(301):
    poll task-1 → Successed
  chain_terminal(301) → True
  跳出 _wait_chain_terminal
  active_root_id = None
  for 迴圈跑完(只有一個 item)
  self._done = True               ← runner2 整個結束

  但 main 的 asyncio.gather 還在等其他 coroutine(runner1 + render_loop)
  runner2.run() 的 coroutine 從 event loop 移除,不再消耗 CPU/IO。

  render:
  === release-1 ===
    task-a : Successed
      |_task-b : Successed
    task-c : InProgress ◀ active
  === release-2 ===
    task-1 : Successed              ← 沒 active marker(_done=True)

  render_loop 的 while not all(r.is_done() for r in runners) 還是 True(因為 runner1 未完成),繼續每 2 秒重畫。

  ---
  🔁 T+22s — runner1 也完成,整個程式結束

  mock_api 改 task-c = "Successed"

  runner1._poll_chain(201):
    poll task-c → Successed
  chain_terminal(201) → True
  for 迴圈跑完(原本 ["task-a", "task-c"])
  self._done = True

  render_loop 下一次醒來:
    all(r.is_done() for r in runners) = True
    跳出 while
    寫最後一次 render(final paint)
    return

  asyncio.gather 收齊 3 個 coroutine 完成
  main() return
  asyncio.run() 結束 → 程式退出

  最終畫面:
  === release-1 ===
    task-a : Successed
      |_task-b : Successed
    task-c : Successed
  === release-2 ===
    task-1 : Successed

  ---
  📊 心智模型總結

  ┌─────────────────────────────────────────────────────────────┐
  │                  asyncio event loop (單執行緒)               │
  │                                                              │
  │  Coroutine A: runner1.run                                    │
  │    ├─ [trigger task-a] await ──┐                             │
  │    ├─ poll a+b until terminal  │                             │
  │    ├─ [trigger task-c] await ──┤  每個 await = yield 點      │
  │    └─ poll c until terminal    │                             │
  │                                │                             │
  │  Coroutine B: runner2.run      │  ◀── event loop 在這些     │
  │    ├─ [trigger task-1] await ──┤      yield 點之間切換       │
  │    └─ poll until terminal      │                             │
  │                                │                             │
  │  Coroutine C: render_loop      │                             │
  │    └─ write & sleep(2) 迴圈 ───┘                             │
  │                                                              │
  │              ▼ 共寫共讀                                       │
  │  ┌────────────────────────────────────────┐                  │
  │  │  tasks: dict[int, Task]                 │                  │
  │  │  {101:..., 102:..., 201:..., 301:...}  │                  │
  │  └────────────────────────────────────────┘                  │
  └─────────────────────────────────────────────────────────────┘

  關鍵特性:

  ┌───────────────────┬──────────────────────────────────────────────────────────────────────────────────────┐
  │       屬性        │                                         行為                                         │
  ├───────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ 同一 release 內   │ 序列 — run() 是 for name in queue:,一定先做完上一個才換下一個                        │
  ├───────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ 不同 release 之間 │ 並行 — 它們是獨立 coroutine,各自的 sleep 不會擋到對方                                │
  ├───────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ 共享 tasks dict   │ 安全 — asyncio 單執行緒,每個 dict 操作是原子的                                       │
  ├───────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ 終態判斷          │ 每個 runner 各自判斷 chain_terminal(self.active_root_id);整體結束 = all(r.is_done()) │
  ├───────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ Render            │ 完全獨立 — 不關心 runner 在做什麼,2 秒重畫一次當下的 tasks 與 runners 狀態           │
  └───────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘

  兩個 release 的「快慢」不會互相拖累 — runner2 跑得快、3 步就完成的話,runner1 還在等 cascade 的時候 runner2 已經 _done=True,從 event loop 退出,把 CPU 還給其他 coroutine。