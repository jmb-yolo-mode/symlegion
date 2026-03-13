from pathlib import Path

from symlegion import LinkStatus, Manager


def test_check_and_fix_link(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("x", encoding="utf-8")
    link = tmp_path / "AGENTS.md"

    manager = Manager(False, False, False)
    assert manager.check_link(link, source).status == LinkStatus.MISSING

    assert manager.fix_link(link, source) == "create"
    assert manager.check_link(link, source).status == LinkStatus.OK


def test_fix_link_with_directory_source(tmp_path: Path):
    source_dir = tmp_path / "instructions"
    source_dir.mkdir()
    (source_dir / "README.md").write_text("x", encoding="utf-8")
    link = tmp_path / ".ai"

    manager = Manager(False, False, False)
    manager.validate_source(source_dir)
    assert manager.fix_link(link, source_dir) == "create"
    assert link.is_symlink()
    assert manager.check_link(link, source_dir).status == LinkStatus.OK
