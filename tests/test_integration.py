from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(cwd: Path, *args: str):
    env = dict(**__import__("os").environ, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "symlegion", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def test_init_sync_check_clean(tmp_path: Path):
    (tmp_path / ".git").mkdir()

    p = run(tmp_path, "init")
    assert p.returncode == 0
    assert (tmp_path / ".symlegion.yaml").exists()

    p = run(tmp_path, "check")
    assert p.returncode == 1

    (tmp_path / "CLAUDE.md").write_text("hello", encoding="utf-8")
    p = run(tmp_path, "sync")
    assert p.returncode == 0
    assert "[create]" in p.stdout

    for link in ["AGENTS.md", "OPENCODE.md"]:
        assert (tmp_path / link).is_symlink()

    p = run(tmp_path, "check")
    assert p.returncode == 0
    assert "All links are correctly configured" in p.stdout

    p = run(tmp_path, "--dry-run", "clean")
    assert p.returncode == 0
    assert "would remove" in p.stdout
