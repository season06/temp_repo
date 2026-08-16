"""Wheel build hook:把 agent_template 編成 sourceless .pyc(-OO),不出任何 .py。

輸出一顆與 OS 無關、綁當前 CPython 次版的 wheel(cpXY-none-any)。
公開 API 的 .pyi + py.typed 一併附上,保留下游型別檢查與補全。
每個支援的 Python 次版各跑一次此 build(見 build_wheels.sh)。
"""

import py_compile
import shutil
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SRC = Path("src/agent_template")
BUILD = Path("build/pyc/agent_template")
STUBS = ("__init__.pyi", "py.typed")


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data: dict):
        shutil.rmtree(BUILD.parent, ignore_errors=True)
        for py in sorted(SRC.rglob("*.py")):
            rel = py.relative_to(SRC).with_suffix(".pyc")
            out = BUILD / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(
                str(py), cfile=str(out), optimize=2, doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            build_data["force_include"][str(out)] = f"agent_template/{rel.as_posix()}"
        for name in STUBS:
            build_data["force_include"][str(SRC / name)] = f"agent_template/{name}"
        build_data["pure_python"] = True
        build_data["tag"] = f"cp{sys.version_info.major}{sys.version_info.minor}-none-any"
