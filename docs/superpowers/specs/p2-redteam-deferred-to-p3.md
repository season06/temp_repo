# P2 紅隊發現 — 延到 P3 的項目

來源:`p2-envelope-hardening` 紅隊 workflow(46 findings,11/12 rule changes 已採用並在 P2 實作)。
以下為刻意**延到 P3**(編譯硬化階段)處理的項目;此檔為稽核軌跡與 P3 規劃輸入。

- **進階混淆正規化**:leetspeak 折疊、base64/rot13/hex 解碼後再掃描。模稜兩可、易誤判,需調校後的 canonicalization 放在編譯層。
- **同形字(homoglyph)防禦**:需 Unicode TR39 confusables/skeleton 表,對合法混合書寫文字本身有誤判面。
- **注入樣式的字詞插入縫隙**:如 "ignore. previous instructions"、"ignore all of the previous instructions";放寬間隔會拉高誤判,需謹慎調校。
- **間接注入(indirect injection)**:經由 tool / RAG / 取回文件內容的注入。目前 guard 只看 HumanMessage;掃 tool/AI 訊息內容誤判面高,需攔截設計。
- **電話號碼偵測**:無低誤判的硬擋 baseline regex;需 locale-aware matcher。
- **通用高熵機密**:AWS 40 碼 secret key、裸密碼、無已知前綴的 sk-/bearer blob;熵啟發法會與 hash/UUID/ID 衝突,需 entropy scorer + allow-list。
- **輸出涵蓋範圍擴大**:掃中間 AIMessage/tool 結果、`_final_text` 不只看 `messages[-1]`;重掃歷史有重複擋/誤判風險,需定義「本回合產生的輸出」。
- **工具輸入/輸出攔截**:封住 tool 端外洩需 tool-wrapping 子系統;v1 工具仍在使用者信任邊界內。
- **Validator monkeypatch 硬化**:in-process validator 可 rebind `detect_pii`;唯有把 `_secure/` 以 Cython 編譯使綁定內部化才能真正緩解(=P3 核心目的)。
- **IMEI 殘留誤判**:15 碼 IMEI 為 Luhn-valid 仍會被標記;v1 接受,以測試記錄而非再加 regex 扭曲。
