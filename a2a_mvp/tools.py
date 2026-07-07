import asyncio
from langchain_core.tools import tool
from a2a_mvp.a2a_client import call_peer, RemoteNotAllowed


def build_tools(config):
    @tool
    def echo_upper(text):
        """把輸入文字轉大寫回傳(本地示範工具)。"""
        return text.upper()

    @tool
    def call_remote_agent(base_url, prompt):
        """呼叫另一個 A2A agent。base_url 須在允許清單內;回傳其文字回應。"""
        try:
            return asyncio.run(call_peer(base_url, prompt, config))
        except RemoteNotAllowed:
            return f"ERROR: remote agent not allowed: {base_url}"
        except Exception as exc:  # 逾時/遠端錯誤 → 結構化錯誤,不讓 agent crash
            return f"ERROR: remote call failed: {exc}"

    return [echo_upper, call_remote_agent]
