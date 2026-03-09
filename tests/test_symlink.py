from pathlib import Path

from agentlink.symlink import LinkStatus, Manager


def test_check_and_fix_link(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("x", encoding="utf-8")
    link = tmp_path / "AGENTS.md"

    manager = Manager(False, False, False)
    assert manager.check_link(link, source).status == LinkStatus.MISSING

    assert manager.fix_link(link, source) == "create"
    assert manager.check_link(link, source).status == LinkStatus.OK
