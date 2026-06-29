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

## P3 必須處理(來自 P2 最終整支審查)

- **factory.py 不在編譯範圍內 → 完整性檢查必涵蓋 factory wiring(R1,重要)**:P3 僅編譯 `_secure/`,但「不可關閉」保證依賴 `factory.build_agent` 永遠注入 `build_security_middleware`。`factory.py` 維持純 Python,故 rebind `factory.build_security_middleware` / `factory._build_deep_agent` 即可在「編譯後」仍剝除外殼。P3 的完整性自檢(設計規格 §C)必須在 build 時驗證「實際掛上的 middleware 與 prompt 夾心為框架原生」,**或**把 factory 的安全 wiring 移進被編譯的套件。此屬「validator monkeypatch」同類,但延伸到 factory 接縫。
- **`.stream()` / `.astream()` 輸出驗證繞過(C1)**:P2 已用 `SecureAgent`(allow-list 包裝,只開放 invoke/ainvoke/batch/abatch,封鎖所有串流與 with_config/pipe/bind 等組合方法)擋住「意外」繞過。P3 需提供「驗證過的串流」設計(緩衝後再吐 或 chunk 級驗證)。
- **SecureAgent 的 in-process 固有限制(書面接受,model A)**:純 Python 包裝無法完全隱藏內層 graph —— 刻意者仍可經 `agent.__dict__['_SecureAgent__agent']` / `vars(agent)` / `gc.get_referents` 取得原始 runnable 直接 `.astream(...)` 繞過驗證。已用 name-mangling 擋住 casual `._agent` 探測;完全擋住刻意繞過需 P3 編譯 `_secure/`(把包裝/wiring 內部化)且最終需 server 端(model B)。此為與威脅模型一致的已接受取捨(主要防意外、次要提高刻意成本)。
