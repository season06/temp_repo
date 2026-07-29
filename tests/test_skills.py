import pytest

from agent_template.loaders.skills import scan_skills


def make_skill(root, name, with_md=True):
    d = root / name
    d.mkdir(parents=True)
    if with_md:
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\n---\nbody",
            encoding="utf-8",
        )
    return d


def test_collects_subdirs_with_skill_md(tmp_path):
    root = tmp_path / "skills"
    a = make_skill(root, "alpha")
    b = make_skill(root, "beta")
    assert scan_skills([str(root)]) == [str(a), str(b)]


def test_subdir_without_skill_md_warns_and_skips(tmp_path):
    root = tmp_path / "skills"
    good = make_skill(root, "good")
    make_skill(root, "bad", with_md=False)
    with pytest.warns(UserWarning, match="bad"):
        assert scan_skills([str(root)]) == [str(good)]


def test_plain_files_under_root_ignored(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "note.txt").write_text("x", encoding="utf-8")
    assert scan_skills([str(root)]) == []


def test_missing_root_warns_and_returns_empty(tmp_path):
    with pytest.warns(UserWarning, match="不存在"):
        assert scan_skills([str(tmp_path / "nope")]) == []
