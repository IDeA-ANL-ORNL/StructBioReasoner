"""
Skill registry — discovers and loads skills from the skills/ directory.

Each skill is a directory under ``skills/`` containing a ``SKILL.md`` file
with YAML front-matter (name, description, metadata).
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default skills root: <repo>/skills
_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SkillInfo:
    """Parsed metadata for a single skill."""
    name: str
    description: str = ""
    directory: Path = field(default_factory=lambda: Path("."))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "directory": str(self.directory),
            "metadata": self.metadata,
        }


def _parse_yaml_frontmatter(text: str) -> Dict[str, Any]:
    """Minimal YAML front-matter parser (avoids external pyyaml dependency at import time).

    Handles the simple key: value format used in SKILL.md files.  Falls back
    gracefully for nested structures by storing them as raw strings.
    """
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    block = match.group(1)
    result: Dict[str, Any] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                result[key] = value
    return result


def _load_skill_md(skill_dir: Path) -> Optional[SkillInfo]:
    """Load a SkillInfo from a SKILL.md in *skill_dir*."""
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        return None
    text = md_path.read_text()
    fm = _parse_yaml_frontmatter(text)
    name = fm.get("name", skill_dir.name)
    description = fm.get("description", "")
    metadata = {k: v for k, v in fm.items() if k not in ("name", "description")}
    return SkillInfo(
        name=name,
        description=description,
        directory=skill_dir,
        metadata=metadata,
    )


class SkillRegistry:
    """
    Discovers and caches skill metadata from the skills/ directory tree.

    Usage::

        registry = SkillRegistry()          # uses default skills/ root
        registry.discover()                  # scan directories
        info = registry.get("bindcraft")     # look up a skill
        all_skills = registry.list_skills()  # list all discovered skills
    """

    def __init__(self, skills_root: Optional[Path] = None) -> None:
        self._root = Path(skills_root) if skills_root else _DEFAULT_SKILLS_ROOT
        self._skills: Dict[str, SkillInfo] = {}

    @property
    def root(self) -> Path:
        return self._root

    def discover(self) -> int:
        """Scan skills_root for skill directories. Returns count of skills found."""
        self._skills.clear()
        if not self._root.is_dir():
            logger.warning("Skills root %s does not exist", self._root)
            return 0
        for child in sorted(self._root.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            info = _load_skill_md(child)
            if info is not None:
                self._skills[info.name] = info
                logger.debug("Discovered skill: %s", info.name)
        logger.info("Discovered %d skills in %s", len(self._skills), self._root)
        return len(self._skills)

    def get(self, name: str) -> Optional[SkillInfo]:
        return self._skills.get(name)

    def list_skills(self) -> List[SkillInfo]:
        return list(self._skills.values())

    def list_names(self) -> List[str]:
        return list(self._skills.keys())

    def has_skill(self, name: str) -> bool:
        return name in self._skills

    def register(self, info: SkillInfo) -> None:
        """Manually register a skill (e.g., for testing)."""
        self._skills[info.name] = info
