"""Cython-compile the security-critical `agent_template/_secure/` submodules.

P3 (compile & integrity): the envelope's detection rules, prompts, guard/validation
middleware, and the SecureAgent wrapper are compiled to native extensions so the
logic is shipped as binary (.so/.pyd), not editable source. Pure-Python-mode Cython
is used — the .py files stay as the source of truth and the compiled .so takes import
precedence over the .py at runtime.

Run:  .venv/bin/python build_secure.py
(produces agent_template/_secure/*.cpython-*.so in-place)

Note: this environment's CPython 3.14 dev headers are extracted under .pyhdr/ (no root
install). On a normal machine with python3.x-dev installed, INCLUDE_DIRS can be empty.
"""
import os

from setuptools import Extension, setup
from Cython.Build import cythonize

_HDR = os.path.abspath(".pyhdr/root/usr/include")
INCLUDE_DIRS = [
    os.path.join(_HDR, "python3.14"),
    os.path.join(_HDR, "x86_64-linux-gnu/python3.14"),
    _HDR,  # so pyconfig.h's `#include <x86_64-linux-gnu/python3.14/pyconfig.h>` resolves
]
# Only include header dirs that actually exist (so this also works where
# the system already provides Python.h and .pyhdr is absent).
INCLUDE_DIRS = [d for d in INCLUDE_DIRS if os.path.isdir(d)]

# Security-critical modules to compile. __init__ stays a thin pure-Python
# re-export; compiling the factory wiring is the R1 follow-up (see
# docs/superpowers/specs/p2-redteam-deferred-to-p3.md).
_SECURE = "agent_template/_secure"
MODULE_FILES = [
    f"{_SECURE}/_rules.py",
    f"{_SECURE}/_envelope.py",
    f"{_SECURE}/_guard.py",
    f"{_SECURE}/_validation.py",
    f"{_SECURE}/_agent.py",
]


def _ext(pyfile):
    modname = pyfile[:-3].replace("/", ".")
    return Extension(modname, [pyfile], include_dirs=INCLUDE_DIRS)


setup(
    name="agent_template_secure_ext",
    ext_modules=cythonize(
        [_ext(f) for f in MODULE_FILES],
        language_level="3",
        compiler_directives={"language_level": "3"},
    ),
    script_args=["build_ext", "--inplace"],
)
