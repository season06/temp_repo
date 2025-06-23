四種方法
- for loop
    由於 batch poll 下來的 tasks 狀態會全部被 conductor 標為 "IN_PROGRESS" (開始計算 timeout)，有機會導致順序較後面的 task 執行時間 timeout
- multi-processing
    fork 太多 sub-process，不確定資源與效能對系統的影響
- multi-threading
    由於 CPython 底層實作 (GIL)，multi threads 執行效率仍然會是 single thread
- async

---

待解決問題
- 現有邏輯需判斷哪些邏輯要加 await -> refactor
- 常駐 process 的 mem 持續堆積 -> 定期砍掉 process (1h) / 改善現有程式寫法 (gc, release connection) 
- metrics

---

# multi-processing
www.geeksforgeeks.org/python/multiprocessing-python-set-1/

# Coroutin (Async)
> Coroutines are a more generalized form of subroutines. Subroutines are entered at one point and exited at another point. Coroutines can be entered, exited, and resumed at many different points. They can be implemented with the async def statement.
Coroutine 具有開始(enter)/暫停(exit)以及任意恢復(resume)執行的能力，譬如發出 HTTP Request 之後，就暫停執行該函式，轉而執行其他工作，等到收到伺服器回應之後，再轉回來恢復執行剩下的工作。

[Python asyncio 從不會到上路](https://myapollo.com.tw/blog/begin-to-asyncio/)  
[【Python - asyncio】非同步 I/O 簡介](https://vocus.cc/article/659e97a0fd897800013095e4)  
[async def & await 重點整理](https://ithelp.ithome.com.tw/articles/10262385)  
[Asyncio Vs Threading In Python](https://www.geeksforgeeks.org/python/asyncio-vs-threading-in-python/)  
[Asynchronous HTTP Requests with Python](https://www.geeksforgeeks.org/python/asynchronous-http-requests-with-python/)  

[awaitables | lib](https://docs.python.org/zh-tw/3.13/library/asyncio-task.html#awaitables)  
[asyncio.to_thread | lib](https://docs.python.org/zh-tw/3.13/library/asyncio-task.html#asyncio.to_thread)  

[淺談 GIL & Thread-safe & Atomic operation](https://www.maxlist.xyz/2020/03/15/gil-thread-safe-atomic/)  

- `asyncio.gather()` 同時運行兩個 function，並等待兩個函數都執行完畢才繼續  

- TODO 
    測試 DBClient  
    測試 http  
    測試 to_thread  
    如何確認真的有併發處理  