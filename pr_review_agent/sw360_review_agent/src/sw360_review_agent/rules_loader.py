# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Project rules loader — loads all configurable rules from the project_rules/ directory.

This module provides a single entry point to load:
- File type classification patterns (file_types.yaml)
- Deterministic lint rules (lint_rules.yaml)
- LLM review prompt (review_prompt.md)
- File-type-specific review focus (review_focus.yaml)
- Indexing configuration (indexing.yaml)

All rules are loaded from a configurable directory, defaulting to
project_rules/ relative to the config file or working directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
import structlog

logger = structlog.get_logger(__name__)

# Default project_rules directory (relative to package)
_PACKAGE_DIR = Path(__file__).parent
_DEFAULT_RULES_DIR = _PACKAGE_DIR.parent.parent.parent / "project_rules"


# ---------------------------------------------------------------------------
# Data classes for loaded rules
# ---------------------------------------------------------------------------


@dataclass
class FileTypePattern:
    """A single file classification pattern."""

    pattern: re.Pattern[str]
    type_name: str


@dataclass
class LintRulePattern:
    """A regex pattern within a lint rule."""

    regex: re.Pattern[str]
    label: str = ""


@dataclass
class LintRule:
    """A single configurable lint rule definition."""

    id: str
    name: str
    type: str  # "commit" or "file"
    severity: str  # "error", "warning", "suggestion"
    patterns: list[LintRulePattern] = field(default_factory=list)
    match_type: str = "must_not_match"  # "must_contain" or "must_not_match"
    pattern: str = ""  # For commit rules (simple string match)
    exclude_paths: list[str] = field(default_factory=list)
    exclude_patterns: list[re.Pattern[str]] = field(default_factory=list)
    applies_to: list[str] | None = None  # None = all file types
    only_modified: bool = False
    message: str = ""
    suggestion: str = ""


@dataclass
class ReviewRule:
    """A single LLM review rule definition."""

    id: str
    name: str
    description: str


@dataclass
class IndexingConfig:
    """Configuration for codebase indexing."""

    project_name: str = "project"
    scan_dirs: list[dict[str, Any]] = field(default_factory=list)
    file_matchers: dict[str, dict[str, str]] = field(default_factory=dict)
    exclude_patterns: list[str] = field(default_factory=list)
    max_doc_length: int = 1500
    extraction_mode: str = "signatures"
    references_dir: str = "project_rules/references"


