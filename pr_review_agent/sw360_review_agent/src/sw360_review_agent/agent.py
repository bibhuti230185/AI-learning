# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""PR Review Agent orchestrator — coordinates Layer 1 + Layer 2 + posting."""

from __future__ import annotations

import time

import structlog

from sw360_review_agent.config import AgentConfig
from sw360_review_agent.github_client import GitHubClient
from sw360_review_agent.lint_rules import DeterministicLinter
from sw360_review_agent.llm_reviewer import LLMReviewer
from sw360_review_agent.models import create_provider
from sw360_review_agent.retriever import VectorRetriever
from sw360_review_agent.rules_loader import ProjectRules, load_project_rules
from sw360_review_agent.schemas import (
    FileClassification,
    PRContext,
    ReviewComment,
    ReviewResult,
    Severity,
)

logger = structlog.get_logger(__name__)


class PRReviewAgent:
    """Two-Layer PR Review Agent.

    Orchestrates the full review pipeline:
    1. Fetch PR diff and classify files
    2. Run Layer 1 deterministic rules
    3. Run Layer 2 RAG + LLM analysis
    4. Merge, deduplicate, and post review
    """

    def __init__(self, config: AgentConfig, project_rules: ProjectRules | None = None) -> None:
        self._config = config

        # Load project rules from config directory or default
        if project_rules is None:
            self._project_rules = load_project_rules(config.project_rules_dir)
        else:
            self._project_rules = project_rules

        self._github = GitHubClient(config.github, project_rules=self._project_rules)
        self._linter = DeterministicLinter(
            enabled_rules=config.layer1.rules if config.layer1.enabled else [],
            project_rules=self._project_rules,
        )
        self._retriever = VectorRetriever(config.layer2.vector_store)

        # LLM provider (shared between Layer 2 reviewer and potential future uses)
        self._llm_provider = create_provider(config.model)
        self._llm_reviewer = LLMReviewer(
            model_config=config.model,
            layer2_config=config.layer2,
            retriever=self._retriever,
            llm_provider=self._llm_provider,
            project_rules=self._project_rules,
        )

    async def initialize(self) -> None:
        """Initialize async resources (vector store, etc.)."""
        if self._config.layer2.enabled:
            try:
                await self._retriever.initialize()
            except Exception as exc:
                logger.warning(
                    "vector_store_init_failed_layer2_disabled",
                    error=str(exc),
                )
                self._config.layer2.enabled = False

    async def review_pr(
        self, owner: str, repo: str, pr_number: int
    ) -> ReviewResult:
        """Execute the full review pipeline on a pull request.

        Args:
            owner: Repository owner (e.g., "eclipse-sw360").
            repo: Repository name (e.g., "sw360").
            pr_number: Pull request number.

        Returns:
            ReviewResult with all findings and verdict.
        """
        start_time = time.monotonic()
        logger.info("review_started", owner=owner, repo=repo, pr=pr_number)

        # Step 0-2: Fetch PR context and classify files
        pr_context = await self._github.get_pr_context(owner, repo, pr_number)

        # Filter to relevant files only (skip "other" type)
        relevant_files = [
            f for f in pr_context.changed_files
            if f.file_type != "other"
        ]

        if not relevant_files:
            logger.info("no_relevant_files_skipping", pr=pr_number)
            return ReviewResult(
                pr_context=pr_context,
                verdict="COMMENT",
                summary="No relevant files changed — skipping review.",
            )

        logger.info(
            "files_classified",
            total=len(pr_context.changed_files),
            relevant=len(relevant_files),
        )

        # Step 3: Layer 1 — Deterministic checks
        layer1_findings: list[ReviewComment] = []
        if self._config.layer1.enabled:
            layer1_findings = self._linter.check_all(
                relevant_files, pr_context.commit_messages
            )
            logger.info("layer1_done", findings=len(layer1_findings))

        # Steps 4-7: Layer 2 — RAG + LLM (skip if >100 files for performance)
        layer2_findings: list[ReviewComment] = []
        if self._config.layer2.enabled and len(relevant_files) <= 100:
            layer2_findings = await self._llm_reviewer.review_all(relevant_files)
            logger.info("layer2_done", findings=len(layer2_findings))
        elif len(relevant_files) > 100:
            logger.info("layer2_skipped_too_many_files", count=len(relevant_files))

        # Step 8: Merge and deduplicate
        all_findings = _deduplicate_and_prioritize(
            layer1_findings, layer2_findings, self._config.review.min_confidence
        )

        # Determine verdict
        has_errors = any(c.severity == Severity.ERROR for c in all_findings)
        verdict = (
            "REQUEST_CHANGES"
            if has_errors and self._config.review.block_on_errors
            else "COMMENT"
        )

        elapsed = time.monotonic() - start_time
        result = ReviewResult(
            pr_context=pr_context,
            comments=all_findings,
            verdict=verdict,
            layer1_count=len(layer1_findings),
            layer2_count=len(layer2_findings),
            summary=f"Review completed in {elapsed:.1f}s.",
        )

        logger.info(
            "review_complete",
            pr=pr_number,
            verdict=verdict,
            total_findings=len(all_findings),
            elapsed_seconds=round(elapsed, 1),
        )

        return result

    async def review_and_post(
        self, owner: str, repo: str, pr_number: int
    ) -> ReviewResult:
        """Review and post results to GitHub.

        Combines review_pr() + posting. Use this for the full webhook flow.
        """
        result = await self.review_pr(owner, repo, pr_number)

        # Step 9: Post to GitHub
        if result.comments:
            await self._github.post_review(result)
        else:
            logger.info("no_findings_no_review_posted", pr=pr_number)

        return result

    async def close(self) -> None:
        """Clean up all resources."""
        await self._github.close()
        await self._llm_reviewer.close()
        await self._retriever.close()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate_and_prioritize(
    layer1: list[ReviewComment],
    layer2: list[ReviewComment],
    min_confidence: float,
) -> list[ReviewComment]:
    """Merge Layer 1 + Layer 2 findings, deduplicate overlaps, sort by severity.

    Rules:
    - If both layers flag same file+line+rule → keep Layer 1 (more reliable)
    - Filter out Layer 2 findings below confidence threshold
    - Sort: errors first, then warnings, then suggestions
    - Cap at 50 comments (GitHub limits)
    """
    # Create a set of (file, line, rule) from Layer 1
    layer1_keys = {(c.file, c.line, c.rule) for c in layer1}

    # Filter Layer 2 findings
    filtered_layer2 = [
        c for c in layer2
        if (c.file, c.line, c.rule) not in layer1_keys
        and c.confidence >= min_confidence
    ]

    combined = layer1 + filtered_layer2

    # Sort: errors first, then warnings, then suggestions; then by file and line
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.SUGGESTION: 2}
    combined.sort(key=lambda c: (severity_order.get(c.severity, 3), c.file, c.line))

    # Cap at 50
    if len(combined) > 50:
        logger.warning("findings_capped", total=len(combined), kept=50)
        combined = combined[:50]

    return combined
