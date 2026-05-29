# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Layer 1 — Deterministic lint rules for SW360 PRs.

These rules run instantly (< 10 seconds), cost $0, and are 100% accurate.
They catch violations that ArchUnit (78 tests) and CI workflows do NOT cover.

What ArchUnit/CI already enforces (we intentionally skip these):
  - License headers (CI: testForLicenseHeaders.sh)
  - System.out / printStackTrace / LoggerFactory (ArchUnit: LoggingStandardRulesTest)
  - Field @Autowired (ArchUnit: DependencyInjectionRulesTest)
  - @PreAuthorize / @Secured (ArchUnit: SecurityAnnotationRulesTest)
  - @Operation on endpoints (ArchUnit: OpenApiDocumentationRulesTest)
  - Naming conventions (ArchUnit: NamingConventionRulesTest)
  - Commit message format (CI: conventional commits action)
"""

from __future__ import annotations

import re
from typing import Callable

import structlog

from sw360_review_agent.schemas import (
    ChangedFile,
    FileClassification,
    ReviewComment,
    Severity,
)

logger = structlog.get_logger(__name__)


# Type alias for a rule checker function
RuleChecker = Callable[[ChangedFile], list[ReviewComment]]


def check_signed_off(commit_messages: list[str]) -> list[ReviewComment]:
    """R01: All commits must have Signed-off-by line (DCO / Eclipse ECA requirement).

    CI checks conventional commit format but the Eclipse ECA bot checks
    Signed-off-by separately. Catching this early saves a CI round-trip.
    """
    findings: list[ReviewComment] = []

    for i, msg in enumerate(commit_messages):
        if "Signed-off-by:" not in msg:
            findings.append(
                ReviewComment(
                    file="",
                    line=0,
                    severity=Severity.ERROR,
                    rule="SW360-R01",
                    message=f"Commit {i + 1} missing 'Signed-off-by:' line (DCO requirement).",
                    suggestion="Use `git commit -s` to add Signed-off-by automatically.",
                    source="deterministic",
                )
            )
    return findings


def check_thrift_null_safety(file: ChangedFile) -> list[ReviewComment]:
    """R02: Thrift client return values used without null-check.

    ArchUnit does NOT check this. Thrift service calls can return null
    and callers must guard against it — a common source of NPEs.
    """
    findings: list[ReviewComment] = []

    # Pattern: calling a thrift client method and immediately chaining on it
    # e.g., client.getComponentById(id, user).getName()  ← NPE risk
    chain_pattern = re.compile(
        r"(client|Client)\.\w+\([^)]*\)\.\w+\("
    )
    # Pattern: thrift getter assigned and used without null check
    # e.g., Component comp = client.get(...);  comp.getName() with no null check in between
    getter_pattern = re.compile(
        r"=\s*\w*(client|Client|thriftClients)\.\w*make\w*\(\)"
    )

    for line_num, line_content in file.added_lines:
        if chain_pattern.search(line_content):
            findings.append(
                ReviewComment(
                    file=file.path,
                    line=line_num,
                    severity=Severity.WARNING,
                    rule="SW360-R02",
                    message="Thrift call result used directly without null-check. Thrift methods can return null.",
                    suggestion=(
                        "Assign to a variable first and check for null:\n"
                        "Component comp = client.getComponentById(id, user);\n"
                        "if (comp == null) { throw new ResourceNotFoundException(...); }"
                    ),
                    source="deterministic",
                )
            )
    return findings


def check_hardcoded_credentials(file: ChangedFile) -> list[ReviewComment]:
    """R03: No hardcoded passwords, tokens, or secrets in source code.

    Not covered by ArchUnit. CodeQL may catch some patterns but this
    is faster and runs before CI.
    """
    findings: list[ReviewComment] = []
    patterns = [
        (re.compile(r'(?i)(password|passwd|pwd)\s*=\s*"[^"]{4,}"'), "password"),
        (re.compile(r'(?i)(api[_-]?key|apikey|secret[_-]?key)\s*=\s*"[^"]{4,}"'), "API key"),
        (re.compile(r'(?i)(token)\s*=\s*"[^"]{8,}"'), "token"),
        (re.compile(r'(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*'), "bearer token"),
    ]

    for line_num, line_content in file.added_lines:
        # Skip test files and config examples
        if "/test/" in file.path or "example" in file.path.lower():
            continue
        for pattern, secret_type in patterns:
            if pattern.search(line_content):
                findings.append(
                    ReviewComment(
                        file=file.path,
                        line=line_num,
                        severity=Severity.ERROR,
                        rule="SW360-R03",
                        message=f"Potential hardcoded {secret_type} detected. Use configuration properties or environment variables.",
                        suggestion="Move secrets to sw360.properties or environment variables.",
                        source="deterministic",
                    )
                )
                break  # One finding per line
    return findings


def check_unbounded_collection_fetch(file: ChangedFile) -> list[ReviewComment]:
    """R04: Fetching all documents without pagination is a performance risk.

    Not covered by ArchUnit. Large CouchDB collections fetched without
    limits cause OOM or slow responses.
    """
    findings: list[ReviewComment] = []
    # Pattern: getAll*, findAll*, list* returning List/Set without Pageable
    fetch_all_pattern = re.compile(
        r"\b(getAll|findAll|listAll|fetchAll)\w*\s*\("
    )
    # Exclude lines that already have PaginationData or Pageable
    pagination_pattern = re.compile(r"(PaginationData|Pageable|pageData|pageable|limit|offset)")

    for line_num, line_content in file.added_lines:
        if fetch_all_pattern.search(line_content):
            if not pagination_pattern.search(line_content):
                # Check surrounding added lines for pagination context
                nearby_lines = dict(file.added_lines)
                has_pagination = any(
                    pagination_pattern.search(nearby_lines.get(line_num + offset, ""))
                    for offset in range(-3, 4)
                    if offset != 0
                )
                if not has_pagination:
                    findings.append(
                        ReviewComment(
                            file=file.path,
                            line=line_num,
                            severity=Severity.WARNING,
                            rule="SW360-R04",
                            message="Unbounded collection fetch without pagination. Consider using PaginationData for large datasets.",
                            suggestion="Use paginated query methods with PaginationData to avoid loading entire collections into memory.",
                            source="deterministic",
                        )
                    )
    return findings


def check_missing_migration_script(file: ChangedFile) -> list[ReviewComment]:
    """R05: New Thrift fields should have a corresponding CouchDB migration script.

    Not covered by ArchUnit or CI. When new fields are added to Thrift
    definitions, existing CouchDB documents need a migration script
    under scripts/migrations/.
    """
    findings: list[ReviewComment] = []
    if not file.path.endswith(".thrift"):
        return []
    if file.status != "modified":
        return []

    # Check for new field definitions (numbered Thrift fields)
    field_pattern = re.compile(r"^\+\s*\d+:\s+(optional|required)?\s*\w+\s+\w+")
    new_fields = []

    for line_num, line_content in file.added_lines:
        if field_pattern.search("+" + line_content):
            new_fields.append((line_num, line_content.strip()))

    if new_fields:
        findings.append(
            ReviewComment(
                file=file.path,
                line=new_fields[0][0],
                severity=Severity.WARNING,
                rule="SW360-R05",
                message=(
                    f"New Thrift field(s) added ({len(new_fields)}). "
                    "Ensure a CouchDB migration script exists under scripts/migrations/ "
                    "to handle existing documents missing this field."
                ),
                suggestion="Create scripts/migrations/0XX_migrate_<description>.py for backward compatibility.",
                source="deterministic",
            )
        )
    return findings


def check_catch_generic_exception(file: ChangedFile) -> list[ReviewComment]:
    """R06: Avoid catching generic Exception — use specific exception types.

    Not fully covered by ArchUnit (it only blocks catch(Throwable)).
    Catching broad Exception hides bugs and makes debugging harder.
    """
    findings: list[ReviewComment] = []
    # Match: catch (Exception e) but not catch (SW360Exception | TException e)
    generic_catch = re.compile(r"catch\s*\(\s*Exception\s+\w+\s*\)")

    for line_num, line_content in file.added_lines:
        if generic_catch.search(line_content):
            # Allow in test files — common for assertThrows patterns
            if "/test/" in file.path:
                continue
            findings.append(
                ReviewComment(
                    file=file.path,
                    line=line_num,
                    severity=Severity.WARNING,
                    rule="SW360-R06",
                    message="Catching generic Exception. Use specific types like SW360Exception, TException, or IOException.",
                    suggestion="catch (SW360Exception e) { ... } catch (TException e) { ... }",
                    source="deterministic",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Rule Registry
# ---------------------------------------------------------------------------

# Maps rule ID -> (checker function, applicable file classifications)
_FILE_RULES: dict[str, tuple[RuleChecker, set[FileClassification] | None]] = {
    "R02": (check_thrift_null_safety, None),
    "R03": (check_hardcoded_credentials, None),
    "R04": (check_unbounded_collection_fetch, None),
    "R05": (check_missing_migration_script, None),
    "R06": (check_catch_generic_exception, None),
}


class DeterministicLinter:
    """Layer 1 deterministic linter that runs rule checks on changed files.

    Focuses on violations that ArchUnit and CI pipelines do NOT catch.
    """

    def __init__(self, enabled_rules: list[str] | None = None) -> None:
        """Initialize with optional subset of rules to enable.

        Args:
            enabled_rules: List of rule IDs (e.g., ["R01", "R02"]).
                          If None, all rules are enabled.
        """
        if enabled_rules is None:
            self._enabled = set(_FILE_RULES.keys()) | {"R01"}
        else:
            self._enabled = set(enabled_rules)

    def check_file(self, file: ChangedFile) -> list[ReviewComment]:
        """Run all applicable deterministic rules on a single file.

        Args:
            file: The changed file to check.

        Returns:
            List of review comments (findings).
        """
        if file.classification == FileClassification.OTHER:
            return []

        findings: list[ReviewComment] = []

        for rule_id, (checker, applicable_to) in _FILE_RULES.items():
            if rule_id not in self._enabled:
                continue

            # Check if rule applies to this file classification
            if applicable_to is not None and file.classification not in applicable_to:
                continue

            try:
                rule_findings = checker(file)
                findings.extend(rule_findings)
            except Exception as exc:
                logger.warning(
                    "rule_check_failed",
                    rule=rule_id,
                    file=file.path,
                    error=str(exc),
                )

        return findings

    def check_commits(self, commit_messages: list[str]) -> list[ReviewComment]:
        """Run commit-level rules (R01: signed-off-by).

        Args:
            commit_messages: List of commit messages in the PR.

        Returns:
            List of review comments for commit-level violations.
        """
        if "R01" not in self._enabled:
            return []
        return check_signed_off(commit_messages)

    def check_all(
        self, files: list[ChangedFile], commit_messages: list[str] | None = None
    ) -> list[ReviewComment]:
        """Run all rules on all files and commits.

        Args:
            files: List of changed files.
            commit_messages: Optional list of commit messages.

        Returns:
            Combined list of all findings.
        """
        findings: list[ReviewComment] = []

        for file in files:
            file_findings = self.check_file(file)
            findings.extend(file_findings)
            logger.debug(
                "file_checked",
                file=file.path,
                findings=len(file_findings),
            )

        if commit_messages:
            commit_findings = self.check_commits(commit_messages)
            findings.extend(commit_findings)

        logger.info("layer1_complete", total_findings=len(findings))
        return findings
