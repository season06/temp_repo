# 強制身分認證 Hook 設計（Mandatory Auth Hook）

日期：2026-07-11
狀態：已實作
範圍：`agent_template` SDK（branch `agent-template`）

## 需求

每次呼叫 Agent 前，都必須先透過 SDK 內建的 middleware / hook 完成身分認證（Authentication）。
此驗證屬於 SDK 的**強制機制**：使用者即使基於該 SDK 開發，也**無法移除、覆寫或繞過**它。
使用者仍可在其之上疊加自己的商業邏輯 hook。

## 定案決策

1. **強制程度：API 設計強制（擋意外）。** auth middleware 在 build 期由 SDK 內部自動注入，開發者的 build API 沒有可關閉/替換它的旋鈕。純 Python 下執意 monkeypatch 者仍可繞過，但正常使用不可能誤關。符合本專案既有威脅模型「主要擋意外、次要盡力擋惡意且可偵測」。編譯硬化（Nuitka `.so`）不在本次範圍。
2. **觸發邊界：兩層皆強制。** 新增 agent 入口強制 auth（每次 `invoke`/`ainvoke` 前一次），並將既有的 per-tool auth 從「選配」提升為「強制自動注入」。
3. **身分來源：per-call，取自 invocation context。** 呼叫端在 `invoke`/`ainvoke` 時透過 `context=` 傳入身分/憑證；middleware 由 `runtime.context` 讀出。
4. **拒絕行為：agent 入口 `raise`，per-tool 維持 `StopRound`。** 入口驗不過直接拋 `AuthenticationError`，LLM 與 tools 完全不執行；per-tool 驗不過沿用既有 `StopRound`（中止該輪）。

## 核心原則：auth 是地板，使用者 hook 只能疊加在上

- **強制（不可動）：** SDK 注入的 `AuthMiddleware`（入口）與 `AuthHook`（per-tool）永遠排在最前，開發者無關閉/移除旋鈕。
- **可擴充（開放）：** 開發者照舊用 `builder.add_hook(MyBusinessHook())` 疊加自己的 hook，這些 hook 一律接在 auth **之後**執行。
- 使用者 hook 只能在 auth 通過後再加限制（可用 `StopRound` 基於自己的理由擋下 tool），**不能**改變或還原 auth 的決定。

## 架構：單一咽喉點

目前 middleware 於 `core/factory.py::build_deepagent` 內就地組裝。改為抽出一個 provider-agnostic 的共用 helper，由它獨佔「強制順序」：

```
assemble_middleware(config, hooks, observability) -> list[middleware]
    永遠回傳：
      [ AuthMiddleware(auth_client),                        # 強制 · agent 入口 · 最前
        HookMiddleware([AuthHook(auth_client), *hooks]),    # 強制 auth 先, 使用者 hook 疊加在後
        *observability ]                                    # 選配
```

- 每個 provider builder（`build_deepagent` 及任何未來 adapter）**只**透過此 helper 組 middleware。
- 內建 `deepagent` provider 的所有路徑都經此 helper，故「內建 provider 組裝出無 auth 的 agent」不存在 —— 此為**結構性保證**。**例外（擋意外門檻）：** `register_provider` 可註冊/覆寫自訂 provider builder；該 builder 若不呼叫 `assemble_middleware` 即無強制 auth。註冊/覆寫 provider 屬刻意的架構行為（adapter 作者責任），視為可信種子，不在結構性保證涵蓋範圍內。
- auth client 由 `config.auth` 建一次，入口 middleware 與 per-tool hook 共用同一個。

## 元件

