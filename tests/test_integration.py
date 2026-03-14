import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(cwd: Path, *args: str):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
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
    config_text = (tmp_path / ".symlegion.yaml").read_text(encoding="utf-8")
    assert "mode: direct" in config_text
    assert "mode: recursive" in config_text

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


def test_sync_multiple_groups_with_directory_source(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle" / "rules.md").write_text("hi", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("hello", encoding="utf-8")
    (tmp_path / ".symlegion.yaml").write_text(
        """- source: CLAUDE.md
  links:
    - AGENTS.md
- source: bundle
  links:
    - .ai/rules
""",
        encoding="utf-8",
    )

    p = run(tmp_path, "sync")
    assert p.returncode == 0
    assert (tmp_path / "AGENTS.md").is_symlink()
    assert (tmp_path / ".ai" / "rules").is_symlink()

    p = run(tmp_path, "check")
    assert p.returncode == 0
    assert p.stdout.count("Source:") == 2


def test_recursive_sync_creates_links_and_warns_for_missing_search_path(tmp_path: Path):
    existing_root = tmp_path / "workspace"
    repo_root = existing_root / "client" / "project"
    source_dir = repo_root / ".opencode" / "commands"
    source_dir.mkdir(parents=True)
    (source_dir / "prompt.md").write_text("hello", encoding="utf-8")

    missing_root = tmp_path / "missing"

    (tmp_path / ".symlegion.yaml").write_text(
        f"""- mode: recursive
  source: .opencode/commands
  links:
    - .claude/commands
    - .pi/prompts
  search:
    - {missing_root}
    - {existing_root}
  depth: 3
""",
        encoding="utf-8",
    )

    p = run(tmp_path, "sync")
    assert p.returncode == 0
    assert "Search path does not exist" in p.stderr
    assert (repo_root / ".claude" / "commands").is_symlink()
    assert (repo_root / ".pi" / "prompts").is_symlink()

    p = run(tmp_path, "check")
    assert p.returncode == 0
    assert "Search path does not exist" in p.stderr
    assert str(repo_root / ".opencode" / "commands") in p.stdout
