from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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
            raise RuntimeError(f"source file {source_path} does not exist")

        if source_path.is_symlink() and not self.force:
            raise RuntimeError(f"source file {source_path} is a symlink (use --force to override)")

        if not source_path.is_file() and not source_path.is_symlink():
            raise RuntimeError(f"source file {source_path} is not a regular file")

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
        import os

        rel_target = Path(os.path.relpath(target_path, link_path.parent))
        link_path.symlink_to(rel_target)

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
                    f"symlink {link_path} points to wrong target {info.target} (expected {target_path}), use --force to fix"
                )
            if not self.dry_run:
                link_path.unlink()
            self.create_link(link_path, target_path)
            return "fix"
        if info.status == LinkStatus.NOT_SYMLINK:
            if not self.force:
                raise RuntimeError(f"file {link_path} exists and is not a symlink, use --force to replace")
            if not self.dry_run:
                if link_path.is_dir():
                    import shutil

                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()
            self.create_link(link_path, target_path)
            return "replace"

        if not self.dry_run:
            link_path.unlink(missing_ok=True)
        self.create_link(link_path, target_path)
        return "fix broken"
