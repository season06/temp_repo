該 PPT 內容是介紹團隊自建的 monitor stack,演講客群是管理層的老闆,時間限制在 10 min 內
Outline:
* Background: 組織有一套可 query SQL 資料作為指標的監控系統 (one defense),但因為其侷限性,逐漸將部分監控轉移到 prometheus 
* Architecture: (可兼容兩個產品的監控: isop, tx)
   1. 自家的 monitor stack: Prometheus, AlertManager, Grafana, ElasticSearch, Kibana
   2. 組織架設的監控: One Defense (藉由 SQL query 轉化為監控指標)
* 維運 Monitor Stack 遭遇許多痛點,目前已作出的優化:
   1. Grafana Centralize: 將 14 個環境的 Grafana 藉由集中 Data Source 僅留下一座 Grafana,減少維運與切換成本
   2. Log: 將 plain text 形式的 log 轉成 Json 形式,提供上下文訊息,減少查案成本
   3. Metrics: 針對各系統增加監控 metrics,彌補 SQL 無法監控的短版: 包含 Airflow, Conductor, k8s 相關指標 
* Future Work:
   1. 結合 AI 提高查案效率 (SRE Agent)
   2. 自動截圖 Grafana Panel 快速回覆驗證結果 (Sanity Check)