"""Smoke test: import the installed (compiled) package and run the agent.

Run this from a directory that does NOT contain agent_demo.py, so ``import
agent_demo`` resolves to the installed .so from the wheel rather than any source.

Note: Nuitka sets a compiled module's ``__file__`` to a synthetic ``.py`` path
for compatibility, so we verify compilation via the loader and the on-disk file.
"""

import glob
import os

import agent_demo

loader = type(agent_demo.__loader__).__name__
print("imported agent_demo, loader:", loader)
assert "nuitka" in loader.lower(), f"expected a Nuitka-compiled module, got loader {loader!r}"

pkg_dir = os.path.dirname(agent_demo.__file__)
so_files = glob.glob(os.path.join(pkg_dir, "agent_demo*.so"))
print("on-disk compiled file(s):", so_files)
assert so_files, "no compiled agent_demo*.so found in the install directory"
assert not os.path.exists(os.path.join(pkg_dir, "agent_demo.py")), "source .py leaked into the install"

output = agent_demo.run("What is 2 + 3?")
print("agent output:", output)
assert isinstance(output, str) and output, "agent returned no text"

print("OK: compiled wheel imports and runs")
