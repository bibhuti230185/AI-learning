# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""GitHub PR integration — fetching diffs, classifying files, posting reviews."""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import httpx
import structlog

from sw360_review_agent.config import GitHubConfig
from sw360_review_agent.schemas import (
    ChangedFile,
    FileClassification,
    PRContext,
    ReviewComment,
    ReviewResult,
    Severity,
)

logger = structlog.get_logger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """Client for GitHub PR operations."""

    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self._config.webhook_secret:
            return True  # No secret configured — skip verification (dev mode)

        expected = hmac.new(
            self._config.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        expected_signature = f"sha256={expected}"
        return hmac.compare_digest(expected_signature, signature)

    async def get_pr_context(self, owner: str, repo: str, pr_number: int) -> PRContext:
        """Fetch PR metadata and build context."""
        # Get PR details
        resp = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        pr_data = resp.json()

        # Get commits for signed-off check
        commits_resp = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/commits"
        )
        commits_resp.raise_for_status()
        commits_data = commits_resp.json()

        commit_messages = [c["commit"]["message"] for c in commits_data]

        # Get changed files
        files = await self._get_changed_files(owner, repo, pr_number)

        return PRContext(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            head_sha=pr_data["head"]["sha"],
            base_branch=pr_data["base"]["ref"],
            title=pr_data["title"],
            author=pr_data["user"]["login"],
            commit_messages=commit_messages,
            changed_files=files,
        )

    async def _get_changed_files(
        self, owner: str, repo: str, pr_number: int
    ) -> list[ChangedFile]:
        """Fetch all changed files in a PR with their patches."""
        files: list[ChangedFile] = []
        page = 1

        while True:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            page_data = resp.json()

            if not page_data:
                break

            for f in page_data:
                changed_file = ChangedFile(
                    path=f["filename"],
                    status=f["status"],
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch", ""),
                )
                changed_file.classification = classify_file(changed_file.path)
                changed_file.added_lines = _extract_added_lines(changed_file.patch)
                files.append(changed_file)

            if len(page_data) < 100:
                break
            page += 1

        logger.info(
            "fetched_changed_files",
            count=len(files),
            java_count=sum(1 for f in files if f.path.endswith(".java")),
        )
        return files

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Fetch the full content of a file at a specific ref."""
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text

    async def post_review(self, result: ReviewResult) -> dict[str, Any]:
        """Post a review with inline comments to the PR."""
        ctx = result.pr_context

        # Build inline comments
        comments = []
        for comment in result.comments[: 50]:  # GitHub limit
            if not comment.file or comment.line <= 0:
                continue  # Skip commit-level findings (included in body)

            body = _format_comment_body(comment)
            comments.append({
                "path": comment.file,
                "line": comment.line,
                "body": body,
            })

        # Build review body (summary)
        body = _format_review_body(result)

        payload: dict[str, Any] = {
            "event": result.verdict,
            "body": body,
        }
        if comments:
            payload["comments"] = comments

        resp = await self._client.post(
            f"/repos/{ctx.owner}/{ctx.repo}/pulls/{ctx.pr_number}/reviews",
            json=payload,
        )

        if resp.status_code == 422:
            # Retry without inline comments (line mapping issues)
            logger.warning("review_post_422_retrying_without_inline")
            payload.pop("comments", None)
            resp = await self._client.post(
                f"/repos/{ctx.owner}/{ctx.repo}/pulls/{ctx.pr_number}/reviews",
                json=payload,
            )

        resp.raise_for_status()
        review_data = resp.json()
        logger.info(
            "review_posted",
            pr=ctx.pr_number,
            verdict=result.verdict,
            comments_count=len(comments),
            review_id=review_data.get("id"),
        )
        return review_data


# ---------------------------------------------------------------------------
# File Classification
# ---------------------------------------------------------------------------

_CLASSIFICATION_PATTERNS: list[tuple[str, FileClassification]] = [
    (r".*Controller\.java$", FileClassification.CONTROLLER),
    (r".*Service\.java$", FileClassification.SERVICE),
    (r".*(Test|SpecTest)\.java$", FileClassification.TEST),
    (r".*\.thrift$", FileClassification.THRIFT),
    (r".*(DatabaseHandler|Handler)\.java$", FileClassification.HANDLER),
    (r".*JacksonCustomizations\.java$", FileClassification.JACKSON_MIXIN),
    (r".*\.java$", FileClassification.JAVA),
]


def classify_file(path: str) -> FileClassification:
    """Classify a file based on its path/name pattern."""
    for pattern, classification in _CLASSIFICATION_PATTERNS:
        if re.match(pattern, path):
            return classification
    return FileClassification.OTHER


# ---------------------------------------------------------------------------
# Diff Parsing
# ---------------------------------------------------------------------------

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _extract_added_lines(patch: str) -> list[tuple[int, str]]:
    """Extract added lines with their line numbers from a unified diff patch.

    Returns:
        List of (line_number, line_content) for added lines.
    """
    if not patch:
        return []

    added_lines: list[tuple[int, str]] = []
    current_line = 0

    for line in patch.split("\n"):
        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue

        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append((current_line, line[1:]))  # Strip leading '+'
            current_line += 1
        elif line.startswith("-"):
            # Deleted line — don't advance line counter
            continue
        else:
            # Context line
            current_line += 1

    return added_lines


# ---------------------------------------------------------------------------
# Comment Formatting
# ---------------------------------------------------------------------------


def _format_comment_body(comment: ReviewComment) -> str:
    """Format a ReviewComment as a GitHub inline comment body."""
    severity_icons = {
        Severity.ERROR: "❌",
        Severity.WARNING: "⚠️",
        Severity.SUGGESTION: "💡",
    }
    icon = severity_icons.get(comment.severity, "ℹ️")

    parts = [f"**{icon} {comment.rule}** | {comment.message}"]

    if comment.suggestion:
        parts.append(f"\n```suggestion\n{comment.suggestion}\n```")

    if comment.reference:
        parts.append(f"\n> Reference: {comment.reference}")

    return "\n".join(parts)


def _format_review_body(result: ReviewResult) -> str:
    """Format the review summary body."""
    error_count = sum(1 for c in result.comments if c.severity == Severity.ERROR)
    warning_count = sum(1 for c in result.comments if c.severity == Severity.WARNING)
    suggestion_count = sum(1 for c in result.comments if c.severity == Severity.SUGGESTION)

    lines = [
        "## 🤖 SW360 PR Review Agent",
        "",
        "| Severity | Count |",
        "|----------|-------|",
        f"| ❌ Errors | {error_count} |",
        f"| ⚠️ Warnings | {warning_count} |",
        f"| 💡 Suggestions | {suggestion_count} |",
        "",
        f"**Layer 1** (deterministic): {result.layer1_count} findings",
        f"**Layer 2** (AI-powered): {result.layer2_count} findings",
        "",
    ]

    if result.summary:
        lines.append(result.summary)

    # Include commit-level findings in body
    commit_findings = [c for c in result.comments if not c.file or c.line <= 0]
    if commit_findings:
        lines.append("\n### Commit-Level Issues")
        for cf in commit_findings:
            lines.append(f"- **{cf.rule}**: {cf.message}")

    lines.append(
        "\n---\n"
        "*Automated review by SW360 PR Review Agent. "
        "React 👍/👎 on inline comments to provide feedback.*"
    )

    return "\n".join(lines)
