# PR Review Agent — Workflow Guide

> **Audience:** Developers and team leads who want to understand exactly what the PR review agent does at each step, why it does it, and how to trace or debug it.

---

## Standardized Folder Context (May 2026)

This repository now organizes the three hackathon ideas under dedicated folders. This file remains the execution-level workflow for the PR review idea.

| Item | Location | Purpose |
|------|----------|---------|
| PR review idea proposal (canonical) | `PR_REVIEW_GUIDE.md` | Problem statement, business value, and hackathon framing |
| PR review execution workflow (this file) | `REVIEW_WORKFLOW.md` | Technical step-by-step behavior of both review layers |
| PR review diagrams | `diagrams/` | Visual assets referenced by the proposal guide |

Cross-idea folder mapping (relative to `agentt_hackathon/`):
- `endpoint_scaffolding_agent/` -> Endpoint scaffolding idea and diagrams
- `pr_review_agent/` -> PR review idea and diagrams (this folder)
- `clearing_agent/` -> License clearing idea and diagrams
- `license_compliance_agent/` -> LicenseLens AI idea and diagrams

When proposal and workflow wording diverge, treat the folder guide as idea truth and this document as the technical execution truth.

---

## Table of Contents

1. [Overview](#1-overview)
2. [High-Level Workflow Diagram](#2-high-level-workflow-diagram)
3. [Layer 1 — Deterministic Checks (Step-by-Step)](#3-layer-1--deterministic-checks-step-by-step)
   - [Step 0 — Receive Webhook](#step-0--receive-webhook)
   - [Step 1 — Fetch PR Diff](#step-1--fetch-pr-diff)
   - [Step 2 — Classify Changed Files](#step-2--classify-changed-files)
   - [Step 3 — Run Deterministic Rules](#step-3--run-deterministic-rules)
4. [Layer 2 — RAG-Powered Deep Review (Step-by-Step)](#4-layer-2--rag-powered-deep-review-step-by-step)
   - [Step 4 — Retrieve Rules for File Type (RAG)](#step-4--retrieve-rules-for-file-type-rag)
   - [Step 5 — Retrieve Reference Implementation (RAG)](#step-5--retrieve-reference-implementation-rag)
   - [Step 6 — Retrieve Cross-File Context (RAG)](#step-6--retrieve-cross-file-context-rag)
   - [Step 7 — LLM Analysis](#step-7--llm-analysis)
5. [Post Review](#5-post-review)
   - [Step 8 — Merge and Deduplicate Findings](#step-8--merge-and-deduplicate-findings)
   - [Step 9 — Post GitHub Review](#step-9--post-github-review)
   - [Step 10 — Store Context for Feedback](#step-10--store-context-for-feedback)
6. [Decision Points and Branching Logic](#6-decision-points-and-branching-logic)
7. [RAG Queries Reference](#7-rag-queries-reference)
8. [Deterministic Rules Reference](#8-deterministic-rules-reference)
9. [Error Handling per Step](#9-error-handling-per-step)
10. [Agent Tool Map](#10-agent-tool-map)
11. [Full Sequence Diagram](#11-full-sequence-diagram)
12. [How the LLM Orchestrates the Agent](#12-how-the-llm-orchestrates-the-agent)
13. [Feedback Collection](#13-feedback-collection)
14. [Debugging Tips](#14-debugging-tips)

---

## 1. Overview

The review agent has **two layers** that run sequentially on every PR.

| Layer | What | Speed | Cost | Catches |
|-------|------|-------|------|---------|
| **Layer 1** | Deterministic regex/pattern checks | <10 sec | $0 | Mechanical violations (R01-R08) |
| **Layer 2** | RAG-powered LLM analysis | 30-60 sec | ~$0.05/PR | Contextual issues (L01-L06) |

Both layers produce structured review comments. They are merged, deduplicated, and posted as a single GitHub review.

---

## 2. High-Level Workflow Diagram

```
         GitHub
          │
          │  pull_request.opened / synchronize
          ▼
   ┌──────────────────────┐
   │  PR REVIEW AGENT     │
   └────────┬─────────────┘
            │
            ├─ Step 0 ──► Receive webhook event
            ├─ Step 1 ──► GitHub API: fetch PR diff + changed files
            ├─ Step 2 ──► Classify files: controller/service/test/thrift/other
            │
            │  ══════ LAYER 1: DETERMINISTIC ═══════════════════════
            ├─ Step 3 ──► Run R01-R08 on each changed file (regex/grep)
            │
            │  ══════ LAYER 2: RAG + LLM ═══════════════════════════
            ├─ Step 4 ──► Vector Store: retrieve rules for file type
            ├─ Step 5 ──► Vector Store: retrieve reference implementation
            ├─ Step 6 ──► Vector Store: retrieve cross-file context
            ├─ Step 7 ──► LLM: analyze diff against context
            │
            │  ══════ POST REVIEW ══════════════════════════════════
            ├─ Step 8 ──► Merge + deduplicate findings
            ├─ Step 9 ──► GitHub API: post review with inline comments
            └─ Step 10 ─► Store review context (for feedback tracking)
```

---

## 3. Layer 1 — Deterministic Checks (Step-by-Step)

---

### Step 0 — Receive Webhook

**Triggered by:** GitHub sends `pull_request` event (action: `opened` or `synchronize`).

**What happens:**
- FastAPI webhook handler receives the event.
- Orchestrator classifies as "review" and routes to `PRReviewAgent`.

**Files involved:**
```
sw360_agents/api/webhooks.py       ← webhook receiver
sw360_agents/orchestrator/graph.py ← routes to review agent
sw360_agents/agents/review.py      ← PRReviewAgent.run()
```

---

### Step 1 — Fetch PR Diff

**Agent calls:** `fetch_pr_diff`

```
GET /repos/{owner}/{repo}/pulls/{pr_number}/files
Authorization: Bearer <github-token>
```

**Returns for each file:**
```json
{
  "filename": "rest/.../PackageController.java",
  "status": "modified",
  "additions": 25,
  "deletions": 3,
  "patch": "@@ -85,6 +85,30 @@ ...\n+    @PostMapping..."
}
```

**Source file:** `sw360_agents/github/pr_analyzer.py → get_changed_files()`

---

### Step 2 — Classify Changed Files

**Agent calls:** `classify_files`

Each file is classified based on path and name:

| Pattern | Classification |
|---------|---------------|
| `*Controller.java` | `controller` |
| `*Service.java` | `service` |
| `*Test.java` / `*SpecTest.java` | `test` |
| `*.thrift` | `thrift` |
| `*Handler.java` / `*DatabaseHandler.java` | `handler` |
| `JacksonCustomizations.java` | `jackson_mixin` |
| `*.java` (other) | `java` |
| Everything else | `other` (skipped) |

**Only `.java` files proceed** to Layer 1 and Layer 2.

**Source file:** `sw360_agents/github/pr_analyzer.py → classify_file()`

---

### Step 3 — Run Deterministic Rules

**Agent calls:** `run_deterministic_checks`

For each changed Java file, runs all applicable rules:

| Rule | Check | Detection | Applies to |
|------|-------|-----------|-----------|
| **R01** | EPL-2.0 license header | `grep SPDX` in first 15 lines | New files only |
| **R02** | No System.out.println | `grep System.out.print` in added lines | All Java |
| **R03** | No e.printStackTrace() | `grep .printStackTrace()` in added lines | All Java |
| **R04** | No @Autowired on fields | Regex: `@Autowired\s+private` in added lines | All Java |
| **R05** | @PreAuthorize on writes | @Post/@Put/@Patch/@Delete without @PreAuthorize within 5 lines above | Controllers |
| **R06** | @Operation on endpoints | Any @*Mapping without @Operation within 10 lines above | Controllers |
| **R07** | Logger uses Log4j2 | `LoggerFactory.getLogger` in added lines (should be LogManager) | All Java |
| **R08** | Commits signed-off | `Signed-off-by:` in commit messages | Commit level |

**Output:** List of `ReviewComment` objects:
```python
ReviewComment(
    file="rest/.../PackageController.java",
    line=142,
    severity="error",
    rule="SW360-R02",
    message="Use Log4j2 logger instead of System.out.println()",
    suggestion="log.info(\"Processing package: {}\", packageId);",
    source="deterministic"
)
```

**Source file:** `sw360_agents/validators/lint_rules.py → DeterministicLinter.check()`

---

## 4. Layer 2 — RAG-Powered Deep Review (Step-by-Step)

---

### Step 4 — Retrieve Rules for File Type (RAG)

**Agent calls:** `retrieve_applicable_rules`

For each changed file (by classification):

```python
query = f"coding rules for {file_type} files in SW360"
filter = {"type": "rule", "applies_to": file_type}
k = 8
```

**Example return for `controller` file:**
```markdown
- Write endpoints MUST have @PreAuthorize("hasAuthority('WRITE')")
- All endpoint methods MUST have @Operation(summary=..., tags=...)
- Catch SW360Exception, check errorCode, throw ResourceNotFoundException or AccessDeniedException
- Use getSw360UserFromAuthentication() for current user
- Never use System.out.println — use LogManager.getLogger()
```

**Source file:** `sw360_agents/agents/review.py → _retrieve_rules()`

---

### Step 5 — Retrieve Reference Implementation (RAG)

**Agent calls:** `retrieve_reference`

```python
entity = extract_entity_from_file(file)  # e.g. "Package" from PackageController.java
query = f"correct {entity} {file_type} implementation"
filter = {"type": f"{file_type}_method", "entity": entity}
k = 2
```

**Example return:**
```java
// Source: PackageController.java::getPackageById (reference)
@Operation(summary = "Get a single package", tags = {"Packages"})
@ApiResponse(responseCode = "200", description = "Package found")
@GetMapping("/{id}")
public ResponseEntity<EntityModel<Package>> getPackageById(
        @Parameter(description = "Package ID") @PathVariable String id) throws TException {
    User sw360User = restControllerHelper.getSw360UserFromAuthentication();
    ...
}
```

**Why this matters:** The LLM compares the PR diff against *how it's actually done correctly* in the same entity. This catches subtle deviations that regex rules cannot.

**Source file:** `sw360_agents/agents/review.py → _retrieve_reference()`

---

### Step 6 — Retrieve Cross-File Context (RAG)

**Agent calls:** `retrieve_cross_file_context`

This step checks if related files should also have been updated.

| If this file changed | Agent retrieves | To check |
|---------------------|-----------------|----------|
| `*Controller.java` | Entity's test file | Does a test exist for the new endpoint? |
| `*Controller.java` | JacksonCustomizations | Is mixin needed for new fields? |
| `*.thrift` | Entity's Handler | Is the handler implementing the new method? |
| `*Service.java` | Entity's controller | Is the service method called from a controller? |

```python
# Example for a Controller change:
queries = [
    ("test_exists", f"{entity} test method", {"type": "test_method", "entity": entity}),
    ("mixin_needed", f"{entity} JacksonCustomizations", {"type": "jackson_mixin"})
]
```

**Source file:** `sw360_agents/agents/review.py → _get_cross_file_context()`

---

### Step 7 — LLM Analysis

**Agent calls:** `llm_review_file`

Sends to GPT-4o per file:

```
## FILE UNDER REVIEW
Path: rest/.../PackageController.java

## DIFF (added/modified lines)
+    @PostMapping("/{id}/link")
+    public ResponseEntity<...> linkPackage(
+            @PathVariable String id,
+            @RequestBody LinkRequest request) throws TException {
+        System.out.println("Linking package: " + id);
+        ...
+    }

## APPLICABLE RULES
{retrieved rules from Step 4}

## REFERENCE IMPLEMENTATION (correct pattern)
{retrieved reference from Step 5}

## CROSS-FILE CONTEXT
- Test file: PackageTest.java has 15 test methods for 14 endpoints (gap: 1)
- Mixin: Package mixin exists, covers current fields

## INSTRUCTIONS
Compare diff against rules and reference. Report violations as JSON array.
```

**LLM returns:**
```json
[
  {
    "line": 142,
    "severity": "error",
    "rule": "SW360-R02",
    "message": "System.out.println detected. Use Log4j2 logger.",
    "suggestion": "log.info(\"Linking package: {}\", id);",
    "reference": "See PackageController.java:85 for correct pattern"
  },
  {
    "line": 140,
    "severity": "warning",
    "rule": "SW360-R05",
    "message": "POST endpoint missing @PreAuthorize(\"hasAuthority('WRITE')\")",
    "suggestion": "@PreAuthorize(\"hasAuthority('WRITE')\")\n@PostMapping(\"/{id}/link\")",
    "reference": "sw360_backend.instructions.md — Security Patterns"
  }
]
```

**Source file:** `sw360_agents/agents/review.py → _llm_review()`

---

## 5. Post Review

---

### Step 8 — Merge and Deduplicate Findings

**Agent calls:** `merge_findings`

Combines Layer 1 (deterministic) and Layer 2 (LLM) results:
- If both layers flag the same line+rule → keep one (prefer deterministic, it's more reliable)
- Sort by: severity (error first), then file, then line number
- Cap at 50 inline comments (GitHub limit)

**Source file:** `sw360_agents/agents/review.py → _deduplicate_and_prioritize()`

---

### Step 9 — Post GitHub Review

**Agent calls:** `post_review`

```
POST /repos/{owner}/{repo}/pulls/{pr_number}/reviews
Authorization: Bearer <github-token>
Body:
{
  "event": "REQUEST_CHANGES",  // or "COMMENT" if no errors
  "body": "## 🤖 SW360 Agent Review\n\n| Severity | Count |...",
  "comments": [
    {
      "path": "rest/.../PackageController.java",
      "line": 142,
      "body": "**❌ SW360-R02** | System.out.println detected\n\n```java\n// ✅ Fix:\nlog.info(...);\n```"
    }
  ]
}
```

| Verdict logic | Condition |
|--------------|-----------|
| `REQUEST_CHANGES` | Any finding with severity "error" |
| `COMMENT` | Only warnings and suggestions |

**Source file:** `sw360_agents/github/reviewer.py → post_review()`

---

### Step 10 — Store Context for Feedback

**Agent calls:** `store_review_context`

For each posted comment, stores:
```json
{
  "comment_id": "gh_comment_12345",
  "pr_number": 142,
  "rule": "SW360-R02",
  "file_type": "controller",
  "diff_context": "...",
  "rag_chunks_used": ["rule:annotations", "ref:PackageController::getById"],
  "layer": "deterministic",
  "posted_at": "2026-04-30T10:00:00Z"
}
```

This is used later when developers react with 👍/👎 to track true/false positive rates.

**Source file:** `sw360_agents/feedback/collector.py → store_context()`

---

## 6. Decision Points and Branching Logic

```
              GitHub webhook: pull_request
                      │
               ┌──────▼──────────────┐
               │  fetch PR diff       │
               └──────┬──────────────┘
                      │
           ┌──────────▼───────────────┐
           │ Any .java files changed? │
           └──────────┬───────────────┘
               NO     │     YES
               ▼      │
         SKIP (no     │
         review)      │
                      │
           ┌──────────▼───────────────┐
           │  Classify changed files  │
           └──────────┬───────────────┘
                      │
      ════════════════▼═══════ LAYER 1 ═══════════════
                      │
           ┌──────────▼───────────────┐
           │  For each file:          │
           │  run deterministic rules │
           └──────────┬───────────────┘
                      │
      ════════════════▼═══════ LAYER 2 ═══════════════
                      │
           ┌──────────▼───────────────────────────┐
           │  For each Java file:                  │
           │  1. Retrieve rules (RAG)              │
           │  2. Retrieve reference (RAG)          │
           │  3. Retrieve cross-file context (RAG) │
           │  4. LLM analysis                      │
           └──────────┬───────────────────────────┘
                      │
      ════════════════▼═══════ POST REVIEW ═══════════
                      │
           ┌──────────▼───────────────┐
           │  Merge + deduplicate     │
           └──────────┬───────────────┘
                      │
           ┌──────────▼────────────────────────┐
           │  Any findings?                     │
           └──────────┬────────────────────────┘
               NO     │     YES
               ▼      │
         NO REVIEW    │
         POSTED       │
               ┌──────▼───────────────────────┐
               │  Any "error" severity?        │
               └──────┬───────────────────────┘
               YES    │     NO
               ▼      ▼
         REQUEST_   COMMENT
         CHANGES
               └──────┬──────────────
                      │
               ┌──────▼──────────────┐
               │  Post GitHub review │
               └──────┬──────────────┘
                      │
               ┌──────▼──────────────┐
               │  Store feedback ctx │
               └─────────────────────┘
```

---

## 7. RAG Queries Reference

| Step | Query | Filter | k | Returns |
|------|-------|--------|---|---------|
| 4 | `"coding rules for {file_type} files"` | `type=rule, applies_to={file_type}` | 8 | Applicable rules |
| 5 | `"correct {entity} {file_type} implementation"` | `type={file_type}_method, entity={entity}` | 2 | Reference code |
| 6a | `"{entity} test method"` | `type=test_method, entity={entity}` | 2 | Test coverage check |
| 6b | `"{entity} JacksonCustomizations"` | `type=jackson_mixin` | 1 | Mixin existence |
| 6c | `"{entity} database handler"` | `type=handler_method, entity={entity}` | 2 | Handler consistency |

---

## 8. Deterministic Rules Reference

| ID | Name | Severity | Applies to | Detection |
|----|------|----------|-----------|-----------|
| R01 | License header | error | New `.java` files | `grep SPDX-License-Identifier` in lines 1-15 |
| R02 | No System.out | error | All Java | `grep System.out.print` in added lines |
| R03 | No printStackTrace | error | All Java | `grep .printStackTrace()` in added lines |
| R04 | No field @Autowired | warning | All Java | Regex: `@Autowired\s+(private\|protected)` |
| R05 | @PreAuthorize on writes | warning | Controllers | @Post/@Put/@Patch/@Delete without @PreAuthorize above |
| R06 | @Operation on endpoints | warning | Controllers | @*Mapping without @Operation above |
| R07 | Logger pattern | warning | All Java | `LoggerFactory.getLogger` (should be LogManager) |
| R08 | Signed-off-by | error | Commits | Missing `Signed-off-by:` in commit message |

---

## 9. Error Handling per Step

| Step | Possible failure | Agent behaviour |
|------|-----------------|-----------------|
| 0 | Webhook signature invalid | Reject with 401 |
| 1 | GitHub API rate limit | Retry with exponential backoff (max 3) |
| 1 | PR has 100+ files | Skip Layer 2; only run Layer 1 |
| 2 | File classification ambiguous | Default to "java" (applies generic rules) |
| 3 | Deterministic rule throws exception | Log error, skip rule, continue others |
| 4-6 | Vector store unreachable | Skip Layer 2; post Layer 1 results only |
| 7 | LLM timeout / rate limit | Retry once; if fail, skip file |
| 7 | LLM returns malformed JSON | Parse what's possible; log and skip bad entries |
| 9 | GitHub review post fails (403) | Log error; retry once; if fail, log for manual check |
| 10 | Feedback store unavailable | Log warning; review still posted (feedback lost) |

> **Recovery tip:** If Layer 2 fails entirely (LLM or vector store down), Layer 1 deterministic results are still posted. The system degrades gracefully.

---

## 10. Agent Tool Map

```
TOOLS registry (PRReviewAgent)
│
├── fetch_pr_diff                  → github.pr_analyzer.get_changed_files()
├── classify_files                 → github.pr_analyzer.classify_file()
│
│  ── Layer 1 ──
├── run_deterministic_checks       → validators.lint_rules.DeterministicLinter.check()
│                                       ├── check_license_header()
│                                       ├── check_system_out()
│                                       ├── check_print_stack_trace()
│                                       ├── check_field_autowired()
│                                       ├── check_preauthorize()
│                                       ├── check_operation_annotation()
│                                       ├── check_logger_pattern()
│                                       └── check_signed_off()
│
│  ── Layer 2 ──
├── retrieve_applicable_rules      → retriever.retrieve(type=rule)
├── retrieve_reference             → retriever.retrieve(type={file_type}_method)
├── retrieve_cross_file_context    → retriever.retrieve(type=test_method, jackson_mixin, handler_method)
├── llm_review_file                → agents.review._llm_review()
│                                       └── llm.generate(review_system_prompt + context)
│
│  ── Post Review ──
├── merge_findings                 → agents.review._deduplicate_and_prioritize()
├── post_review                    → github.reviewer.post_review()
└── store_review_context           → feedback.collector.store_context()
```

---

## 11. Full Sequence Diagram

```
GitHub     Webhook    Orchestrator   ReviewAgent    VectorStore   LLM(GPT-4o)   GitHub API
  │           │              │              │              │              │           │
  │─PR event─►│              │              │              │              │           │
  │           │─classify────►│              │              │              │           │
  │           │              │─run_review──►│              │              │           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 1: fetch diff──────────────────────►│
  │           │              │              │◄─files + patches───────────────────────── │
  │           │              │              │              │              │           │
  │           │              │              │─Step 2: classify files     │           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 3: deterministic rules│           │
  │           │              │              │  [R01-R08, local regex]    │           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 4─────►│              │           │
  │           │              │              │◄─rules──────│              │           │
  │           │              │              │─Step 5─────►│              │           │
  │           │              │              │◄─reference──│              │           │
  │           │              │              │─Step 6─────►│              │           │
  │           │              │              │◄─cross-file─│              │           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 7: LLM analyze────────►│           │
  │           │              │              │◄─review comments────────────│           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 8: merge + dedup      │           │
  │           │              │              │              │              │           │
  │           │              │              │─Step 9: post review─────────────────────►│
  │           │              │              │◄─review posted──────────────────────────── │
  │           │              │              │              │              │           │
  │           │              │              │─Step 10: store context     │           │
  │           │              │              │              │              │           │
  │◄─review notification from GitHub─────────────────────────────────────────────────│
```

---

## 12. How the LLM Orchestrates the Agent

The review agent uses a **sequential pipeline** (not a free-form LLM loop). The LLM is only called in Step 7, with structured input and expected JSON output.

**Step 7 input to LLM:**
```
system:    "You are the SW360 PR Review Agent. Analyze the diff against rules and reference..."
user:      {file_path, diff, rules, reference, cross_file_context}
```

**Step 7 expected output:**
```json
[
  {"line": 142, "severity": "error", "rule": "SW360-R02", "message": "...", "suggestion": "..."},
  {"line": 140, "severity": "warning", "rule": "SW360-R05", "message": "...", "suggestion": "..."}
]
```

The LLM does NOT decide which tools to call or what files to fetch — that's handled deterministically by the agent code. The LLM's only job is: *given this diff and this context, find violations*.

This makes the agent more **reliable and predictable** than a free-form agent loop.

---

## 13. Feedback Collection

When a developer reacts to an agent comment:

| Reaction | Meaning | Agent action |
|----------|---------|-------------|
| 👍 | Correct finding | Log true positive; increase rule confidence |
| 👎 | False positive | Log false positive; decrease rule confidence |

**Confidence adjustment:**
```python
# After each 👎
rule_confidence[rule_id] -= 0.05

# If confidence drops below threshold, demote severity
if rule_confidence[rule_id] < 0.5:
    rule_severity[rule_id] = "suggestion"  # was "warning"
```

**Weekly metrics (auto-generated):**
```
SW360 Review Agent — Week of April 28, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total reviews posted:     23
Total comments:           67
True positives (👍):      58 (87%)
False positives (👎):      9 (13%)

Top triggered rules:
  R02 (System.out):       14 findings
  R05 (@PreAuthorize):    11 findings
  L01 (missing test):      8 findings

Worst precision rules:
  R04 (@Autowired):       3/5 false positive (60%) ← needs tuning
  L03 (Jackson mixin):   2/4 false positive (50%) ← needs tuning
```

**Source file:** `sw360_agents/feedback/collector.py`

---

## 14. Debugging Tips

### Enable verbose logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or environment variable
export SW360_AGENTS_LOG_LEVEL=DEBUG
```

### Test deterministic rules on a specific file

```python
from sw360_agents.validators.lint_rules import DeterministicLinter
from sw360_agents.github.pr_analyzer import ChangedFile

linter = DeterministicLinter()

# Simulate a changed file
file = ChangedFile(
    path="rest/.../PackageController.java",
    status="modified",
    added_lines="+    System.out.println(\"hello\");\n+    @PostMapping...",
    classification="controller"
)

results = linter.check(file)
for r in results:
    print(f"{r.severity} {r.rule} line {r.line}: {r.message}")
```

### Test RAG retrieval for a file

```python
from sw360_agents.rag.retriever import HybridRetriever

retriever = HybridRetriever(config)

# What rules would the agent retrieve for a controller file?
rules = retriever.retrieve(
    query="coding rules for controller files in SW360",
    filter={"type": "rule", "applies_to": "controller"},
    k=8
)
for r in rules:
    print(f"[{r.score:.2f}] {r.text[:100]}")
```

### Inspect what the LLM sees (dry run)

```python
from sw360_agents.agents.review import PRReviewAgent

agent = PRReviewAgent(config, dry_run=True)

# Process a single file's diff
result = agent._llm_review(
    file=mock_file,
    rules=mock_rules,
    reference=mock_reference,
    cross_file=[]
)
# Prints the full prompt sent to LLM + the response
```

### Check feedback statistics

```bash
curl http://localhost:8090/api/agents/review/metrics?days=7
```

### Common errors and fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `No review posted` | No Java files changed in PR | Expected — agent only reviews Java |
| `Layer 2 skipped` | Vector store unreachable | Check Qdrant/ChromaDB is running |
| `LLM returned empty array` | Diff is clean (no violations) | Correct behaviour — no comments posted |
| `Review post failed: 422` | Comment references invalid line number | Bug in line mapping from diff; check `pr_analyzer.py` |
| `Rate limit from GitHub` | Too many PRs in short time | Increase `cooldown_same_pr` in config |
| `Confidence below threshold` | Too many 👎 reactions on a rule | Review the rule; adjust regex or disable |
| `Vector store empty` | Indexing never ran | Run `poetry run python scripts/index_codebase.py` |

