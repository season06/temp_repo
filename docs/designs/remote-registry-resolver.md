# Remote Registry Resolver — 設計方向

> 狀態:**方向已定、部分決策待團隊定案**。此文件為未來實作參考,非可執行 plan。
> 日期:2026-07-10

## 背景與問題

skill / mcp 的來源分兩種:**local** 與 **remote**。

- **local**:已知的具體工具。`config.{mcps,skills}.local`(宣告式)+ `add_mcp()` / `add_skill()`(runtime 追加)。
- **remote**:透過**中央 registry** 依名稱取得。目前 registry 契約尚未規劃。

要解決的是:remote 怎麼進入系統、以及它如何跟 local 的載入路徑整合。

## 已定案的決策

1. **remote 只從 config 進來,runtime 不碰。**
   需要經過 registry 的東西一律宣告在 config(`config.{mcps,skills}.remote`,型別 `RemoteRef`)。
   **不**提供 `add_remote_*()` 之類的 runtime API。
   理由:remote 需要 `registry_url` + 認證,屬基礎設施設定,本該宣告式管理。

2. **`add_*` 維持只做 local 的 runtime 追加。**
   `add_*` 的硬價值在於「傳 yaml 表達不了的活物件」(in-memory tool、現成 connection、帶閉包的 tool),不是「放 local」。local 同時可走 config 宣告與 `add_*` 追加(現況即如此)。

3. **分界是「靜態宣告 vs 動態追加」,不是「local vs remote」。**
   使用者心智:**固定的寫 config,臨時的用 `add_*`**。local/remote 與 config/method 是兩條正交的軸,不對角綁死。

4. **核心設計模式:resolver 匯流回 local 載入路徑。**
   remote 的唯一特殊處是前面多一個**解析層**(registry client),解析完的輸出型別**就是 `LocalMcp` / `LocalSkill`**,之後跟 local 走完全相同的 `load_configured_mcp_tools` / `load_skill_tools`。remote 對載入器透明。

## 架構

```
                       ┌─ config.mcps.remote  (RemoteRef) ─┐
     RegistryClient ◄──┤                                   ├─ resolve ─► [LocalMcp]  ─┐
   (registry_url)      └─ config.skills.remote (RemoteRef) ┘             [LocalSkill]─┤
                                                                                       │ 匯流
     config.mcps.local  (LocalMcp)   ──────────────────────────────────────────────► ├─► 既有 load 路徑
     config.skills.local (LocalSkill) ─────────────────────────────────────────────► │   load_configured_mcp_tools
     add_mcp / add_skill (runtime) ────────────────────────────────────────────────► ┘   load_skill_tools
                                                                                          → tools → create_deep_agent
```

### Resolver 介面(照 `auth/clients.py` 的 pattern:介面 + Http 實作 + 可注入 mock)

新檔 `agent_template/tools/registry.py`:

```python
class RegistryClient:
    """把 RemoteRef(registry_url + name[])解析成 local 描述物件。"""
    def resolve_mcps(self, ref: RemoteRef) -> list[LocalMcp]: ...
    def resolve_skills(self, ref: RemoteRef) -> list[LocalSkill]: ...

class HttpRegistryClient(RegistryClient):
    """逐 name 打 registry HTTP 端點,組成 LocalMcp / LocalSkill。
    解析失敗 = fail-loud(缺宣告的工具是該炸的錯,與 auth 的 fail-closed 相反)。"""

class MockRegistryClient(RegistryClient):
    """測試用:吃預先塞好的 dict,不打網路。"""
```

### 接進 builder(唯一匯流點)

`AgentBuilder` 多收可注入的 `registry`,`build()` 在載入前先解析並 append 到 local 清單之後:

```python
def build(self):
    mcps = list(self._mcps)      # config.local + add_mcp
    skills = list(self._skills)  # config.local + add_skill
    if self._registry is not None:
        mcps.extend(self._registry.resolve_mcps(self._config.mcps.remote))
        skills.extend(self._registry.resolve_skills(self._config.skills.remote))
    tools = list(load_configured_mcp_tools(mcps))
    tools.extend(load_skill_tools(skills))
    return get_provider_builder(...)
```

