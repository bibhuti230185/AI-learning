# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Layer 2 — RAG-powered LLM review for expert-level contextual code analysis.

This layer handles checks that require deep domain knowledge,
cross-file context, and understanding of architectural patterns that
automated linters and CI pipelines cannot cover.

Rules and prompts are loaded from project_rules/ for full configurability.
Any project can customize the LLM reviewer behavior without modifying Python code.
"""

from __future__ import annotations

import re

import structlog

from sw360_review_agent.config import Layer2Config, ModelConfig
from sw360_review_agent.models import (
    LLMMessage,
    LLMProvider,
    create_provider,
    parse_json_response,
)
from sw360_review_agent.retriever import RetrievedChunk, VectorRetriever
from sw360_review_agent.rules_loader import ProjectRules
from sw360_review_agent.schemas import (
    ChangedFile,
    FileClassification,
    ReviewComment,
    Severity,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Fallback system prompt (used when no project_rules/review_prompt.md exists)
# ---------------------------------------------------------------------------

_FALLBACK_SYSTEM_PROMPT = """\
You are an expert code reviewer. You review PR diffs for issues \
that automated tools (linters, CI) CANNOT catch.

## Response Format
Return ONLY a JSON array. Each finding:
```json
[
  {
    "line": <int>,
    "severity": "error" | "warning" | "suggestion",
    "rule": "<rule-id>",
    "message": "<clear, specific description>",
    "suggestion": "<concrete code fix>",
    "reference": "<file or class where the correct pattern exists>"
  }
]
```
If no issues found, return: []

