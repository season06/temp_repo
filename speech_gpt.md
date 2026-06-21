## Slide 1｜Title：自建 Monitor Stack 介紹

**時間：30 秒**

各位主管好，今天會用 10 分鐘介紹我們團隊目前自建的 Monitor Stack。

這套系統的目標很單純：讓我們能更快發現問題、更快定位問題，並且降低維運人員在查案時的時間成本。

今天會分成四個部分：背景、架構、目前已完成的優化，以及未來規劃。

## Slide 2｜Background：為什麼需要自建 Monitor Stack？

**時間：1 分鐘 10 秒**

**投影片重點：**

* 原本組織已有 One Defense，可透過 SQL Query 產生監控指標
* One Defense 適合資料庫型、結果型監控
* 但對即時系統狀態、服務健康度、Kubernetes、Airflow、Conductor 等監控較有限
* 因此逐步導入 Prometheus-based Monitor Stack

**逐字稿：**

在背景上，組織原本其實已經有一套監控系統，也就是 One Defense。

One Defense 的優點是，它可以透過 SQL Query，把資料庫中的資料轉換成監控指標。對於一些已經落在資料表裡的業務資料、交易結果、批次結果，它是非常有價值的。

但是隨著我們系統越來越複雜，只看資料庫結果會有一些限制。

例如服務本身是不是健康、Pod 有沒有重啟、CPU 或 Memory 是否異常、Airflow Scheduler 是否卡住、Conductor Worker 是否處理變慢，這些狀態不一定會完整反映在 SQL 資料裡。

也就是說，One Defense 比較像是看「結果」，但我們還需要一套系統來看「過程」與「即時狀態」。

因此，我們逐步將部分監控移轉到以 Prometheus 為核心的 Monitor Stack，補足原本 SQL-based monitoring 看不到的面向。

---

## Slide 3｜Architecture：整體監控架構

**時間：1 分鐘 30 秒**

**投影片重點：**

* 支援兩個產品線：ISOP、TX
* 自建 Monitor Stack：

  * Prometheus：收集 Metrics
  * AlertManager：告警通知
  * Grafana：視覺化 Dashboard
  * ElasticSearch：儲存 Log
  * Kibana：查詢與分析 Log
* 組織既有監控：

  * One Defense：透過 SQL Query 產生指標
* 兩者互補，而非互相取代

**逐字稿：**

這一頁是整體架構。

目前我們的 Monitor Stack 設計上，是希望可以同時支援兩個產品線，也就是 ISOP 和 TX。

整體上可以分成兩塊。

第一塊是我們團隊自建的 Monitor Stack。Prometheus 負責收集各系統的 Metrics，例如 Kubernetes、Airflow、Conductor，以及服務本身暴露出來的指標。

當 Metrics 達到異常條件時，會透過 AlertManager 發送告警，讓維運同仁可以第一時間收到通知。

Grafana 則負責把這些指標視覺化，讓我們可以透過 Dashboard 快速看到系統健康度、趨勢與異常點。

另外，Log 的部分會進到 ElasticSearch，並透過 Kibana 進行查詢與分析。這主要用在問題發生後，需要往下追細節的情境。

第二塊是組織既有的 One Defense。One Defense 仍然保留它的價值，特別是在 SQL Query 能夠直接反映業務資料或交易結果的場景。

所以我們現在的方向不是用 Prometheus 取代 One Defense，而是讓兩套系統互補。

One Defense 偏向資料結果監控，Prometheus Stack 偏向系統狀態、即時指標與服務健康度監控。兩者結合後，整體監控覆蓋率會更完整。

---

## Slide 4｜Pain Points：維運 Monitor Stack 遇到的痛點

**時間：1 分鐘 20 秒**

**投影片重點：**

* 環境多，Dashboard 分散，切換成本高
* Plain text log 缺少結構化資訊，查案成本高
* SQL 指標無法涵蓋所有系統健康狀態
* 告警與 Dashboard 需要逐步標準化
* 維運人員需要在多個工具之間來回查詢

