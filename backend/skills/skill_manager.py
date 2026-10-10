# Load skill metadata cheaply and disclose instruction bodies by task match.
"""Progressive, composable project skill loading."""

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
SKILL_DIR = Path(__file__).parent
RANK = {"global": 0, "project": 1, "user-attached": 2, "system": 3}


class SkillManager:
    """Read skill metadata once and load matching bodies on demand."""

    def __init__(self, directory: Path = SKILL_DIR) -> None:
        """Index the Markdown frontmatter without retaining skill bodies."""
        self.directory = directory
        self._metadata = [self._read_metadata(path) for path in sorted(directory.glob("*.md"))]
        self._active: list[str] = []

    def _read_metadata(self, path: Path) -> dict[str, Any]:
        """Parse the small frontmatter block and estimate body token cost."""
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^---\s*$\n(.*?)\n---\s*$", text, re.DOTALL)
        if not match:
            raise ValueError(f"Skill {path.name} has no frontmatter.")
        fields: dict[str, Any] = {}
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            value = value.strip()
            fields[key] = [part.strip() for part in value[1:-1].split(",")] if value.startswith("[") and value.endswith("]") else value
        if not all(key in fields for key in ("name", "description", "triggers", "tags")):
            raise ValueError(f"Skill {path.name} has incomplete metadata.")
        fields.update({"token_cost": max(1, len(text[match.end():].split()) * 4 // 3),
                       "scope": "project", "priority": 0, "path": str(path)})
        return fields

    def list_skills(self) -> list[dict[str, Any]]:
        """Return skill metadata with no instruction bodies or local paths."""
        return [{key: value for key, value in item.items() if key != "path"}
                for item in self._metadata]

    def load_skills_for(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Read full Markdown bodies only when a trigger matches task fields."""
        haystack = " ".join(str(task.get(key, "")) for key in ("language", "framework", "file_path", "description", "agent"))
        selected = [item for item in self._metadata if any(
            trigger.lower() in haystack.lower() for trigger in item["triggers"])]
        selected.sort(key=lambda item: (-RANK.get(item["scope"], 0), -item["priority"], item["name"]))
        accepted: list[dict[str, Any]] = []
        rules: dict[str, dict[str, Any]] = {}
        for item in selected:
            text = Path(item["path"]).read_text(encoding="utf-8")
            body = text.split("---", 2)[-1].strip()
            conflict = False
            for line in body.splitlines():
                normalized = re.sub(r"\s+", " ", line.strip("- ").lower())
                if not normalized:
                    continue
                key = normalized.split(" ", 2)[:2]
                key_text = " ".join(key)
                existing = rules.get(key_text)
                if existing and existing["rule"] != normalized:
                    if existing["scope"] == item["scope"]:
                        log.warning("Conflicting same-scope skills: %s and %s; skipping %s",
                                    existing["name"], item["name"], item["name"])
                    conflict = True
                    break
            if conflict:
                continue
            item_public = {key: value for key, value in item.items() if key != "path"}
            accepted.append({**item_public, "body": body})
            for line in body.splitlines():
                normalized = re.sub(r"\s+", " ", line.strip("- ").lower())
                if normalized:
                    rules[" ".join(normalized.split(" ", 2)[:2])] = {
                        "rule": normalized, "scope": item["scope"], "name": item["name"]}
        self._active = [item["name"] for item in accepted]
        return accepted

    def get_active_skill_names(self) -> list[str]:
        """Return the names selected by the most recent task match."""
        return list(self._active)


skill_manager = SkillManager()