## Critical Constraints
- ONLY report findings you are ≥80% confident about.
- EVERY finding must cite a specific line number from the diff.
- NEVER flag issues that automated linters/CI already catch.
- Provide ACTIONABLE suggestions with actual code, not vague advice.
"""

_FALLBACK_FOCUS = """\
## Review Focus: General Source File
Review this file for:
1. Null-safety on external or service calls
2. Proper exception handling (no swallowing, proper mapping)
3. Efficient data access patterns (no N+1 queries)
4. Proper resource management (streams closed, no leaks)
"""


def _build_system_prompt(project_rules: ProjectRules | None) -> str:
    """Build the system prompt from project rules or use fallback."""
    if project_rules and project_rules.review_prompt:
        prompt = project_rules.review_prompt

        # Append rules section if review rules are defined
        if project_rules.review_rules:
            rules_section = "\n\n## Rules You Enforce\n"
            for rule in project_rules.review_rules:
                rules_section += f"\n- **{rule.id} — {rule.name}**: {rule.description}"
            prompt += rules_section

        return prompt

    return _FALLBACK_SYSTEM_PROMPT


def _get_focus_prompt(
    file_type: str,
    project_rules: ProjectRules | None,
) -> str:
    """Get file-type-specific focus prompt from config or fallback."""
    if project_rules and project_rules.review_focus:
        focus = project_rules.review_focus.get(file_type)
        if focus:
            return focus
        # Try "default" key
        return project_rules.review_focus.get("default", _FALLBACK_FOCUS)

    # Legacy: try the hardcoded dict (kept for backward compat)
    return _FILE_TYPE_FOCUS.get(
        FileClassification(file_type) if file_type in FileClassification.__members__.values() else FileClassification.OTHER,
        _FALLBACK_FOCUS,
    )


# ---------------------------------------------------------------------------
# Legacy file-type-specific review focus prompts (backward compat)
# These are used ONLY when no project_rules/review_focus.yaml is configured.
# ---------------------------------------------------------------------------

_FILE_TYPE_FOCUS: dict[FileClassification, str] = {
    FileClassification.CONTROLLER: (
        "## Review Focus: REST Controller\n"
        "Focus on: API backward compatibility, serialization config, "
        "response format conventions, matching tests, permission checks."
    ),
    FileClassification.SERVICE: (
        "## Review Focus: Service Layer\n"
        "Focus on: null-safety on external calls, exception mapping, "
        "cross-file consistency, resource management."
    ),
    FileClassification.HANDLER: (
        "## Review Focus: Backend Handler\n"
        "Focus on: N+1 query patterns, pagination, query efficiency, "
        "permission checks, exception handling."
    ),
    FileClassification.TEST: (
        "## Review Focus: Test Class\n"
        "Focus on: real HTTP/integration calls, meaningful assertions, "
        "error case coverage, naming conventions."
    ),
    FileClassification.THRIFT: (
        "## Review Focus: Interface Definition\n"
        "Focus on: field number sequencing, optional vs required, "
        "backward compatibility, matching implementations."
    ),
}


class LLMReviewer:
    """Layer 2 reviewer that uses RAG + LLM for contextual code analysis.

    Supports config-driven prompts loaded from project_rules/ or falls back
    to built-in prompts for backward compatibility.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        layer2_config: Layer2Config,
        retriever: VectorRetriever,
        llm_provider: LLMProvider | None = None,
        project_rules: ProjectRules | None = None,
    ) -> None:
        self._config = layer2_config
        self._retriever = retriever
        self._provider = llm_provider or create_provider(model_config)
        self._enabled_checks = set(layer2_config.checks)
        self._project_rules = project_rules
        self._system_prompt = _build_system_prompt(project_rules)

    async def review_file(self, file: ChangedFile) -> list[ReviewComment]:
        """Run Layer 2 review on a single file."""
        if file.classification == FileClassification.OTHER and file.file_type == "other":
            return []
        if not file.added_lines:
            return []

        entity = _extract_entity(file.path)
        file_type = file.file_type

        # Step 4: Retrieve rules
        rules_chunks = await self._retriever.retrieve_rules(file_type)

        # Step 5: Retrieve reference implementation
        reference_chunks = await self._retriever.retrieve_reference(entity, file_type)

        # Step 6: Retrieve cross-file context
        cross_file_chunks = await self._retriever.retrieve_cross_file_context(entity, file_type)

        # Step 7: LLM analysis
        findings = await self._llm_analyze(
            file=file,
            entity=entity,
            rules=rules_chunks,
            reference=reference_chunks,
            cross_file=cross_file_chunks,
        )

        logger.info(
            "layer2_file_reviewed",
            file=file.path,
            findings=len(findings),
        )
        return findings

    async def review_all(self, files: list[ChangedFile]) -> list[ReviewComment]:
        """Run Layer 2 review on all files.

        Args:
            files: Changed Java files to review.

        Returns:
            Combined findings from all files.
        """
        all_findings: list[ReviewComment] = []

        java_files = [
            f for f in files
            if f.classification != FileClassification.OTHER and f.added_lines
        ]

        for file in java_files:
            try:
                findings = await self.review_file(file)
                all_findings.extend(findings)
            except Exception as exc:
                logger.error(
                    "layer2_file_failed",
                    file=file.path,
                    error=str(exc),
                )

        logger.info("layer2_complete", total_findings=len(all_findings))
        return all_findings

    async def _llm_analyze(
        self,
        file: ChangedFile,
        entity: str,
        rules: list[RetrievedChunk],
        reference: list[RetrievedChunk],
        cross_file: list[RetrievedChunk],
    ) -> list[ReviewComment]:
        """Step 7: Send context to LLM and parse findings."""

        # Build the user prompt with all context
        diff_text = "\n".join(
            f"+{line_num}: {content}" for line_num, content in file.added_lines
        )

        user_prompt = self._build_user_prompt(
            file_path=file.path,
            entity=entity,
            diff=diff_text,
            rules=rules,
            reference=reference,
            cross_file=cross_file,
            file_type=file.file_type,
        )

        messages = [
            LLMMessage(role="system", content=self._system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        try:
            response = await self._provider.generate(
                messages,
                temperature=0.1,
                response_format="json",
            )
        except Exception as exc:
            logger.error("llm_call_failed", file=file.path, error=str(exc))
            return []

        # Parse LLM response into ReviewComment objects
        raw_findings = parse_json_response(response)
        findings: list[ReviewComment] = []

        for raw in raw_findings:
            try:
                severity_str = raw.get("severity", "warning").lower()
                severity = Severity(severity_str) if severity_str in Severity.__members__.values() else Severity.WARNING

                rule = raw.get("rule", "SW360-L00")
                # Only include if the check is enabled
                check_id = rule.replace("SW360-", "")
                if check_id not in self._enabled_checks and check_id.startswith("L"):
                    continue

                findings.append(
                    ReviewComment(
                        file=file.path,
                        line=int(raw.get("line", 1)),
                        severity=severity,
                        rule=rule,
                        message=raw.get("message", ""),
                        suggestion=raw.get("suggestion", ""),
                        source="llm",
                        confidence=0.8,
                        reference=raw.get("reference", ""),
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("skipping_malformed_finding", raw=raw, error=str(exc))

        return findings

    def _build_user_prompt(
        self,
        file_path: str,
        entity: str,
        diff: str,
        rules: list[RetrievedChunk],
        reference: list[RetrievedChunk],
        cross_file: list[RetrievedChunk],
        file_type: str = "java",
    ) -> str:
        """Build the complete user prompt for LLM analysis."""
        # File-type-specific focus instructions
        focus = _get_focus_prompt(file_type, self._project_rules)

        sections = [
            focus,
            f"## FILE UNDER REVIEW\nPath: {file_path}\nEntity: {entity}\n",
            f"## DIFF (added/modified lines)\n```\n{diff}\n```\n",
        ]

        if rules:
            rules_text = "\n".join(f"- {chunk.text}" for chunk in rules[:8])
            sections.append(f"## APPLICABLE RULES\n{rules_text}\n")

        if reference:
            ref_text = "\n".join(
                f"```java\n// Source: {chunk.source}\n{chunk.text}\n```"
                for chunk in reference[:2]
            )
            sections.append(f"## REFERENCE IMPLEMENTATION (correct pattern)\n{ref_text}\n")

        if cross_file:
            cf_text = "\n".join(
                f"- [{chunk.metadata.get('type', 'context')}] {chunk.text[:200]}"
                for chunk in cross_file[:5]
            )
            sections.append(f"## CROSS-FILE CONTEXT\n{cf_text}\n")

        sections.append(
            "## INSTRUCTIONS\n"
            "Compare the diff against rules and reference. "
            "Report violations as a JSON array. "
            "Only report issues you are confident about (>80% sure). "
            "If the code looks correct, return []."
        )

        return "\n".join(sections)

    async def close(self) -> None:
        """Clean up resources."""
        await self._provider.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENTITY_PATTERN = re.compile(r"(?:Sw360)?(\w+?)(?:Controller|Service|Handler|Test|SpecTest)\.java$")


def _extract_entity(file_path: str) -> str:
    """Extract the entity name from a file path.

    Examples:
        "rest/.../PackageController.java" -> "Package"
        "rest/.../Sw360ProjectService.java" -> "Project"
    """
    filename = file_path.split("/")[-1]
    match = _ENTITY_PATTERN.search(filename)
    if match:
        return match.group(1)
    # Fallback: use filename without extension
    return filename.replace(".java", "")
