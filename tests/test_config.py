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
    assert cfg.groups[0].mode == "direct"
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


def test_load_recursive_config_expands_search_paths(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- mode: recursive
  source: .opencode/commands
  links:
    - .claude/commands
    - .pi/prompts
  search:
    - ~/workspace
    - /tmp/search-root
  depth: 3
""",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.groups[0].mode == "recursive"
    assert cfg.groups[0].source == ".opencode/commands"
    assert cfg.groups[0].links == [".claude/commands", ".pi/prompts"]
    assert cfg.groups[0].search == [
        str(home / "workspace"),
        "/tmp/search-root",
    ]
    assert cfg.groups[0].depth == 3


def test_load_recursive_config_defaults_depth_to_five(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- mode: recursive
  source: .opencode/commands
  links:
    - .claude/commands
  search:
    - /tmp/search-root
""",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.groups[0].depth == 5


def test_type_field_is_not_accepted_for_recursive_mode(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- type: recursive
  source: .opencode/commands
  links:
    - .claude/commands
  search:
    - /tmp/search-root
""",
        encoding="utf-8",
    )

    try:
        load_config(cfg_file)
    except RuntimeError as exc:
        assert "search is only supported in recursive mode" in str(exc)
    else:
        raise AssertionError("expected config loading to fail")


def test_load_config_accepts_explicit_direct_mode(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """- mode: direct
  source: docs
  links:
    - linked-docs
""",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.groups[0].mode == "direct"
    assert cfg.groups[0].source == str(tmp_path / "docs")
    assert cfg.groups[0].links == [str(tmp_path / "linked-docs")]


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
