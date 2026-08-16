"""Public API 型別介面。實作以 sourceless .pyc 散布,本檔僅供 IDE 與型別檢查。"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

__all__ = ["AgentBuilder", "Config", "ConfigError"]

class ConfigError(Exception):
    """config 檔錯誤;訊息為人話,可直接顯示給使用者。"""

class AgentSection:
    name: str
    """agent 在 registry 的查詢 key。"""
    provider: str
    """agent 實作供應者,目前支援 "deepagent"。"""
    model: str
    """LLM 模型名稱;留空則需在 build(model=...) 提供。"""
    system_prompt: str
    """系統提示詞。"""

class McpServer:
    name: str
    transport: str
    url: str

class A2aAgent:
    name: str
    url: str

class Config:
    """已載入並驗證的設定(yaml + .env 合併結果)。"""

    agent: AgentSection
    agent_card: str
    """agent card 檔路徑;留空則找 config 同目錄的 agent_card.yaml/.json。"""
    local_mcp: list[McpServer]
    local_tools: list[str]
    local_skills: list[str]
    local_a2a: list[A2aAgent]

class Agent:
    """建好的 agent。str 進 str 出;傳 dict 則透傳原生行為。"""

    native: object
    """底層原生 agent 物件(進階用途)。"""

    def a2a_app(self, host: str = ..., port: int = ..., auth=...):
        """回傳 A2A 的 ASGI app,供掛既有服務、自控部署或測試直打。"""

    def serve(self, host: str = ..., port: int = ..., auth=...) -> None:
        """一行把 agent 曝露成 A2A 端點(阻塞執行)。"""

    def invoke(self, message: str) -> str:
        """同步呼叫 agent,回傳最終回覆文字。"""

    async def ainvoke(self, message: str) -> str:
        """invoke 的 async 版。"""

    def astream(self, message: str) -> AsyncIterator[str]:
        """async 逐段串流回覆文字。"""

    def stream(self, message: str) -> Iterator[str]:
        """同步逐段串流回覆文字(適合邊產生邊印)。"""

class AgentBuilder:
    """從 config 檔建立 agent 的進入點。"""

    def __init__(self, config: str | Path) -> None:
        """以 config 檔路徑(str 或 Path)建立 builder;載入 yaml + .env 並合併 remote/local 設定。"""

    def build(self, **kwargs) -> Agent:
        """建立並回傳 Agent。

        可用 kwargs:model、system_prompt、tools、skills、middleware。
        撞名時 config 優先於 build() 傳入值,並會發出 warning。
        """