**逐字稿：**

在實際維運 Monitor Stack 的過程中，我們也遇到不少痛點。

第一個痛點是環境很多。過去不同環境各自有 Grafana，總共有 14 個環境需要維護。這會帶來兩個問題：一個是維護成本高，另一個是查問題時需要一直切換入口。

第二個痛點是 Log 原本多數是 plain text 格式。plain text 雖然人可以讀，但在查案時比較難快速過濾條件，例如 workflow id、task id、request id、狀態碼、產品線、Fab 或 namespace。這會讓工程師花很多時間在人工比對。

第三個痛點是 SQL-based 指標的限制。只用 SQL 很難掌握即時服務狀態，例如 Pod 是否重啟、Thread 是否接近滿載、Airflow DAG 是否延遲、Conductor Worker 是否 timeout。

第四個痛點是告警與 Dashboard 需要逐步標準化。當指標來源越來越多，如果沒有整理，很容易變成「有很多資料，但不容易判斷重點」。

所以這一階段，我們主要做的事情，就是降低查案成本、降低維運成本，並提高監控資料的可讀性。

---

## Slide 5｜Optimization 1：Grafana Centralize

**時間：1 分鐘 20 秒**

**投影片重點：**

* 原本：14 個環境，各自一座 Grafana
* 現在：集中 Data Source，整合成一座主要 Grafana
* 效益：

  * 降低 Grafana 維運成本
  * 減少查案時切換環境的時間
  * Dashboard 管理更一致
  * 管理層與維運團隊可以共用同一個觀察入口

**逐字稿：**

第一個已經完成的優化，是 Grafana Centralize。

過去我們有 14 個環境，每個環境都有自己的 Grafana。這代表我們在查問題時，常常要先確認問題在哪個環境，再切到對應的 Grafana，才能開始看 Dashboard。

對維運來說，這增加了切換成本。對 Dashboard 管理來說，也代表同樣的 Dashboard 可能要在多個地方維護，容易出現版本不一致。

因此我們做了 Grafana 集中化。做法是把各環境的 Data Source 集中管理，讓主要的 Grafana 可以查詢不同環境的資料。

這樣的好處是，維運入口變得單一。當問題發生時，不需要在 14 個 Grafana 之間來回切換，而是可以在同一個 Grafana 中選擇環境、產品線或 namespace 來觀察。

對管理層來說，這也代表整體監控視角會更一致。未來不管是看 ISOP、TX，或是不同 Fab、不同環境，都可以逐步收斂到同一個觀察入口。

---

## Slide 6｜Optimization 2：Log 結構化

**時間：1 分鐘 20 秒**

**投影片重點：**

* 原本：plain text log
* 現在：JSON log
* JSON log 可提供更多上下文：

  * request id
  * workflow id
  * task id
  * status
  * error reason
  * environment / namespace
* 效益：

  * 更容易搜尋、過濾、聚合
  * 減少人工比對時間
  * 提高查案效率

**逐字稿：**

第二個優化是 Log 結構化。

過去很多 Log 是 plain text，也就是一整段文字。這種格式在單筆閱讀時還可以，但當問題發生，需要查大量 Log 時，就會變得很沒效率。

例如我們想查某一個 workflow id 的所有相關紀錄，或是某一類錯誤在某個時間區間內出現幾次，如果 Log 沒有結構化，就需要靠人工搜尋與比對。

因此我們逐步將 Log 從 plain text 轉成 JSON 格式。

JSON log 的好處是，它可以把重要的上下文資訊拆成欄位，例如 request id、workflow id、task id、status、error reason、namespace、environment 等。

這樣在 Kibana 查詢時，就可以用欄位做精準過濾，而不是只靠關鍵字模糊搜尋。

對查案來說，這會大幅減少時間成本。以前可能要人工從多段文字裡找關聯，現在可以直接用欄位把相關 Log 串起來。

簡單來說，結構化 Log 的價值，就是讓 Log 不只是文字紀錄，而是可以被查詢、過濾與分析的資料。

---

