# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Shared data models for the PR Review Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Review comment severity levels."""

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class FileClassification(str, Enum):
    """Classification of changed files."""

    CONTROLLER = "controller"
    SERVICE = "service"
    TEST = "test"
    THRIFT = "thrift"
    HANDLER = "handler"
    JACKSON_MIXIN = "jackson_mixin"
    JAVA = "java"
    OTHER = "other"


@dataclass
class ReviewComment:
    """A single review finding/comment."""

    file: str
    line: int
    severity: Severity
    rule: str
    message: str
    suggestion: str = ""
    source: str = "deterministic"  # "deterministic" or "llm"
    confidence: float = 1.0
    reference: str = ""


@dataclass
class ChangedFile:
    """A file changed in a pull request."""

    path: str
    status: str  # "added", "modified", "removed", "renamed"
    additions: int = 0
    deletions: int = 0
    patch: str = ""
    content: str = ""
    classification: FileClassification = FileClassification.OTHER
    added_lines: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class PRContext:
    """Context about a pull request being reviewed."""

    owner: str
    repo: str
    pr_number: int
    head_sha: str
    base_branch: str = "main"
    title: str = ""
    author: str = ""
    commit_messages: list[str] = field(default_factory=list)
    changed_files: list[ChangedFile] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Complete result of a PR review."""

    pr_context: PRContext
    comments: list[ReviewComment] = field(default_factory=list)
    verdict: str = "COMMENT"  # "COMMENT" or "REQUEST_CHANGES"
    summary: str = ""
    layer1_count: int = 0
    layer2_count: int = 0
