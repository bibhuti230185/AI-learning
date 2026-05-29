# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Layer 2 — RAG-powered LLM review for expert-level contextual code analysis.

This layer handles checks that require deep SW360 domain knowledge,
cross-file context, and understanding of architectural patterns that
ArchUnit (78 tests) and CI pipelines cannot cover.

Rule categories:
  L01–L03: REST API layer (backward compat, Jackson mixin, HATEOAS)
  L04–L06: Service & Thrift layer (null-safety, exception handling, cross-file)
  L07–L09: Database layer (query efficiency, pagination, migration)
  L10–L12: Testing & security (test quality, permissions, resource mgmt)
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
from sw360_review_agent.schemas import (
    ChangedFile,
    FileClassification,
    ReviewComment,
    Severity,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt — deep SW360 expertise baked in
# ---------------------------------------------------------------------------

REVIEW_SYSTEM_PROMPT = """\
You are an expert SW360 code reviewer with deep knowledge of the Eclipse SW360 \
architecture, conventions, and common pitfalls. You review PR diffs for issues \
that automated tools (ArchUnit, Spotless, CI) CANNOT catch.

## SW360 Architecture (you MUST understand this)
```
REST Controllers → Sw360*Service → ThriftClients → Backend *Handler → *Repository → CouchDB
                                                     ↑
                                            Thrift .thrift files define the interface
```
- **Controllers**: @RestController, HATEOAS (EntityModel/CollectionModel), HAL links
- **Services** (Sw360*Service): Bridge REST ↔ Thrift. Must null-check every Thrift return.
- **ThriftClients**: makeComponentClient(), makeProjectClient(), etc.
- **Handlers** (*Handler, *DatabaseHandler): Business logic + CouchDB access via repositories
- **Repositories**: Extend DatabaseRepositoryCloudantClient<T>, use CouchDB views/selectors
- **DTOs**: Thrift-generated objects (not POJOs). Serialized via JacksonCustomizations mixins.

## Response Format
Return ONLY a JSON array. Each finding:
```json
[
  {
    "line": <int>,
    "severity": "error" | "warning" | "suggestion",
    "rule": "SW360-L01" to "SW360-L12",
    "message": "<clear, specific description>",
    "suggestion": "<concrete code fix>",
    "reference": "<file or class where the correct pattern exists>"
  }
]
```
If no issues found, return: []

## Rules You Enforce

### REST API Layer
- **L01 — API backward compatibility**: Detect breaking REST API changes: \
field removal from responses, field type changes, endpoint path/method changes, \
renamed query parameters. These break existing clients.
- **L02 — JacksonCustomizations dual registration**: When new Thrift types are exposed \
via REST, the mixin must be registered TWICE in JacksonCustomizations.java: \
(1) setMixInAnnotation() for runtime serialization AND \
(2) SpringDocUtils.getConfig().replaceWithClass() for OpenAPI schema. \
Missing either causes silent bugs.
- **L03 — HATEOAS & HAL response format**: Controllers must return \
EntityModel<T> / CollectionModel<T>, not raw objects. Links must be added via \
restControllerHelper. Pagination must use PaginationResult.

### Service & Thrift Layer
- **L04 — Thrift null-safety**: Every Thrift client call can return null. \
The caller MUST check for null before using the result. \
Common anti-pattern: `client.getXById(id, user).getName()` → NPE. \
Correct: assign to variable → null-check → throw ResourceNotFoundException if null.
- **L05 — Exception handling chain**: SW360Exception must be caught and mapped: \
errorCode 404 → ResourceNotFoundException, 403 → AccessDeniedException, \
409 → DataIntegrityViolationException. Never expose raw TException or stack traces.
- **L06 — Cross-file consistency**: Verify these change-pairs are complete: \
Thrift .thrift change → Handler updated → Service updated → Test updated. \
New Controller endpoint → matching test with actual HTTP call. \
New REST field → JacksonCustomizations mixin updated.

### Database & CouchDB Layer
- **L07 — CouchDB query efficiency**: Detect N+1 query patterns (loop + single doc fetch). \
Prefer bulk operations (executeBulk, getAll with keys). \
New selector queries should have a matching createIndex or createPartialTypeIndex.
- **L08 — Pagination correctness**: DB-side pagination must use PaginationData consistently. \
Set totalRowCount. Don't load all docs and then paginate in-memory (defeats the purpose). \
Repository methods returning List<T> for large collections must accept PaginationData.
- **L09 — CouchDB view design**: Map functions must filter by type. \
Views emitting too many fields waste memory. \
Reduce functions should use built-ins (_count, _sum) when possible.

### Testing & Security
- **L10 — Test quality & coverage depth**: Tests must make REAL HTTP calls \
(TestRestTemplate.exchange(), MockMvc.perform()). Tests with only \
assertTrue(true) or no assertions are worthless. Integration tests must verify \
response status, body content, and error cases. Test both happy path and error paths.
- **L11 — Document-level permission checks**: Write operations on documents \
(update, delete) must check permissions via makePermission(doc, user).isActionAllowed(). \
Role checks via isUserAtLeast() for admin operations. \
Visibility enforcement: PRIVATE, ME_AND_MODERATORS, BUISNESSUNIT_AND_MODERATORS, EVERYONE.
- **L12 — Resource management**: Thrift transport must be closed after use. \
Streams must use try-with-resources. No Thread creation in controllers/services \
(use managed executors). No mutable static state.

## Critical Constraints
- ONLY report findings you are ≥80% confident about.
- EVERY finding must cite a specific line number from the diff.
- NEVER flag issues already caught by ArchUnit (System.out, @Autowired fields, \
@Operation missing, naming conventions, banned imports, etc.).
- Provide ACTIONABLE suggestions with actual code, not vague advice.
- When referencing a pattern, cite the actual SW360 class where it's done correctly.
"""

# ---------------------------------------------------------------------------
# File-type-specific review focus prompts
# ---------------------------------------------------------------------------

_FILE_TYPE_FOCUS: dict[FileClassification, str] = {
    FileClassification.CONTROLLER: """\
## Review Focus: REST Controller
You are reviewing a **REST Controller**. Focus on:
1. **L01**: Are any existing response fields removed or renamed? (breaking change)
2. **L02**: If this controller returns new Thrift types, does JacksonCustomizations need updating?
3. **L03**: Does the response use EntityModel<T> / CollectionModel<T>? Are HAL links added?
4. **L06**: Is there a matching test class with actual HTTP calls for new/changed endpoints?
5. **L11**: Do write endpoints check document-level permissions?

DO NOT check: @Operation, @PreAuthorize, @SecurityRequirement, @RestController \
(ArchUnit already enforces these).
""",
    FileClassification.SERVICE: """\
## Review Focus: Service (Sw360*Service)
You are reviewing a **REST Service class**. Focus on:
1. **L04**: Is EVERY Thrift client return value null-checked before use?
2. **L05**: Are SW360Exception error codes mapped to proper HTTP exceptions?
3. **L06**: If a new Thrift method is called, is the Handler implementation present?
4. **L12**: Are Thrift clients obtained and used safely?

Pattern to verify:
```java
ComponentService.Iface client = thriftClients.makeComponentClient();
Component comp = client.getComponentById(id, user);
if (comp == null) {
    throw new ResourceNotFoundException("Component not found: " + id);
}
```
""",
    FileClassification.HANDLER: """\
## Review Focus: Backend Handler
You are reviewing a **Backend Handler**. Focus on:
1. **L07**: Are there N+1 query patterns? (looping with single-doc fetches)
2. **L08**: Do methods returning collections use PaginationData when appropriate?
3. **L09**: If new CouchDB views are defined, do map functions filter by type?
4. **L11**: Are permission checks applied before write/delete operations?
5. **L05**: Are exceptions wrapped in SW360Exception with proper error codes?

Anti-pattern to catch:
```java
// BAD: N+1 query
for (String id : releaseIds) {
    Release r = repository.get(id);  // One query per iteration!
    results.add(r);
}
// GOOD: Bulk fetch
List<Release> results = repository.get(releaseIds);
```
""",
    FileClassification.TEST: """\
## Review Focus: Test Class
You are reviewing a **Test class**. Focus on:
1. **L10**: Do @Test methods actually make HTTP calls (TestRestTemplate/MockMvc)?
2. **L10**: Are there real assertions on response status, body, and fields?
3. **L10**: Are error cases tested (404, 403, 400)?
4. **L06**: Does the test naming follow existing patterns?

Worthless test pattern to flag:
```java
@Test
void testSomething() {
    assertTrue(true);  // Does nothing — ArchUnit will count this but it's useless
}
```
""",
    FileClassification.THRIFT: """\
## Review Focus: Thrift Definition
You are reviewing a **Thrift .thrift file**. Focus on:
1. **L06**: Are field numbers sequential? No gaps or reused numbers from deleted fields?
2. **L06**: Are new fields marked optional (required fields break backward compat)?
3. **L09**: Does a new service method need a corresponding Handler implementation?
4. **L01**: Could removing/renaming a field break existing REST responses?
""",
}

_DEFAULT_FOCUS = """\
## Review Focus: General Java File
Review this file for:
1. **L04**: Null-safety on any Thrift or external service calls
2. **L05**: Proper exception handling (no swallowing, proper mapping)
3. **L07**: Efficient data access patterns (no N+1 queries)
4. **L12**: Proper resource management (streams closed, no leaks)
"""


class LLMReviewer:
    """Layer 2 reviewer that uses RAG + LLM for contextual code analysis."""

    def __init__(
        self,
        model_config: ModelConfig,
        layer2_config: Layer2Config,
        retriever: VectorRetriever,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._config = layer2_config
        self._retriever = retriever
        self._provider = llm_provider or create_provider(model_config)
        self._enabled_checks = set(layer2_config.checks)

    async def review_file(self, file: ChangedFile) -> list[ReviewComment]:
        """Run Layer 2 review on a single file.

        Steps 4-7 from the workflow:
        4. Retrieve applicable rules (RAG)
        5. Retrieve reference implementation (RAG)
        6. Retrieve cross-file context (RAG)
        7. LLM analysis
        """
        if file.classification == FileClassification.OTHER:
            return []
        if not file.added_lines:
            return []

        entity = _extract_entity(file.path)
        file_type = file.classification.value

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
            file_classification=file.classification,
        )

        messages = [
            LLMMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
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
        file_classification: FileClassification = FileClassification.JAVA,
    ) -> str:
        """Build the complete user prompt for LLM analysis."""
        # File-type-specific focus instructions
        focus = _FILE_TYPE_FOCUS.get(file_classification, _DEFAULT_FOCUS)

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
