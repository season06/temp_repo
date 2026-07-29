import pytest

from agent_template.loaders.tools import scan_tools

TOOL_FILE = '''
from langchain_core.tools import tool

VERSION = "1.0"

def helper():
    return "not a tool"

@tool
def add(a: int, b: int) -> int:
    """兩數相加。"""
    return a + b
'''

NESTED_TOOL_FILE = '''
from langchain_core.tools import tool

@tool
def shout(text: str) -> str:
    """轉大寫。"""
    return text.upper()
'''

BROKEN_FILE = "this is not valid python ((("


def make_tools_dir(tmp_path):
    d = tmp_path / "tools"
    d.mkdir()
    return d


def test_collects_only_basetool_instances(tmp_path):
    d = make_tools_dir(tmp_path)
    (d / "math.py").write_text(TOOL_FILE, encoding="utf-8")
    tools = scan_tools([str(d)])
    assert [t.name for t in tools] == ["add"]  # helper 與 VERSION 都不收


def test_recursive_scan(tmp_path):
    d = make_tools_dir(tmp_path)
    sub = d / "text"
    sub.mkdir()
    (sub / "shout.py").write_text(NESTED_TOOL_FILE, encoding="utf-8")
    assert [t.name for t in scan_tools([str(d)])] == ["shout"]


def test_skips_underscore_files(tmp_path):
    d = make_tools_dir(tmp_path)
    (d / "_private.py").write_text(TOOL_FILE, encoding="utf-8")
    assert scan_tools([str(d)]) == []


def test_broken_file_warns_and_skips_others_still_load(tmp_path):
    d = make_tools_dir(tmp_path)
    (d / "broken.py").write_text(BROKEN_FILE, encoding="utf-8")
    (d / "math.py").write_text(TOOL_FILE, encoding="utf-8")
    with pytest.warns(UserWarning, match="broken.py"):
        tools = scan_tools([str(d)])
    assert [t.name for t in tools] == ["add"]


def test_missing_dir_warns_and_returns_empty(tmp_path):
    with pytest.warns(UserWarning, match="不存在"):
        assert scan_tools([str(tmp_path / "nope")]) == []


def test_same_instance_exposed_twice_collected_once(tmp_path):
    d = make_tools_dir(tmp_path)
    (d / "math.py").write_text(
        TOOL_FILE + "\nalias = add\n",  # 同一個 BaseTool 實例在 module 層級曝露兩次
        encoding="utf-8",
    )
    tools = scan_tools([str(d)])
    assert [t.name for t in tools] == ["add"]
