from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    source: str
    links: list[str]

    def validate(self) -> None:
        if not self.source:
            raise ValueError("source cannot be empty")
        if not self.links:
            raise ValueError("links cannot be empty")

    def expand_paths(self, config_dir: Path) -> None:
        self.source = str(expand_path(self.source, config_dir))
        self.links = [str(expand_path(link, config_dir)) for link in self.links]


def expand_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    import os

    return Path(os.path.abspath(path))


def _parse_simple_yaml(text: str) -> dict[str, object]:
    source = ""
    links: list[str] = []
    in_links = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("source:"):
            source = line.split(":", 1)[1].strip()
            in_links = False
            continue
        if line.startswith("links:"):
            in_links = True
            inline = line.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                items = [x.strip().strip("'\"") for x in inline[1:-1].split(",") if x.strip()]
                links.extend(items)
                in_links = False
            continue
        if in_links and line.lstrip().startswith("-"):
            links.append(line.split("-", 1)[1].strip())

    return {"source": source, "links": links}


def load_config(path: Path) -> Config:
    try:
        data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"failed to read config file {path}: {exc}") from exc

    cfg = Config(source=str(data.get("source", "")), links=list(data.get("links", [])))
    try:
        cfg.validate()
    except ValueError as exc:
        raise RuntimeError(f"invalid config in {path}: {exc}") from exc

    cfg.expand_paths(path.parent)
    return cfg


def find_config_path() -> tuple[Path, bool]:
    project = Path.cwd() / ".legion.yaml"
    if project.exists():
        return project.resolve(), True

    home = Path.home()
    return home / ".config" / "legion" / "config.yaml", False


def create_default_global_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Legion global configuration
# This file was auto-created. Uncomment and modify as needed.

# Example: Use a file in your Claude config as source
# source: ~/.config/claude/CLAUDE.md
# links:
#   - ~/.config/opencode/AGENTS.md
#   - ~/.config/some-tool/INSTRUCTIONS.md

source: ~/.config/legion/INSTRUCTIONS.md
links:
  - ~/.config/legion/CLAUDE.md
  - ~/.config/legion/AGENTS.md
""",
        encoding="utf-8",
    )


def create_project_config(path: Path) -> None:
    path.write_text(
        """# Choose the file you actually edit as the source:
source: CLAUDE.md
links:
  - AGENTS.md                    # Root level
  - OPENCODE.md                  # Root level
  # - .agent/AGENTS.md           # Inside .agent directory
  # - .codex/instructions.md     # Different name and location
  # - config/ai/GEMINI.md        # Nested directories
""",
        encoding="utf-8",
    )
