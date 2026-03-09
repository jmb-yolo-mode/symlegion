from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

from . import config
from .symlink import LinkStatus, Manager

VERSION = "dev"


def print_info(msg: str) -> None:
    print(f"[info] {msg}")


def print_ok(msg: str) -> None:
    print(f"[ok] {msg}")


def print_create(msg: str) -> None:
    print(f"[create] {msg}")


def print_skip(msg: str) -> None:
    print(f"[skip] {msg}")


def print_error(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    print(f"[warning] {msg}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentlink", description="Keep your AI instruction files in sync with zero magic — just symlinks")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)

    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("init", help="Create .agentlink.yaml in current directory")
    subs.add_parser("sync", help="Create/fix symlinks based on configuration")
    subs.add_parser("check", help="Check status of symlinks")
    subs.add_parser("clean", help="Remove managed symlinks")
    subs.add_parser("doctor", help="Check environment and permissions")
    return parser


def run_init(args: argparse.Namespace) -> int:
    config_path = Path(".agentlink.yaml")
    if config_path.exists() and not args.force:
        print_error(".agentlink.yaml already exists (use --force to overwrite)")
        return 1

    if not Path(".git").exists() and not args.force:
        response = input("No .git directory found. Create .agentlink.yaml here anyway? (y/N): ").strip().lower()
        if response not in {"y", "yes"}:
            print_info("Cancelled")
            return 0

    if args.dry_run:
        print_info("Would create .agentlink.yaml")
        return 0

    config.create_project_config(config_path)
    print_ok(f"Created {config_path.resolve()}")
    print_info("Edit the config file and run 'agentlink sync' after creating your source file")
    return 0


def load_or_create_config(config_path: Path, is_project: bool, dry_run: bool):
    if config_path.exists():
        return config.load_config(config_path)

    if is_project:
        print_error("No .agentlink.yaml found in current directory")
        print_info("Run 'agentlink init' to create one")
        raise RuntimeError("no project config found")

    print_info(f"Creating default global config at {config_path}")
    if not dry_run:
        config.create_default_global_config(config_path)
    print_warning(f"Please edit {config_path} to configure your source and links")
    raise RuntimeError("created default config - please edit it first")


def process_link(manager: Manager, link_path: Path, source_path: Path, verbose: bool) -> None:
    if verbose:
        print_info(f"Processing link: {link_path}")
    action = manager.fix_link(link_path, source_path)
    if action == "create":
        print_create(f"{link_path} -> {source_path}")
    elif action == "fix":
        print_ok(f"Fixed {link_path} -> {source_path}")
    elif action == "replace":
        print_ok(f"Replaced {link_path} -> {source_path}")
    elif action == "fix broken":
        print_ok(f"Fixed broken {link_path} -> {source_path}")
    elif action == "skip" and verbose:
        print_skip(f"{link_path} already links to {source_path}")


def run_sync(args: argparse.Namespace) -> int:
    config_path, is_project = config.find_config_path()
    try:
        cfg = load_or_create_config(config_path, is_project, args.dry_run)
    except RuntimeError as exc:
        print_error(str(exc))
        return 1

    if args.verbose:
        print_info(f"Using {'project' if is_project else 'global'} config: {config_path}")

    manager = Manager(args.dry_run, args.force, args.verbose)
    try:
        manager.validate_source(Path(cfg.source))
    except RuntimeError as exc:
        print_error(f"Source validation failed: {exc}")
        return 1

    print_ok(f"Source: {cfg.source}")
    has_errors = False
    for link in cfg.links:
        try:
            process_link(manager, Path(link), Path(cfg.source), args.verbose)
        except RuntimeError as exc:
            has_errors = True
            print_error(f"Failed to process {link}: {exc}")

    if args.dry_run:
        print_info("Dry run completed - no changes made")

    return 1 if has_errors else 0


