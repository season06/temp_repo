"""Hatchling build hook: package the Nuitka-compiled .so into the wheel.

Nuitka emits agent_demo.cpython-<ver>-<plat>.so (a name that changes per Python
version / platform), so we glob for it at build time instead of hard-coding the
name. We also mark the wheel non-pure so it gets a real platform tag.
"""

import glob

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        matches = glob.glob("build/agent_demo.cpython-*.so")
        if not matches:
            raise FileNotFoundError(
                "no build/agent_demo.cpython-*.so found — run Nuitka before building the wheel"
            )
        # ship the compiled module at the wheel root, keeping its canonical name
        build_data["force_include"][matches[0]] = matches[0].split("/", 1)[1]
        # non-pure -> infer cp<ver>-<abi>-<platform> tag (no separate retag step)
        build_data["pure_python"] = False
        build_data["infer_tag"] = True
