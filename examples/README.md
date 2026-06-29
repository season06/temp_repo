# agent_template 範例

## MVP:支援型 agent(`mvp_support_agent.py`)

示範團隊成員如何用 SDK 開發 agent:提供 `task_prompt`、自己的工具、(可選)自己的輸出 validator;**安全外殼(輸入防護 / 輸出驗證 / prompt 夾心)自動套用且關不掉**。

### 執行

```bash
# 從 repo 根目錄(尚未 pip install 時用 PYTHONPATH)
PYTHONPATH=. .venv/bin/python examples/mvp_support_agent.py
```

預設為 **OFFLINE** 模式(內建 canned 模型),讓五個情境不需真實 LLM 即可展示:

| 情境 | 結果 |
|---|---|
| 一般問題 | ✅ 正常回覆 |
| Prompt injection 輸入 | ⛔ 進模型前就被擋(`before_agent`) |
| 輸出含信用卡號 | ⛔ 強制輸出驗證擋下(Luhn-gated) |
| 成員自訂 validator(內部代號) | ⛔ 自訂驗證擋下(跑在強制層之前) |
| `.stream()` | ⛔ SecureAgent 停用串流(會繞過輸出驗證) |

### 接真實 Qwen

設環境變數後,「一般問題」情境會走真實呼叫:

```bash
export QWEN_API_KEY=sk-...
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1   # 可選
export QWEN_MODEL=qwen-max                                                # 可選
PYTHONPATH=. .venv/bin/python examples/mvp_support_agent.py
```

> 真實使用者只需設定 `AgentConfig` 並呼叫 `build_agent(...)`;範例裡的 canned 模型注入(`factory.build_chat_model = ...`)只是為了離線展示,正式使用不需要。

## 安全核心編譯(Cython,P3)

`build_secure.py` 把 `agent_template/_secure/` 的敏感模組(規則、prompt、guard/validation、SecureAgent)編成原生擴充(`.so`),讓邏輯以二進位散布而非可改寫的原始碼。

```bash
.venv/bin/python build_secure.py      # 產生 agent_template/_secure/*.so(in-place)
.venv/bin/python -m pytest -q          # 編譯後行為應與原始碼完全一致(176 passing)
```

- 採 Cython **pure-Python mode**:`.py` 仍是源碼,執行時 `.so` 優先載入。
- 此環境的 CPython 3.14 dev headers 已抽到 `.pyhdr/`(免 root);一般機器裝了 `python3.x-dev` 後 `build_secure.py` 的 `INCLUDE_DIRS` 可留空。
- 尚未做(P3 後續):整合 `cibuildwheel` 出多平台 wheel(wheel 內只放 `.so`)、完整性自檢、以及把 factory wiring 納入編譯邊界(R1)。
