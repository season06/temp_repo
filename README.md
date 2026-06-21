## Slide 1 — 自建 Monitor Stack 維運優化

今天我要分享 我們團隊過去這段時間在監控系統上做的一些演進。
我們的產品線同時涵蓋 iSOP 和 TX 兩個系統,
如何確保這兩個系統的健康狀態能被有效監控,一直是維運上的核心課題。
今天會從現況的背景出發,帶大家看我們做了什麼、解決了什麼問題,以及接下來要走的方向。

## Slide 2 — Background:現有監控的局限
> 投影片內容: 兩欄式,左側「One Defense 的價值」,右側「遇到的瓶頸」
> 投影片重點:
```
- 原本組織已有 One Defense，可透過 SQL Query 產生監控指標
- One Defense 適合資料庫型、結果型監控
- 但對即時系統狀態、服務健康度、Kubernetes、Airflow、Conductor 等監控較有限
- 因此逐步導入 Prometheus-based Monitor Stack
```
> 逐字稿:
目前組織既有的監控平台 - One Defense 的優勢是，透過定期執行 SQL Query, 把資料庫裡的資料轉換成監控指標。對於已經落在資料庫中的業務資料、運行結果，它是非常有價值的。

但隨著系統逐漸容器化、與複雜度提升, SQL-Base 的監控方式有根本上無法突破的限制:
- One Defense 能檢索的只有「資料庫裡的資料」，對於系統的「當前」的執行狀態、或應用程式內部的健康度、資源使用率，無法藉由 SQL 維度呈現

也就是說，One Defense 比較像是看「結果」，但我們還需要一套系統來看監控系統的「過程」與「即時狀態」。
因此，我們逐步將部分監控移轉到以 Prometheus 為核心的 Monitor Stack，補足原本 SQL-based monitoring 看不到的面向。

## Slide 3 — Architecture:監控平台架構
> 投影片內容: 架構示意圖,兩層:自建 Stack（Prometheus / AlertManager / Grafana / Elasticsearch / Kibana） + One Defense 
> 投影片重點:
```
- 支援兩個產品線：ISOP、TX
- 自建 Monitor Stack：
    - Prometheus：收集 Metrics
    - AlertManager：告警通知
    - Grafana：視覺化 Dashboard
    - ElasticSearch：儲存 Log
    - Kibana：查詢與分析 Log
- 組織既有監控：
    - One Defense：透過 SQL Query 產生指標
- 兩者互補，而非互相取代
```
> 逐字稿:
目前我們的 Monitor Stack 設計上，希望可以同時支援多個產品線，包含 ISOP 和 TX。

這是我們目前的監控架構全貌，整體上可以分成兩塊。

第一塊是我們團隊自建的 Monitor Stack。
Prometheus 負責收集各系統的 Metrics，例如 Kubernetes、Airflow、Conductor，以及服務本身暴露出來的指標。
當 Metrics 達到異常條件時，會透過 AlertManager 發送告警，讓夥伴可以第一時間收到通知。
Grafana 則負責把這些指標視覺化，讓我們可以透過 Dashboard 快速看到系統健康度、趨勢與異常點。
另外，Log 的部分會進到 ElasticSearch，並透過 Kibana 進行查詢與分析。這主要用在問題發生後，需要往下追細節的情境。

第二塊是組織既有的 One Defense。
One Defense 仍然保留它的價值，特別是在 SQL Query 能夠直接反映業務資料或交易結果的場景。

這套監控系統結合組織現有的 One Defense，可同時監控系統運行狀態、與業務運行結果，整體監控覆蓋率會更完整
且這套架構同時服務 iSOP 和 TX 兩個產品線,讓我們在一個平台上就能掌握兩個系統的健康狀態。


## Slide 4 — 痛點與優化 1 - Grafana Centralize
> 投影片內容: 三張卡片式佈局,每張對應一項優化,標題+成效數字
> 投影片重點：
```
- 原本：14 個環境，各自一座 Grafana
- 現在：集中 Data Source，整合成一座主要 Grafana
- 效益：
    - 降低 Grafana 維運成本
    - 減少查案時切換環境的時間
    - Dashboard 管理更一致
    - 管理層與維運團隊可以共用同一個觀察入口
```
> 逐字稿:
建立這套平台的過程中,我們也遭遇了不少維運上的痛點,並且逐一做出優化。這裡跟大家報告三個最關鍵的改善。

第一個是 Grafana 集中化。
痛點:
1. 維運成本高: 過去我們在 14 個不同 fab 環境各自跑一座 Grafana,工程師查問題時要在多個介面之間切換,維護成本也非常高。
2. 無法整合多個環境進行盤點
優化:
1. 入口單一化: 現在把所有環境的資料來源都集中到一座 Grafana,這大幅降低了切換成本,也讓儀表板的維護從 14 份變成 1 份。 
不管是不同系統、不同 Fab、不同環境，都可以收斂到同一個入口。工程師只需要在同一個入口就能切換不同環境的狀態