def run_check(args: argparse.Namespace) -> int:
    config_path, is_project = config.find_config_path()
    if not config_path.exists():
        print_error("No .agentlink.yaml found in current directory" if is_project else f"No global config found at {config_path}")
        return 1

    cfg = config.load_config(config_path)
    manager = Manager(False, False, args.verbose)

    source_status = "OK"
    has_problems = False
    try:
        manager.validate_source(Path(cfg.source))
    except RuntimeError as exc:
        source_status = f"ERROR: {exc}"
        has_problems = True

    print(f"Source: {cfg.source} [{source_status}]")
    print("Links:")

    max_len = max((len(link) for link in cfg.links), default=0)
    for link in cfg.links:
        info = manager.check_link(Path(link), Path(cfg.source))
        if info.status != LinkStatus.OK:
            has_problems = True
        print(f"  {link:<{max_len}} -> ", end="")
        if info.status == LinkStatus.OK:
            print(f"{cfg.source} ✓")
        elif info.status == LinkStatus.MISSING:
            print("missing")
        elif info.status == LinkStatus.WRONG_TARGET:
            print(f"{info.target} (expected {cfg.source}) ✗")
        elif info.status == LinkStatus.NOT_SYMLINK:
            print("not a symlink ✗")
        else:
            print("broken ✗")

    if has_problems:
        print("\nFound problems. Run 'agentlink sync' to fix them.")
        return 1

    print("\nAll links are correctly configured ✓")
    return 0


def run_clean(args: argparse.Namespace) -> int:
    config_path, _ = config.find_config_path()
    if not config_path.exists():
        print_error(f"No config found at {config_path}")
        return 1
    cfg = config.load_config(config_path)
    manager = Manager(args.dry_run, args.force, args.verbose)

    print_info(f"Source: {cfg.source} (will NOT be removed)")
    removed = 0
    skipped = 0

    for link in cfg.links:
        link_path = Path(link)
        info = manager.check_link(link_path, Path(cfg.source))
        if info.status == LinkStatus.OK:
            manager.remove_link(link_path, Path(cfg.source))
            print_ok(f"Removed {link}")
            removed += 1
        elif info.status == LinkStatus.BROKEN:
            if not args.dry_run:
                link_path.unlink(missing_ok=True)
            print_ok(f"Removed broken symlink {link}")
            removed += 1
        else:
            skipped += 1
            if args.verbose:
                print_skip(f"Skipped {link}")

    if args.dry_run:
        print_info(f"Dry run completed - would remove {removed} symlinks, skip {skipped} items")
    else:
        print_info(f"Clean completed - removed {removed} symlinks, skipped {skipped} items")
    return 0


def _check_symlink_support() -> None:
    tmp = Path(os.getenv("TMPDIR", "/tmp"))
    target = tmp / "agentlink_test_target"
    link = tmp / "agentlink_test_link"
    target.write_text("test", encoding="utf-8")
    try:
        link.unlink(missing_ok=True)
        link.symlink_to(target)
        _ = link.readlink()
    finally:
        target.unlink(missing_ok=True)
        link.unlink(missing_ok=True)


def run_doctor(args: argparse.Namespace) -> int:
    print("Agentlink Doctor\n================\n")
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
    print(("✓" if shutil.which("agentlink") else "⚠️") + " Binary is{} in PATH".format("" if shutil.which("agentlink") else " not"))
    print()

    cfg_dir = Path.home() / ".config" / "agentlink"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    print("Configuration:")
    print(f"✓ Config directory accessible: {cfg_dir}\n")

    print("Project Configuration:")
    print("✓ Git repository detected" if Path(".git").exists() else "⚠️  No .git directory")
    print("✓ Project config found: .agentlink.yaml" if Path(".agentlink.yaml").exists() else "⚠️  No project config (.agentlink.yaml)")
    print()

    print("Global Configuration:")
    global_cfg, _ = config.find_config_path()
    print(f"✓ Global config found: {global_cfg}" if global_cfg.exists() else f"⚠️  No global config found: {global_cfg}")
    print()

    if has_issues:
        print("🔧 Some issues found. See messages above for details.")
        return 1
    print("✅ Environment looks good!")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        return run_init(args)
    if args.command == "sync":
        return run_sync(args)
    if args.command == "check":
        return run_check(args)
    if args.command == "clean":
        return run_clean(args)
    if args.command == "doctor":
        return run_doctor(args)
    return 1
