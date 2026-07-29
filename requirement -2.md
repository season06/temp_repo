# 第二階段: Agent Registry

可拉取來自遠端 Agent registry 的資源:以 agent 為單位,registry 回傳整包 agent 定義(zip),
用於中央管理 agent 設定。

## 識別與啟用

- 識別欄位: config 的 `agent.name`(**暫定**,團隊定案 id 規格後再改)
- 啟用條件: 環境變數 `AGENT_REGISTRY_URL` 與 config 的 `agent.name` **都有值**才去撈 registry;
  缺任一則走純 local,第一階段行為完全不變

## .env

```
# ===================
# Agent Registry
# ===================
AGENT_REGISTRY_URL=

# ===================
# Auth
# ===================
AUTH_TOKEN=
```

- `AUTH_ENDPOINT` 本次不實作(future,等團隊定案)
- registry 請求本身**暫不帶 token**(等團隊定案)

## API

- `GET {AGENT_REGISTRY_URL}/agents/{agent_name}`
- `200` + zip binary: 包含 `config.yaml`、`skills/`
- `404`: 查無此 agent → logger info、使用 local 設定(正常流程,不發 warning)

remote zip 的 `config.yaml`(schema 獨立於 local,`skills:` 欄位忽略——skill 以 zip 內 `skills/` 目錄為準):

```yaml
agent:
  provider: deepagent
  model: qwen-max
  system_prompt: "you are a helpful agent"

mcp:
  - name: remote-mcp
    transport: streamable-http
    url: https://
```

## 行為與優先序

一條鏈: **remote > local config > build()**,撞名高層贏、必發 warning。

- `agent:` 區塊: 撈到 remote 就**整包以 remote 為準**(`agent.name` 例外,永遠取 local);
  remote 覆蓋屬正常流程,記 logger info、不發 warning
- mcp / skills: remote 與 local **聯集 merge**;撞名 remote 贏 + warning
- skill 沿用根目錄掃描語義(zip 內 `skills/` 視為 skills root)

## 失敗行為(一律不擋 build)

- 連不上 / timeout / 5xx → warning + fallback **整包 local**
- remote config 驗證失敗(爛資料、zip 壞檔)→ warning + fallback 整包 local

## zip 落地

- 解壓到 `~/.cache/agent_template/<agent_name>/`(尊重 `XDG_CACHE_HOME`),拉新前先清舊
- 每次 `AgentBuilder(config)` init 都重新拉,不做快取(快取優化屬第三階段)

## Authentication

- **只有**來自 registry 的 mcp,存取時在 header 加 `Authorization: Bearer {AUTH_TOKEN}`
- `AUTH_TOKEN` 未設定但 remote mcp 存在 → warning「可能驗證失敗」+ 照連
  (連線失敗會再吃到 MCP 層的 warning + 跳過)