@dataclass
class ProjectRules:
    """Complete loaded project rules — everything the agent needs."""

    file_types: list[FileTypePattern] = field(default_factory=list)
    lint_rules: list[LintRule] = field(default_factory=list)
    review_prompt: str = ""
    review_rules: list[ReviewRule] = field(default_factory=list)
    review_focus: dict[str, str] = field(default_factory=dict)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    rules_dir: Path = field(default_factory=lambda: _DEFAULT_RULES_DIR)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Safely load a YAML file, returning empty dict if not found."""
    if not path.exists():
        logger.warning("rules_file_not_found", path=str(path))
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_file_types(rules_dir: Path) -> list[FileTypePattern]:
    """Load file type classification patterns from file_types.yaml."""
    data = _load_yaml(rules_dir / "file_types.yaml")
    patterns_data = data.get("patterns", [])

    file_types: list[FileTypePattern] = []
    for item in patterns_data:
        try:
            compiled = re.compile(item["pattern"])
            file_types.append(FileTypePattern(pattern=compiled, type_name=item["type"]))
        except (re.error, KeyError) as exc:
            logger.warning("invalid_file_type_pattern", item=item, error=str(exc))

    logger.debug("file_types_loaded", count=len(file_types))
    return file_types


def _load_lint_rules(rules_dir: Path) -> list[LintRule]:
    """Load deterministic lint rules from lint_rules.yaml."""
    data = _load_yaml(rules_dir / "lint_rules.yaml")
    rules_data = data.get("rules", [])

    lint_rules: list[LintRule] = []
    for item in rules_data:
        try:
            # Parse patterns
            patterns: list[LintRulePattern] = []
            for p in item.get("patterns", []):
                compiled = re.compile(p["regex"])
                patterns.append(LintRulePattern(regex=compiled, label=p.get("label", "")))

            # Parse exclude patterns
            exclude_patterns: list[re.Pattern[str]] = []
            for ep in item.get("exclude_patterns", []):
                exclude_patterns.append(re.compile(ep))

            rule = LintRule(
                id=item["id"],
                name=item.get("name", item["id"]),
                type=item.get("type", "file"),
                severity=item.get("severity", "warning"),
                patterns=patterns,
                match_type=item.get("match_type", "must_not_match"),
                pattern=item.get("pattern", ""),
                exclude_paths=item.get("exclude_paths", []),
                exclude_patterns=exclude_patterns,
                applies_to=item.get("applies_to"),
                only_modified=item.get("only_modified", False),
                message=item.get("message", ""),
                suggestion=item.get("suggestion", ""),
            )
            lint_rules.append(rule)
        except (KeyError, re.error) as exc:
            logger.warning("invalid_lint_rule", item=item, error=str(exc))

    logger.debug("lint_rules_loaded", count=len(lint_rules))
    return lint_rules


def _load_review_prompt(rules_dir: Path) -> str:
    """Load the LLM system prompt from review_prompt.md."""
    prompt_path = rules_dir / "review_prompt.md"
    if not prompt_path.exists():
        logger.warning("review_prompt_not_found", path=str(prompt_path))
        return ""
    return prompt_path.read_text(encoding="utf-8")


def _load_review_focus(rules_dir: Path) -> tuple[list[ReviewRule], dict[str, str]]:
    """Load review rules and file-type focus from review_focus.yaml."""
    data = _load_yaml(rules_dir / "review_focus.yaml")

    # Load rules
    rules: list[ReviewRule] = []
    for item in data.get("rules", []):
        rules.append(ReviewRule(
            id=item.get("id", ""),
            name=item.get("name", ""),
            description=item.get("description", ""),
        ))

    # Load focus prompts
    focus: dict[str, str] = {}
    for type_name, prompt in data.get("focus", {}).items():
        focus[type_name] = prompt

    logger.debug("review_focus_loaded", rules=len(rules), focus_types=len(focus))
    return rules, focus


def _load_indexing(rules_dir: Path) -> IndexingConfig:
    """Load indexing configuration from indexing.yaml."""
    data = _load_yaml(rules_dir / "indexing.yaml")
    if not data:
        return IndexingConfig()

    return IndexingConfig(
        project_name=data.get("project_name", "project"),
        scan_dirs=data.get("scan_dirs", []),
        file_matchers=data.get("file_matchers", {}),
        exclude_patterns=data.get("exclude_patterns", []),
        max_doc_length=data.get("max_doc_length", 1500),
        extraction_mode=data.get("extraction_mode", "signatures"),
        references_dir=data.get("references_dir", "project_rules/references"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_project_rules(rules_dir: str | Path | None = None) -> ProjectRules:
    """Load all project rules from the specified directory.

    Args:
        rules_dir: Path to the project_rules/ directory.
                   Defaults to project_rules/ relative to the package.

    Returns:
        Fully loaded ProjectRules instance.
    """
    if rules_dir is None:
        rules_path = _DEFAULT_RULES_DIR
    else:
        rules_path = Path(rules_dir)

    if not rules_path.exists():
        logger.warning("project_rules_dir_not_found", path=str(rules_path))
        return ProjectRules(rules_dir=rules_path)

    logger.info("loading_project_rules", path=str(rules_path))

    file_types = _load_file_types(rules_path)
    lint_rules = _load_lint_rules(rules_path)
    review_prompt = _load_review_prompt(rules_path)
    review_rules, review_focus = _load_review_focus(rules_path)
    indexing = _load_indexing(rules_path)

    return ProjectRules(
        file_types=file_types,
        lint_rules=lint_rules,
        review_prompt=review_prompt,
        review_rules=review_rules,
        review_focus=review_focus,
        indexing=indexing,
        rules_dir=rules_path,
    )
