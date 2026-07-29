"""Tool 掃描:遞迴載入目錄下的 .py,只收 module 層級 BaseTool 實例。"""

import importlib.util
import logging
import warnings
from pathlib import Path

from langchain_core.tools import BaseTool

logger = logging.getLogger("agent_template")


def scan_tools(dirs: list) -> list:
    tools, seen = [], set()
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            warnings.warn(f"tool 目錄不存在,已跳過: {root}")
            continue
        for file in sorted(root.rglob("*.py")):
            if file.name.startswith("_"):
                continue
            module = _import_module(file)
            if module is None:
                continue
            for obj in vars(module).values():
                if isinstance(obj, BaseTool) and id(obj) not in seen:
                    seen.add(id(obj))
                    tools.append(obj)
    logger.info("scan_tools: 載入 %d 個 tool", len(tools))
    return tools


def _import_module(file):
    name = f"_agent_template_tools_{file.stem}_{abs(hash(str(file)))}"
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        warnings.warn(f"tool 檔載入失敗,已跳過: {file} ({exc})")
        return None
    return module
