"""Skill 掃描:config 給根目錄,收其下含 SKILL.md 的子目錄路徑。

skill 走 deepagents 原生機制(skills= 收路徑,progressive disclosure),
不轉成 langchain tool,此處只做路徑收集與驗證。
"""

import logging
import warnings
from pathlib import Path

logger = logging.getLogger("agent_template")


def scan_skills(dirs: list) -> list:
    paths = []
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            warnings.warn(f"skill 根目錄不存在,已跳過: {root}")
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if (child / "SKILL.md").is_file():
                paths.append(str(child))
            else:
                warnings.warn(f"skill 目錄缺 SKILL.md,已跳過: {child}")
    logger.info("scan_skills: 載入 %d 個 skill", len(paths))
    return paths
