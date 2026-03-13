#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML>=6.0"]
# ///
from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

import yaml

VERSION = "dev"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class LinkGroup:
    source: str
    links: list[str]

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source cannot be empty")
        if not self.links:
            raise ValueError("links cannot be empty")

    def expand_paths(self, config_dir: Path) -> None:
        self.source = str(_expand_path(self.source, config_dir))
        self.links = [str(_expand_path(link, config_dir)) for link in self.links]


@dataclass
class Config:
    groups: list[LinkGroup]

    def validate(self) -> None:
        if not self.groups:
            raise ValueError("at least one source group is required")
        for group in self.groups:
            group.validate()

    def expand_paths(self, config_dir: Path) -> None:
        for group in self.groups:
            group.expand_paths(config_dir)


def _expand_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return Path(os.path.abspath(path))


def _parse_yaml(text: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(text)
    if not isinstance(data, list):
        raise RuntimeError("root must be a YAML list of source/link groups")

    for index, group in enumerate(data, start=1):
        if not isinstance(group, dict):
            raise RuntimeError(f"group {index} must be a mapping")

    return cast(list[dict[str, Any]], data)


def _load_groups(data: list[dict[str, Any]]) -> list[LinkGroup]:
    return [
        LinkGroup(
            source=str(group.get("source", "")),
            links=list(cast(list[str], group.get("links", []))),
        )
        for group in data
    ]


def load_config(path: Path) -> Config:
    try:
        data = _parse_yaml(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"failed to read config file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid YAML in {path}: {exc}") from exc
    except RuntimeError as exc:
        raise RuntimeError(f"invalid config in {path}: {exc}") from exc

    cfg = Config(groups=_load_groups(data))
    try:
        cfg.validate()
    except ValueError as exc:
        raise RuntimeError(f"invalid config in {path}: {exc}") from exc

    cfg.expand_paths(path.parent)
    return cfg


def find_config_path() -> tuple[Path, bool]:
    project = Path.cwd() / ".symlegion.yaml"
    if project.exists():
        return project.resolve(), True
    return Path.home() / ".config" / "symlegion" / "config.yaml", False


def create_default_global_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Symlegion global configuration
# This file was auto-created. Uncomment and modify as needed.

# Example with one source group:
# - source: ~/.config/claude/CLAUDE.md
#   links:
#     - ~/.config/opencode/AGENTS.md
#     - ~/.config/some-tool/INSTRUCTIONS.md

- source: ~/.config/symlegion/INSTRUCTIONS.md
  links:
    - ~/.config/symlegion/CLAUDE.md
    - ~/.config/symlegion/AGENTS.md
""",
        encoding="utf-8",
    )


def create_project_config(path: Path) -> None:
    path.write_text(
        """# Choose one or more source groups to manage.
- source: CLAUDE.md
  links:
    - AGENTS.md                    # Root level
    - OPENCODE.md                  # Root level
    # - .agent/AGENTS.md           # Inside .agent directory
    # - .codex/instructions.md     # Different name and location
    # - config/ai/GEMINI.md        # Nested directories
# - source: docs/instructions
#   links:
#     - .ai/instructions
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


class LinkStatus(str, Enum):
    OK = "OK"
    MISSING = "missing"
    WRONG_TARGET = "wrong target"
    NOT_SYMLINK = "not a symlink"
    BROKEN = "broken"


@dataclass
class LinkInfo:
    path: Path
    expected_path: Path
    target: str = ""
    status: LinkStatus = LinkStatus.BROKEN
    error: Exception | None = None


class Manager:
    def __init__(self, dry_run: bool, force: bool, verbose: bool):
        self.dry_run = dry_run
        self.force = force
        self.verbose = verbose

    def validate_source(self, source_path: Path) -> None:
        if not source_path.exists() and not source_path.is_symlink():
            raise RuntimeError(f"source path {source_path} does not exist")
        if source_path.is_symlink() and not self.force:
            raise RuntimeError(
                f"source path {source_path} is a symlink (use --force to override)"
            )
        if (
            not source_path.is_file()
            and not source_path.is_dir()
            and not source_path.is_symlink()
        ):
            raise RuntimeError(f"source path {source_path} must be a file or directory")

    def check_link(self, link_path: Path, expected_target: Path) -> LinkInfo:
        info = LinkInfo(path=link_path, expected_path=expected_target)

        if not link_path.exists() and not link_path.is_symlink():
            info.status = LinkStatus.MISSING
            return info

        if not link_path.is_symlink():
            info.status = LinkStatus.NOT_SYMLINK
            return info

        try:
            target = link_path.readlink()
        except OSError as exc:
            info.error = exc
            info.status = LinkStatus.BROKEN
            return info

        info.target = str(target)
        resolved = (link_path.parent / target).resolve(strict=False)
        expected = expected_target.resolve(strict=False)
        info.status = LinkStatus.OK if resolved == expected else LinkStatus.WRONG_TARGET
        return info

    def create_link(self, link_path: Path, target_path: Path) -> None:
        if self.dry_run:
            return
        link_path.parent.mkdir(parents=True, exist_ok=True)
        rel_target = Path(os.path.relpath(target_path, link_path.parent))
        link_path.symlink_to(rel_target, target_is_directory=target_path.is_dir())

    def remove_link(self, link_path: Path, expected_target: Path) -> None:
        if self.dry_run:
            return
        if self.check_link(link_path, expected_target).status == LinkStatus.OK:
            link_path.unlink()

    def fix_link(self, link_path: Path, target_path: Path) -> str:
        info = self.check_link(link_path, target_path)

        if info.status == LinkStatus.OK:
            return "skip"
        if info.status == LinkStatus.MISSING:
            self.create_link(link_path, target_path)
            return "create"
        if info.status == LinkStatus.WRONG_TARGET:
            if not self.force:
                raise RuntimeError(
                    f"symlink {link_path} points to wrong target {info.target} "
                    f"(expected {target_path}), use --force to fix"
                )
            if not self.dry_run:
                link_path.unlink()
            self.create_link(link_path, target_path)
            return "fix"
        if info.status == LinkStatus.NOT_SYMLINK:
            if not self.force:
                raise RuntimeError(
                    f"file {link_path} exists and is not a symlink, use --force to replace"
                )
            if not self.dry_run:
                if link_path.is_dir():
                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()
            self.create_link(link_path, target_path)
            return "replace"

        if not self.dry_run:
            link_path.unlink(missing_ok=True)
        self.create_link(link_path, target_path)
        return "fix broken"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _info(msg: str) -> None:
    print(f"[info] {msg}")


def _ok(msg: str) -> None:
    print(f"[ok] {msg}")


def _create(msg: str) -> None:
    print(f"[create] {msg}")


def _skip(msg: str) -> None:
    print(f"[skip] {msg}")


def _error(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)


def _warning(msg: str) -> None:
    print(f"[warning] {msg}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="symlegion",
        description="Keep your AI instruction files in sync with zero magic — just symlinks",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)

    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("init", help="Create .symlegion.yaml in current directory")
    subs.add_parser("sync", help="Create/fix symlinks based on configuration")
    subs.add_parser("check", help="Check status of symlinks")
    subs.add_parser("clean", help="Remove managed symlinks")
    subs.add_parser("doctor", help="Check environment and permissions")
    return parser


def _run_init(args: argparse.Namespace) -> int:
    config_path = Path(".symlegion.yaml")
    if config_path.exists() and not args.force:
        _error(".symlegion.yaml already exists (use --force to overwrite)")
        return 1

    if not Path(".git").exists() and not args.force:
        response = (
            input(
                "No .git directory found. Create .symlegion.yaml here anyway? (y/N): "
            )
            .strip()
            .lower()
        )
        if response not in {"y", "yes"}:
            _info("Cancelled")
            return 0

    if args.dry_run:
        _info("Would create .symlegion.yaml")
        return 0

    create_project_config(config_path)
    _ok(f"Created {config_path.resolve()}")
    _info(
        "Edit the config file and run 'symlegion sync' after creating your source file"
    )
    return 0


def _load_or_create_config(
    config_path: Path, is_project: bool, dry_run: bool
) -> Config:
    if config_path.exists():
        return load_config(config_path)

    if is_project:
        _error("No .symlegion.yaml found in current directory")
        _info("Run 'symlegion init' to create one")
        raise RuntimeError("no project config found")

    _info(f"Creating default global config at {config_path}")
    if not dry_run:
        create_default_global_config(config_path)
    _warning(f"Please edit {config_path} to configure your source and links")
    raise RuntimeError("created default config - please edit it first")


def _process_link(
    manager: Manager, link_path: Path, source_path: Path, verbose: bool
) -> None:
    if verbose:
        _info(f"Processing link: {link_path}")
    action = manager.fix_link(link_path, source_path)
    if action == "create":
        _create(f"{link_path} -> {source_path}")
    elif action == "fix":
        _ok(f"Fixed {link_path} -> {source_path}")
    elif action == "replace":
        _ok(f"Replaced {link_path} -> {source_path}")
    elif action == "fix broken":
        _ok(f"Fixed broken {link_path} -> {source_path}")
    elif action == "skip" and verbose:
        _skip(f"{link_path} already links to {source_path}")


def _run_sync(args: argparse.Namespace) -> int:
    config_path, is_project = find_config_path()
    try:
        cfg = _load_or_create_config(config_path, is_project, args.dry_run)
    except RuntimeError as exc:
        _error(str(exc))
        return 1

    if args.verbose:
        _info(f"Using {'project' if is_project else 'global'} config: {config_path}")

    manager = Manager(args.dry_run, args.force, args.verbose)
    has_errors = False
    for group in cfg.groups:
        try:
            manager.validate_source(Path(group.source))
        except RuntimeError as exc:
            has_errors = True
            _error(f"Source validation failed for {group.source}: {exc}")
            continue

        _ok(f"Source: {group.source}")
        for link in group.links:
            try:
                _process_link(manager, Path(link), Path(group.source), args.verbose)
            except RuntimeError as exc:
                has_errors = True
                _error(f"Failed to process {link}: {exc}")

    if args.dry_run:
        _info("Dry run completed - no changes made")

    return 1 if has_errors else 0


def _run_check(args: argparse.Namespace) -> int:
    config_path, is_project = find_config_path()
    if not config_path.exists():
        _error(
            "No .symlegion.yaml found in current directory"
            if is_project
            else f"No global config found at {config_path}"
        )
        return 1

    cfg = load_config(config_path)
    manager = Manager(False, False, args.verbose)

    has_problems = False
    for index, group in enumerate(cfg.groups, start=1):
        source_status = "OK"
        try:
            manager.validate_source(Path(group.source))
        except RuntimeError as exc:
            source_status = f"ERROR: {exc}"
            has_problems = True

        print(f"Source: {group.source} [{source_status}]")
        print("Links:")

        max_len = max((len(link) for link in group.links), default=0)
        for link in group.links:
            info = manager.check_link(Path(link), Path(group.source))
            if info.status != LinkStatus.OK:
                has_problems = True
            print(f"  {link:<{max_len}} -> ", end="")
            if info.status == LinkStatus.OK:
                print(f"{group.source} ✓")
            elif info.status == LinkStatus.MISSING:
                print("missing")
            elif info.status == LinkStatus.WRONG_TARGET:
                print(f"{info.target} (expected {group.source}) ✗")
            elif info.status == LinkStatus.NOT_SYMLINK:
                print("not a symlink ✗")
            else:
                print("broken ✗")

        if index < len(cfg.groups):
            print()

    if has_problems:
        print("\nFound problems. Run 'symlegion sync' to fix them.")
        return 1

    print("\nAll links are correctly configured ✓")
    return 0


def _run_clean(args: argparse.Namespace) -> int:
    config_path, _ = find_config_path()
    if not config_path.exists():
        _error(f"No config found at {config_path}")
        return 1

    cfg = load_config(config_path)
    manager = Manager(args.dry_run, args.force, args.verbose)

    removed = 0
    skipped = 0

    for group in cfg.groups:
        _info(f"Source: {group.source} (will NOT be removed)")
        for link in group.links:
            link_path = Path(link)
            info = manager.check_link(link_path, Path(group.source))
            if info.status == LinkStatus.OK:
                manager.remove_link(link_path, Path(group.source))
                _ok(f"Removed {link}")
                removed += 1
            elif info.status == LinkStatus.BROKEN:
                if not args.dry_run:
                    link_path.unlink(missing_ok=True)
                _ok(f"Removed broken symlink {link}")
                removed += 1
            else:
                skipped += 1
                if args.verbose:
                    _skip(f"Skipped {link}")

    if args.dry_run:
        _info(
            f"Dry run completed - would remove {removed} symlinks, skip {skipped} items"
        )
    else:
        _info(f"Clean completed - removed {removed} symlinks, skipped {skipped} items")
    return 0


def _check_symlink_support() -> None:
    tmp = Path(os.getenv("TMPDIR", "/tmp"))
    target = tmp / "symlegion_test_target"
    link = tmp / "symlegion_test_link"
    target.write_text("test", encoding="utf-8")
    try:
        link.unlink(missing_ok=True)
        link.symlink_to(target)
        _ = link.readlink()
    finally:
        target.unlink(missing_ok=True)
        link.unlink(missing_ok=True)


def _run_doctor(args: argparse.Namespace) -> int:
    print("Symlegion Doctor\n================\n")
    has_issues = False

    print(f"Operating System: {sys.platform} {platform.machine()}")
    print("✓ Supported platform\n")

    print("Symlink Support:")
    try:
        _check_symlink_support()
        print("✓ Symlinks are supported\n")
    except OSError as exc:
        print(f"✗ Symlinks not supported: {exc}\n")
        has_issues = True

    print("Binary Location:")
    print(f"Binary: {sys.executable}")
    print(
        ("✓" if shutil.which("symlegion") else "⚠️")
        + " Binary is{} in PATH".format("" if shutil.which("symlegion") else " not")
    )
    print()

    cfg_dir = Path.home() / ".config" / "symlegion"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    print("Configuration:")
    print(f"✓ Config directory accessible: {cfg_dir}\n")

    print("Project Configuration:")
    print(
        "✓ Git repository detected" if Path(".git").exists() else "⚠️  No .git directory"
    )
    print(
        "✓ Project config found: .symlegion.yaml"
        if Path(".symlegion.yaml").exists()
        else "⚠️  No project config (.symlegion.yaml)"
    )
    print()

    print("Global Configuration:")
    global_cfg, _ = find_config_path()
    print(
        f"✓ Global config found: {global_cfg}"
        if global_cfg.exists()
        else f"⚠️  No global config found: {global_cfg}"
    )
    print()

    if has_issues:
        print("🔧 Some issues found. See messages above for details.")
        return 1
    print("✅ Environment looks good!")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "init":
        return _run_init(args)
    if args.command == "sync":
        return _run_sync(args)
    if args.command == "check":
        return _run_check(args)
    if args.command == "clean":
        return _run_clean(args)
    if args.command == "doctor":
        return _run_doctor(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