## Slide 7｜Optimization 3：Metrics 補足 SQL 監控短板

**時間：1 分鐘 30 秒**

**投影片重點：**

* 新增多類系統 Metrics：

  * Airflow：Scheduler、DAG、Task、Queue 狀態
  * Conductor：Workflow、Task、Worker、Timeout、API latency
  * Kubernetes：Pod、CPU、Memory、Restart、Thread
* 補足 SQL 不容易觀察的面向：

  * 即時健康度
  * 系統壓力
  * 執行延遲
  * 異常趨勢
* 讓問題能更早被發現

**逐字稿：**

第三個優化，是針對各系統補上 Metrics。

這也是 Prometheus Stack 最重要的價值之一。

SQL Query 通常比較適合看結果，例如某個任務最後成功或失敗、某個資料量是否異常。但很多系統問題，在變成結果異常之前，其實已經有一些前兆。

例如 Airflow Scheduler 開始延遲、Task queue 開始堆積、Conductor Worker polling 變慢、Workflow decision time 變長、Kubernetes Pod 頻繁重啟，或是 Tomcat thread 接近滿載。

這些狀態如果只靠 SQL，不一定能即時掌握。

所以我們針對 Airflow、Conductor、Kubernetes 等系統逐步補上 Metrics，讓我們可以觀察系統壓力、執行延遲、資源使用率與異常趨勢。

這帶來的價值是，問題不一定要等到使用者回報，或等到資料結果出錯後才被發現。

透過 Metrics，我們可以更早看到系統正在變慢、正在堆積、正在接近瓶頸。

對維運來說，這代表從被動救火，逐步往主動預警靠近。

---

## Slide 8｜Future Work：下一階段規劃

**時間：1 分鐘 20 秒**

**投影片重點：**

* SRE Agent：結合 AI 提高查案效率

  * 自動整理告警上下文
  * 查詢 Metrics / Logs
  * 參考 SOP
  * 初步推測 root cause
* Sanity Check 自動化：

  * 自動截圖 Grafana Panel
  * 快速回覆驗證結果
  * 降低人工截圖與整理成本
* 目標：讓維運從「人工查詢」走向「輔助判斷」

**逐字稿：**

最後是下一階段的 Future Work。

第一個方向，是結合 AI 提高查案效率，也就是我們稱為 SRE Agent 的方向。

目前查案通常需要工程師收到告警後，手動打開 Grafana、Kibana、Prometheus，再去對照 SOP 或過去經驗，最後整理出可能原因。

未來我們希望 SRE Agent 可以協助完成前面的資料整理工作。

例如告警發生時，自動查詢相關 Metrics、Logs，整理異常時間點、影響範圍、相關 Pod 或 Workflow，並參考既有 SOP，給出初步 root cause 推測與建議處理方向。

這不代表完全取代工程師判斷，而是讓工程師不用從零開始查，能更快進入問題核心。

第二個方向，是 Sanity Check 自動化。

目前很多驗證結果需要人工打開 Grafana、選時間、截圖、整理，再回覆給相關窗口。這些動作本身不難，但很花時間，而且重複性高。

未來我們希望可以自動截取指定 Grafana Panel，快速產生驗證結果，讓例行檢查或問題確認更有效率。

總結來說，現階段 Monitor Stack 已經完成基礎建設與幾個重要優化；下一階段，我們會把重點放在自動化與 AI 輔助，讓維運從「人工查詢」逐步走向「系統輔助判斷」。

---

## Closing｜收尾講稿

**時間：30 秒**

今天簡單介紹了我們自建 Monitor Stack 的背景、架構、目前優化，以及未來方向。

整體來說，這套系統的價值不是單純多建一套監控工具，而是幫助團隊更快發現問題、更快定位問題，並且降低長期維運成本。

目前我們已經完成 Grafana 集中化、Log 結構化，以及 Metrics 補強。接下來會進一步導入 AI 與自動化，讓監控系統不只是看板，而是能協助維運決策的工具。

以上是今天的介紹，謝謝。
