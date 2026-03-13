from pathlib import Path

from symlegion import Config, LinkGroup, find_config_path, load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- source: test.md
  links:
    - a.md
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert len(cfg.groups) == 1
    assert cfg.groups[0].source == str(tmp_path / "test.md")
    assert cfg.groups[0].links == [str(tmp_path / "a.md")]


def test_load_config_with_multiple_groups(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- source: docs
  links:
    - linked-docs
- source: CLAUDE.md
  links: [AGENTS.md, OPENCODE.md]
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert [group.source for group in cfg.groups] == [
        str(tmp_path / "docs"),
        str(tmp_path / "CLAUDE.md"),
    ]
    assert cfg.groups[0].links == [str(tmp_path / "linked-docs")]
    assert cfg.groups[1].links == [
        str(tmp_path / "AGENTS.md"),
        str(tmp_path / "OPENCODE.md"),
    ]


def test_validate():
    Config(groups=[LinkGroup(source="a", links=["b"])]).validate()


def test_find_config_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, is_project = find_config_path()
    assert not is_project
    (tmp_path / ".symlegion.yaml").write_text(
        "- source: a\n  links: [b]\n", encoding="utf-8"
    )
    path, is_project = find_config_path()
    assert is_project
    assert path == (tmp_path / ".symlegion.yaml").resolve()
