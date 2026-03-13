from pathlib import Path

from symlegion import Config, find_config_path, load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("source: test.md\nlinks:\n  - a.md\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.source == str(tmp_path / "test.md")
    assert cfg.links == [str(tmp_path / "a.md")]


def test_validate():
    Config(source="a", links=["b"]).validate()


def test_find_config_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, is_project = find_config_path()
    assert not is_project
    (tmp_path / ".symlegion.yaml").write_text(
        "source: a\nlinks: [b]\n", encoding="utf-8"
    )
    path, is_project = find_config_path()
    assert is_project
    assert path == (tmp_path / ".symlegion.yaml").resolve()
