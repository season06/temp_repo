# AI Agent Template 設計規格書

- 日期:2026-06-29
- 狀態:設計確認(待 plan 拆解)
- 分支:`ai-agent`

## 目的

提供一個團隊共用的 Python AI Agent 模板,讓內部成員以此為骨架快速開發各類 agent。模板建構於 LangChain 的 **deepagents** 之上,並在其外加一層**安全外殼**,確保安全相關邏輯(system prompt、輸入防護、輸出驗證)不會在正常使用下被改弱。

## 範圍與前提

- **散布模式:** pip 函式庫(library)。團隊成員 `pip install` 後在自己的程序中執行 agent。
- **Agent 類型:** 通用型(RAG 問答、工具/流程型、混合皆可),模板對「agent 要做什麼」保持中立。
- **威脅模型:**
  - **主要(必須做到):** 防止「意外/便宜行事」的誤用——安全路徑為預設,繞過安全層必須困難且顯眼。
  - **次要(盡力而為):** 對蓄意拆除防護者提高成本並可偵測,接受在 library 模式下無法做到絕對防護。
- **既有資產沿用:** RAG 檢索接既有的 RAG Adapter SDK(tkms / Qdrant / Qwen via API);LLM provider 沿用 Qwen(OpenAI 相容 API)策略。

## 核心架構:安全外殼 + 可自訂核心

模板是「deepagents 之上的安全化封裝」。deepagents 既有能力(規劃工具、子代理、虛擬檔案系統、human-in-the-loop)不重造,只在其外加上統一骨架與安全外殼。

設計的關鍵是把 prompt 與驗證拆成**兩層**,使「通用」與「不可改弱」得以並存:

- **安全外殼(框架擁有,受保護、不可覆蓋)**
  - base 防護 system prompt
  - 強制**輸入防護**(prompt injection / PII 偵測)
  - 強制**輸出驗證**(post-hook)
- **可自訂核心(成員擁有)**
  - 任務用 task prompt
  - 自訂工具
  - 額外的自訂驗證(跑在框架強制驗證**之前**)

外殼「包住」核心:

```
最終 system prompt = [安全前綴] + [成員 task_prompt] + [安全後綴]
輸出驗證流程       = [成員自訂驗證(可選)] → [框架強制驗證(必跑、擋得住)]
輸入處理流程       = [框架強制輸入防護(必跑)] → 進入 agent
```

成員只能填中間那層;外層由框架自動套上,正常使用 API 時碰不到也覆蓋不掉。

## Q1:通用 agent 的功能組成

對外只有**單一入口**(Agent Factory)。功能分核心與可插拔兩類。

### 核心骨架(框架管理,人人皆有)

1. **Agent Factory** — 唯一建構入口。輸入 `task_prompt`、`tools`、`config`;**不提供**覆蓋 base prompt 或關閉驗證的參數。
2. **安全外殼(受保護、編譯)** — base 防護 prompt + 強制輸入防護 + 強制輸出驗證。
3. **LLM Provider 設定** — Qwen via API(OpenAI 相容);model 與參數集中管理。
4. **工具註冊(Tool Registry)** — 成員註冊自訂工具;支援 allow/deny 政策。
5. **狀態 / 記憶 / checkpoint** — 對話狀態(LangGraph state)。
6. **可觀測性(Observability)** — 結構化日誌、token/成本追蹤、audit log。
7. **錯誤處理** — retry / timeout / 統一例外型別。
8. **設定管理(Config)** — frozen dataclass(沿用既有 config 層的全型別風格)。

### 可插拔(opt-in)

- RAG 檢索工具(接既有 RAG Adapter SDK:tkms / Qdrant / Qwen)
- 子代理(deepagents)、human-in-the-loop 審批、streaming
- 成員額外的自訂驗證(置於框架強制驗證之前)

## Q2:保護機制(API 設計 + Cython 編譯 + 完整性檢查)

採「方案 2」:在 library 模式下,以 API 設計堵住意外、以編譯與完整性檢查提高蓄意拆除的成本並使其可偵測。

### A. API 表面設計(主要防線:擋意外)

- 安全邏輯置於私有套件 `_secure/`(base prompt、輸入防護、輸出驗證)。
- Factory 內部自動串接安全外殼;對外簽章僅 `task_prompt` / `tools` / `config`,**無**任何參數可覆蓋 prompt 或關閉驗證。
- `__init__.py` 僅 export 安全介面;私有模組不對外公開。
- system prompt 的「夾心」組裝在編譯層內完成。

### B. 編譯(提高蓄意拆除成本)

- `_secure/` 整包以 **Cython** 編成 `.so`/`.pyd`,發布的 wheel **不含對應 `.py` 原始碼**。
- 其餘骨架(factory、registry、observability)維持純 Python,方便團隊閱讀與除錯;**僅安全核心編譯**。
- 以 `cibuildwheel` 產出 Linux / macOS / Windows 多平台 wheel。

### C. 完整性檢查與偵測

- agent 建構時,編譯層自我檢查:輸入防護與輸出驗證 callable 仍為框架原生(身分/簽章比對),且 prompt 安全標記存在。
- 偵測到被替換或移除時,**預設拒絕執行**,並寫入本機 audit log。
- 中央回報(tamper telemetry)留作日後可選升級(原「方案 3」)。

### D. CI 防呆(供使用端 repo)

- 提供可選的 lint / pre-commit 規則:偵測 `import _secure.*`、對 factory 做 monkeypatch、或試圖注入假驗證時,使 CI 失敗。

## 明確不做(本版範圍外)

- 中央 tamper telemetry 伺服器(方案 3)——日後可選。
- 伺服器 / gateway 集中執行模式(model B)——若未來需擋蓄意內部人再評估。
- 對「絕對防止蓄意拆除」的保證——library 模式下不可能,僅提供盡力而為的成本與偵測。

## 未決 / 後續由 plan 處理

- 各功能模組的介面與檔案結構。
- 輸入防護 / 輸出驗證的具體規則與實作方式。
- 完整性檢查的簽章機制細節。
- 多平台 wheel 的 build 與發布流程。

> 實作細節(逐步 task、程式碼、TDD)寫入 `docs/superpowers/plans/`,分階段拆成多份;本 spec 維持高層方向不被實作細節污染。