## Slide 5 — 痛點與優化 2 - Log 結構化 
> 投影片重點：
```
- 原本：plain text log
- 現在：JSON log
- JSON log 可提供更多上下文：
- 效益：
更容易搜尋、過濾、聚合
減少人工比對時間
提高查案效率
```
> 逐字稿:
第二個是 Log 結構化。 
原本系統產生的 Log 是 plain text，也就是一段純文字。這種格式在單筆閱讀時還可以，但當問題發生，需要查大量 Log 時，就會變得很沒效率。

例如我們想查某一個 SOP 為何做動異常，我們僅能藉由模糊搜尋，找出相對應的時間區間，再人工逐一縮小範圍，非常費時。

將 Log 從 plain text 轉成結構化的 JSON 格式的好處是，可以把重要的上下文資訊拆成欄位，例如 sop id、workflow id、task id、status、error reason、namespace、environment 等。
在 Kibana 查詢時，就可以用欄位做精準過濾，而不是只靠關鍵字模糊搜尋。
對查案來說，這會大幅減少時間成本。以前可能要人工從多段文字裡找關聯，現在可以直接用欄位把相關 Log 串起來。

## Slide 6 — 痛點與優化 3 - 補齊 Metrics
> 投影片重點：
```
- 新增多類系統 Metrics：
    - Airflow (排程健康度)：Scheduler Fail Rate
    - Conductor (工作流執行狀態)：Worker Queue Status、Timeout、異常 Terminal task
    - Kubernetes (叢集的資源使用狀況)：Pod、CPU、Memory、Restart
- 補足 SQL 不容易觀察的面向：
    - 即時健康度
    - 系統壓力
    - 執行延遲
    - 異常趨勢
- 讓問題能更早被發現
```
> 逐字稿:
第三個是指標覆蓋補強。
針對幾個 SQL 無法監控到的關鍵系統增加了專屬的指標。這些指標讓我們能在問題發生之前就提前預警，很多系統問題在變成結果異常之前，其實已經有一些前兆
例如 Airflow Scheduler 開始延遲、Task queue 開始堆積。

新增多類系統 Metrics：
- Airflow (排程健康度)：Scheduler Fail Rate
- Conductor (工作流執行狀態)：Worker Queue Status、Timeout、異常 Terminal task
- Kubernetes (叢集的資源使用狀況)：Pod、CPU、Memory、Restart

根據我們的觀察，當 one defense 發出警報時，prometheus 通常在 5~10 分鐘前就偵測到系統異狀


## Slide 7 — Future Work
> 投影片內容: 兩個方向,各有 icon + 標題 + 一句說明
> 投影片重點:
```
- SRE Agent：結合 AI 提高查案效率
    - 自動整理告警上下文
    - 查詢 Metrics / Logs
    - 參考 SOP
    - 初步推測 root cause
- Sanity Check 自動化：
    - 自動截圖 Grafana Panel
    - 快速回覆驗證結果
    - 降低人工截圖與整理成本
目標：讓維運從「人工查詢」走向「輔助判斷」
```
> 逐字稿:

最後分享兩個正在規劃中的方向。 

第一個是 SRE Agent, 希望結合 AI 提升查案效率。
目前查案通常需要工程師收到告警後，手動打開 Grafana、Kibana、Prometheus，再去對照 SOP 或過去經驗，最後整理出可能原因。
未來我們希望 SRE Agent 可以協助完成前面的資料整理工作。
例如告警發生時，自動查詢相關 Metrics、Logs，整理異常時間點、影響範圍、相關 Pod 或 Workflow，並參考既有 SOP，給出初步 root cause 推測與建議處理方向。
這不代表 AI 需要完全取代工程師的判斷，而是讓工程師不用從零開始查，能更快進入問題核心。

第二個是 Grafana Sanity Check 自動截圖。
目前當周值班接到二線回報 sanity check 的需求越來越多，人工打開 Grafana、切換系統、截圖、回報，雖然動作本身不複雜，但重複性高，累積下來值班人員當週花在 sanity check 的時間也相當多。
未來我們希望可以自動截取指定 Grafana 儀表板的畫面，並直接回報到通訊頻道，讓驗證流程從原本需要人工操作縮短為自動完成。

總結來說，現階段 Monitor Stack 已經完成基礎建設與幾個重要優化；下一階段，我們會把重點放在自動化與 AI 輔助，讓維運從「人工查詢」逐步走向「系統輔助判斷」。