| 元件 | 狀態 | 職責 |
|------|------|------|
| `AuthMiddleware` | 新增 | 實作 `before_agent`（sync）；`ainvoke` 亦回退呼叫此 sync 方法（async 下短暫阻塞，MVP 接受，與 `AuthHook` 一致）。由 `runtime.context` 讀身分 → 呼叫 auth client → 失敗則 `raise AuthenticationError`。 |
| `AuthHook` | 既有，行為不變 | per-tool `before_tool` → 拒絕回 `StopRound`。由「開發者自行 `add_hook`」改為「`assemble_middleware` 自動注入」。 |
| auth client（`AuthClient`/`AsyncHttpAuthClient` seam） | 既有，沿用 | 提供 sync + async verify。verify payload 由 `_auth_payload` 依 context 組出：per-tool 帶 tool 名，入口與 per-tool 皆帶呼叫者身分。async client（A2A）不變。 |
| 身分通道 | 新增 | SDK 宣告 `context_schema`（如 `AuthContext`，含 token/identity 欄位）。呼叫端 `agent.invoke(state, context={...})`；middleware 讀 `runtime.context`。 |
| `AuthenticationError` | 新增 | SDK 自有例外型別，讓呼叫端能與一般錯誤區分地 `except`。 |
| `config.auth.endpoint` | 既有，沿用 | 未設定時觸發 fail-closed（見下）。 |
| 開發者 hooks（`add_hook`） | 不變 | 一律在 auth 之後執行。 |

## 控制流

**成功呼叫** `agent.invoke(state, context={"identity": ...})`：
```
invoke/ainvoke
  → before_agent (AuthMiddleware)     ── verify(identity) → pass
  → before_model → LLM turn
      → wrap_tool_call:
            AuthHook.before_tool       ── verify(identity, tool) → pass
            → user hook 1 → user hook 2 → 執行 tool
      → after_model
  → agent 結束, 回傳原生結果
```

**入口拒絕：**
```
before_agent → verify 失敗 → raise AuthenticationError
  → invoke/ainvoke 向外傳播例外; LLM/tools 從未執行
```

**tool 拒絕：**
```
AuthHook.before_tool → verify 失敗 → StopRound
  → 合成 session_stop ToolMessage; 該 call 的使用者 hook 不執行; 中止該輪
```

## 錯誤處理與 fail-closed

- **auth endpoint 未設定**（`config.auth.endpoint` 為 `None`）：**build 期直接拒絕** — `assemble_middleware` / `get_provider_builder` 拋清楚的設定錯誤。理由：強制 auth 卻無端點屬設定錯誤，應立即浮現，而非到第一次 invoke 才靜默拒絕。
- **auth endpoint 不可達 / 非 200 / verify 任何例外**：fail-closed 視為拒絕（入口 → `raise AuthenticationError`；tool → `StopRound`）。既有 client 已如此。
- **context 缺身分**：fail-closed 拒絕，等同 verify 失敗。

## 測試策略

- `assemble_middleware` 在 0 / 1 / 多個使用者 hook 下，**永遠**把 `AuthMiddleware` 放最前且注入 `AuthHook` —— 證明不論開發者輸入為何，auth 都存在且排序正確（「無法移除」保證）。
- 每個 provider builder 都經由 `assemble_middleware`（無旁路）。
- 入口 auth：通過 → agent 執行；失敗 → `invoke` 與 `ainvoke` 皆拋 `AuthenticationError`（async 路徑對 MCP agent 重要）。
- per-tool auth 仍以 `StopRound` 拒絕；疊在其後的使用者 hook 於放行時仍執行，且可獨立 `StopRound`。
- fail-closed：未設 endpoint → build 期拋；endpoint 不可達 / 缺身分 → 拒絕。
- context 身分確實進入 verify payload。

## 範圍外 / 延後

- 編譯硬化（Nuitka `.so` + 完整性檢查）以擋惡意竄改 —— 本次僅做 API 設計強制。
- verify 的正式契約（真實 auth 端點的 request/response、caller identity 欄位、headers）沿用 MVP mock 契約；正式契約由團隊敲定。
- A2A 入站 auth 已於 P6 存在，本設計聚焦於本地 `invoke`/`ainvoke` 入口；兩者共用 auth client seam，但整合細節不在本次。

## 已驗證（實作期確認）

- `before_agent` 於 `invoke`/`ainvoke` 皆觸發，且 `raise` 能乾淨傳播出 `invoke`/`ainvoke`（langgraph node 例外傳播），不會被吞掉或轉型。
- `context=` dict 會 coerce 成 `AuthContext`，並可由 `runtime.context` 讀出（`context_schema=AuthContext` 經 `create_deep_agent` 原樣透傳）。
- 入口採 sync `before_agent`（async 下短暫阻塞，MVP 接受，與既有 `AuthHook` 一致）。