- `registry=None` 時整段跳過,行為與現況完全相同(remote 純加值、向後相容)。
- remote 沒有 `add_*` 對應,強制其只從 config 進來。

## Remote MCP — 乾淨,無懸念

remote MCP = **連到一個跑著的 server**,不搬 code。幾乎必然是 `streamable_http`
(stdio 是「本機 spawn 一支 .py」,遠端沒有那支檔案)。

```
GET {registry_url}/mcp/{name}
→ {"transport": "streamable_http", "url": "https://svc.internal/mcp", "func": ["get"]}
→ LocalMcp(name, transport="streamable_http", path=url, func=...)
→ mcp_to_connection(對 non-stdio:path 當 url)→ load ✅
```

`mcp_to_connection` 一行都不用改。

## 待定案決策

### D1. Remote skill 的語意 — **團隊尚未定案,傾向 A**

remote skill 與 remote MCP **本質不同**:skill 是一支要被 `importlib` 執行的 `@tool` .py
(`skills.py` 的 `exec_module`),「remote skill」意味那段 code 在別處,必須先弄到本機才能跑。

| 選項 | resolve_skills 做什麼 | 代價 |
|---|---|---|
| **A. 下載 code 再載入**(團隊傾向) | registry 回 `code_url` → 下載 .py 到 cache dir → `LocalSkill(name, path=cached.py)` | **遠端任意程式碼執行**。本專案無安全外殼 = 等於 100% 信任 registry |
| B. 套件名 + 安裝 | registry 回 `package="foo==1.2"` → pip install → import | 需可寫環境;但有 pip 的信任模型 |
| C. 不支援 | registry 只服務 MCP;遠端工具一律走 MCP | 最簡單最安全 |

**團隊目前傾向 A(下載 code 再載入)。** 若採 A,實作**必須**補上:

- **完整性驗證**:registry 回應帶 hash / 簽章,下載後比對,不符即拒載。
- **來源信任**:只允許白名單 registry;registry_url 走 HTTPS。
- **cache 落地策略**:下載到哪、如何 invalidate、是否 pin 版本。
- **明確風險註記**:此專案無安全外殼(見 req.md 定位),A 在無護欄處開任意 code 執行,上 prod 前需上述驗證到位。

`RemoteRef` schema 先保留;`resolve_skills` 在定案前可先接成拋 `NotImplementedError` + 清楚訊息,或回 `[]` 並 log。

### D2. Registry 數量 — **保留彈性,可能多組**

registry **可能有多組**,暫不收斂成頂層單一 `registry_url`。

- **維持 `RemoteRef` per-section**(`skills.remote` / `mcps.remote` 各自帶 `registry_url`),不提到頂層。
- 未來若需要「一個 section 對多個 registry」,可能演進為 **list of `RemoteRef`**
  (e.g. `mcps__remote: [{registry_url, name}, {registry_url, name}]`),resolver 逐一解析後合併。
- 設計 resolver 時**不要假設只有一個 registry_url**;`HttpRegistryClient` 應無狀態、
  registry_url 由每次 `resolve_*(ref)` 的 `ref` 帶入,而非建構時綁死單一 url。

## 其他實作細節

- **錯誤策略**:registry 解析失敗 **fail-loud**(raise,指出哪個 name 拿不到)。
- **快取**:`build()` 每次都解析;resolver 可自帶記憶體 cache(`dict[name→descriptor]`),MVP 先不做,註記即可。
- **exports**:`tools/__init__.py` 加 `RegistryClient / HttpRegistryClient / MockRegistryClient`。
- **測試**:`MockRegistryClient` 塞假 `LocalMcp` / `LocalSkill`,驗證
  (a) remote 被 append 在 local 之後、(b) `registry=None` 時完全跳過、(c) 解析失敗會 raise。
  不需真網路,與現有 `tests/fakes.py` 風格一致。

## 未解問題(等 registry 契約定案)

- registry 的實際 API 形狀(端點、回應 schema、認證方式)。
- D1 最終選項與(若 A)完整性驗證機制。
- D2 是否演進為 list of registries,以及跨 registry 的 name 衝突處理。
