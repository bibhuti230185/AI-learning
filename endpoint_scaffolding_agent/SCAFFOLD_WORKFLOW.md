# Endpoint Scaffolding Agent — Workflow Guide

> **Audience:** Developers who want to understand exactly what the scaffolding agent does at each step, why it does it, and how to trace or debug it.

---

## Standardized Folder Context (May 2026)

This repository now organizes the three hackathon ideas under dedicated folders. This file remains the execution-level workflow for the endpoint scaffolding idea.

| Item | Location | Purpose |
|------|----------|---------|
| Endpoint scaffolding idea proposal (canonical) | `ENDPOINT_SCAFFOLDING_GUIDE.md` | Problem statement, value case, and hackathon framing |
| Endpoint scaffolding execution workflow (this file) | `SCAFFOLD_WORKFLOW.md` | Technical step-by-step retrieval/generation/validation flow |
| Endpoint scaffolding diagrams | `diagrams/` | Visual assets referenced by the proposal guide |

Cross-idea folder mapping (relative to `agentt_hackathon/`):
- `endpoint_scaffolding_agent/` -> Endpoint scaffolding idea and diagrams (this folder)
- `pr_review_agent/` -> PR review idea and diagrams
- `clearing_agent/` -> License clearing idea and diagrams
- `license_compliance_agent/` -> LicenseLens AI idea and diagrams

When proposal and workflow wording diverge, treat the folder guide as idea truth and this document as the technical execution truth.

---

## Table of Contents

1. [Overview](#1-overview)
2. [High-Level Workflow Diagram](#2-high-level-workflow-diagram)
3. [Scaffolding Agent — Step-by-Step](#3-scaffolding-agent--step-by-step)
   - [Step 0 — Start Agent](#step-0--start-agent)
   - [Step 1 — Parse Endpoint Specification](#step-1--parse-endpoint-specification)
   - [Step 2 — Retrieve Similar Endpoints (RAG)](#step-2--retrieve-similar-endpoints-rag)
   - [Step 3 — Retrieve Thrift Service Methods (RAG)](#step-3--retrieve-thrift-service-methods-rag)
   - [Step 4 — Retrieve Test Patterns (RAG)](#step-4--retrieve-test-patterns-rag)
   - [Step 5 — Retrieve Coding Rules (RAG)](#step-5--retrieve-coding-rules-rag)
   - [Step 6 — Retrieve Jackson Mixin Context (RAG)](#step-6--retrieve-jackson-mixin-context-rag)
   - [Step 7 — Generate Code (LLM)](#step-7--generate-code-llm)
   - [Step 8 — Validate Generated Code](#step-8--validate-generated-code)
   - [Step 9 — Fix Loop (if validation fails)](#step-9--fix-loop-if-validation-fails)
   - [Step 10 — Output Results](#step-10--output-results)
4. [Decision Points and Branching Logic](#4-decision-points-and-branching-logic)
5. [RAG Queries Reference](#5-rag-queries-reference)
6. [Validation Checks Reference](#6-validation-checks-reference)
7. [Error Handling per Step](#7-error-handling-per-step)
8. [Agent Tool Map](#8-agent-tool-map)
9. [Full Sequence Diagram](#9-full-sequence-diagram)
10. [How the LLM Orchestrates the Agent](#10-how-the-llm-orchestrates-the-agent)
11. [Debugging Tips](#11-debugging-tips)

---

## 1. Overview

The scaffolding agent is a single agent with a **RAG retrieval phase**, an **LLM generation phase**, and a **validation loop**.

| Phase | What it does | External systems |
|-------|-------------|-----------------|
| **RAG Retrieval** | Fetches relevant code chunks from vector store | ChromaDB / Qdrant |
| **LLM Generation** | Generates Controller + Service + Test code | OpenAI GPT-4o |
| **Validation** | Checks syntax, annotations, ArchUnit compliance | Local (tree-sitter, regex, optional mvn) |
| **Fix Loop** | If validation fails, sends errors back to LLM | OpenAI GPT-4o |
| **Output** | Creates PR, applies edits, or returns JSON | GitHub API |

---

## 2. High-Level Workflow Diagram

```
         User
          │
          │  /scaffold GET /api/packages/{id}/vulns "Get vulns for package"
          ▼
   ┌──────────────────────┐
   │  SCAFFOLDING AGENT   │  ◄── GPT-4o (function-calling loop)
   └────────┬─────────────┘
            │
            ├─ Step 1 ──► Parse specification from command
            ├─ Step 2 ──► Vector Store: retrieve similar endpoints (k=3)
            ├─ Step 3 ──► Vector Store: retrieve Thrift methods (k=5)
            ├─ Step 4 ──► Vector Store: retrieve test patterns (k=3)
            ├─ Step 5 ──► Vector Store: retrieve coding rules (k=5)
            ├─ Step 6 ──► Vector Store: retrieve Jackson mixin (k=1)
            ├─ Step 7 ──► LLM: generate Controller + Service + Test
            ├─ Step 8 ──► Validate: syntax, annotations, HTTP call in test
            ├─ Step 9 ──► [If fail] LLM fix → re-validate (max 3 retries)
            └─ Step 10 ─► Output: create PR / apply edits / return JSON

```

---

## 3. Scaffolding Agent — Step-by-Step

---

### Step 0 — Start Agent

**Triggered by (one of):**
```bash
# GitHub slash command
/scaffold GET /api/packages/{id}/vulnerabilities "Get vulnerabilities for a package"

# API call
curl -X POST http://localhost:8090/api/agents/scaffold -d '{"entity":"Package",...}'

# IDE agent mode
@sw360 scaffold a GET endpoint on Package for /{id}/vulnerabilities
```

**What happens:**
- Webhook / API handler receives the request.
- Orchestrator classifies task as "scaffold" and routes to `ScaffoldingAgent`.
- Agent begins its tool-calling loop.

**Files involved:**
```
sw360_agents/api/webhooks.py       ← slash command / webhook handler
sw360_agents/orchestrator/graph.py ← routes to scaffold agent
sw360_agents/agents/scaffold.py    ← ScaffoldingAgent.run()
```

---

### Step 1 — Parse Endpoint Specification

**Agent calls:** `parse_endpoint_spec`

Extracts structured data from the user's input:

```json
{
  "entity": "Package",
  "http_method": "GET",
  "path": "/{id}/vulnerabilities",
  "description": "Get vulnerabilities for a package",
  "auth_level": "READ",
  "return_type": "list",
  "return_entity": "Vulnerability"
}
```

| Field | Source | Default |
|-------|--------|---------|
| `entity` | Extracted from path (`/api/packages/...` → Package) | Required |
| `http_method` | First word in command | Required |
| `path` | Path segment after `/api/{entity}/` | Required |
| `description` | Quoted string in command | Required |
| `auth_level` | GET → READ; POST/PUT/PATCH/DELETE → WRITE | Inferred |
| `return_type` | "list" if path has no `{id}`, "single" otherwise | Inferred |
| `return_entity` | Same as entity unless specified | Same as entity |

**Source file:** `sw360_agents/agents/scaffold.py → _parse_spec()`

---

### Step 2 — Retrieve Similar Endpoints (RAG)

**Agent calls:** `retrieve_similar_endpoints`

```python
query = f"{spec.entity} {spec.http_method} endpoint"
filter = {"type": "controller_method", "entity": spec.entity}
k = 3
```

**What the vector store returns (example):**

```java
// Source: PackageController.java::getPackageById (lines 120-145)
@Operation(summary = "Get a single package", tags = {"Packages"})
@ApiResponse(responseCode = "200", description = "Package found")
@ApiResponse(responseCode = "404", description = "Package not found")
@GetMapping("/{id}")
public ResponseEntity<EntityModel<Package>> getPackageById(
        @Parameter(description = "Package ID") @PathVariable String id
) throws TException {
    User sw360User = restControllerHelper.getSw360UserFromAuthentication();
    Package pkg = packageService.getPackageById(id, sw360User);
    // ...HATEOAS assembly...
}
```

**Why this matters:** The LLM sees the *exact* pattern used in the same Controller, including annotation style, variable names, and HATEOAS wrapping.

**Source file:** `sw360_agents/agents/scaffold.py → _gather_context()`

---

### Step 3 — Retrieve Thrift Service Methods (RAG)

**Agent calls:** `retrieve_thrift_methods`

```python
query = f"{spec.entity} {spec.description} thrift service"
filter = {"type": "thrift_service_method"}
k = 5
```

**What the vector store returns (example):**

```thrift
// Source: vulnerabilities.thrift::VulnerabilityService (line 45)
list<Vulnerability> getVulnerabilitiesByPackageId(1: string packageId, 2: User user)
    throws (1: SW360Exception exp);
```

**Why this matters:** The LLM can ONLY use Thrift methods that actually exist. No hallucination of non-existent methods.

**Source file:** `sw360_agents/agents/scaffold.py → _gather_context()`

---

### Step 4 — Retrieve Test Patterns (RAG)

**Agent calls:** `retrieve_test_patterns`

```python
query = f"{spec.entity} integration test {spec.http_method}"
filter = {"type": "test_method", "entity": spec.entity}
k = 3
```

**What the vector store returns (example):**

```java
// Source: PackageTest.java::should_get_package_by_id (lines 85-105)
@Test
void should_get_package_by_id() throws Exception {
    given(this.packageServiceMock.getPackageById(eq(packageId), any()))
        .willReturn(testPackage);

    ResponseEntity<String> response = testRestTemplate
        .withBasicAuth(testUserId, testUserPassword)
        .exchange("/api/packages/" + packageId,
            HttpMethod.GET, null, String.class);

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
}
```

**Why this matters:** The generated test will call `testRestTemplate.exchange()` — satisfying ArchUnit Rule 3. Tests without HTTP calls are rejected.

**Source file:** `sw360_agents/agents/scaffold.py → _gather_context()`

---

### Step 5 — Retrieve Coding Rules (RAG)

**Agent calls:** `retrieve_rules`

```python
query = "endpoint annotations PreAuthorize Operation ApiResponse exception handling"
filter = {"type": "rule"}
k = 5
```

**What the vector store returns (example chunks):**

```markdown
## Security Patterns
Write endpoints (POST/PUT/PATCH/DELETE) MUST have @PreAuthorize("hasAuthority('WRITE')")

## Exception Handling
Catch SW360Exception, check e.getErrorCode(), throw:
- 404 → ResourceNotFoundException
- 403 → AccessDeniedException

## OpenAPI Documentation
All endpoint methods MUST have @Operation(summary=..., tags=...)
All endpoint methods MUST have @ApiResponse for success and error cases
```

**Source file:** `sw360_agents/agents/scaffold.py → _gather_context()`

---

### Step 6 — Retrieve Jackson Mixin Context (RAG)

**Agent calls:** `retrieve_mixin_context`

```python
query = f"{spec.entity} JacksonCustomizations mixin"
filter = {"type": "jackson_mixin"}
k = 1
```

**What the vector store returns (if mixin exists):**

```java
// Source: JacksonCustomizations.java (lines 220-235)
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonIgnoreProperties({"setId", "setRevision", "iteratorSize", ...})
public abstract class PackageMixin extends Package {
    @Override @JsonProperty("packageManager") abstract String getPackageManager();
}
// Registration:
// mapper.setMixInAnnotation(Package.class, PackageMixin.class);
// SpringDocUtils.getConfig().replaceWithClass(Package.class, PackageMixin.class);
```

**Why this matters:** If the endpoint returns a new entity type not yet covered by a mixin, the agent suggests adding one.

**Source file:** `sw360_agents/agents/scaffold.py → _gather_context()`

---

### Step 7 — Generate Code (LLM)

**Agent calls:** `generate_endpoint_code`

Sends all retrieved context to GPT-4o with the scaffold system prompt.

**System prompt structure:**
```
1. Task definition (entity, method, path, description, auth level)
2. Retrieved rules (from Step 5)
3. Retrieved similar endpoints (from Step 2)
4. Retrieved Thrift methods (from Step 3)
5. Retrieved test patterns (from Step 4)
6. Retrieved mixin context (from Step 6)
7. Output format instructions (3 code blocks: CONTROLLER, SERVICE, TEST)
```

**LLM response structure:**
```
### CONTROLLER_METHOD
```java
@Operation(...)
@ApiResponse(...)
@GetMapping("/{id}/vulnerabilities")
public ResponseEntity<CollectionModel<...>> getVulnerabilitiesForPackage(...) {
    ...
}
```

### SERVICE_METHOD
```java
public List<Vulnerability> getVulnerabilitiesForPackage(String packageId, User user) throws TException {
    ...
}
```

### TEST_METHOD
```java
@Test
void should_get_vulnerabilities_for_package() throws Exception {
    ...testRestTemplate.exchange(...)...
}
```
```

**Source file:** `sw360_agents/agents/scaffold.py → _generate()`

---

### Step 8 — Validate Generated Code

**Agent calls:** `validate_generated_code`

Runs 5 validation stages:

| Stage | Check | How | Fails if |
|-------|-------|-----|----------|
| 1 | Java syntax | tree-sitter Java parser | Parse error |
| 2 | @Operation present | String search in Controller code | Missing |
| 3 | @ApiResponse present | String search in Controller code | Missing |
| 4 | @PreAuthorize (writes) | Check if POST/PUT/PATCH/DELETE has it | Missing on write endpoint |
| 5 | Test has HTTP call | Search for `testRestTemplate` or `mockMvc.perform` | Missing — ArchUnit will reject |

**Optional Stage 6 (if Maven available):**
```bash
mvn compile -pl rest/resource-server -q
```

**Source file:** `sw360_agents/validators/java_validator.py → validate()`

---

### Step 9 — Fix Loop (if validation fails)

**Triggered when:** Step 8 returns errors.  
**Max retries:** 3

**Agent calls:** `fix_generated_code`

Sends to LLM:
```
## GENERATED CODE
{the 3 code blocks}

## ERRORS
- CONTROLLER: Missing @Operation annotation
- TEST: No HTTP call found — ArchUnit Rule 3 will reject this

## RULES
{retrieved coding rules from Step 5}

Fix the code. Return the same 3 code blocks with errors corrected.
```

After the LLM responds, the agent runs Step 8 again.

| Attempt | Outcome | Action |
|---------|---------|--------|
| 1 | FAIL | Fix and retry |
| 2 | FAIL | Fix and retry |
| 3 | FAIL | Report failure, output partial result with errors |
| 1-3 | PASS | Proceed to Step 10 |

**Source file:** `sw360_agents/agents/scaffold.py → _fix()`

---

### Step 10 — Output Results

**Agent calls:** `deliver_results`

Depending on the trigger mode:

| Mode | Output action | Tool used |
|------|--------------|-----------|
| GitHub slash command | Create branch + commit + PR | `github.create_pull_request()` |
| API call | Return JSON with file diffs | HTTP response |
| IDE integration | Apply edits to workspace files | Editor API |

**PR creation details (GitHub mode):**
```
Branch: feat/scaffold-package-get-vulnerabilities
Commit: feat(rest): add GET /packages/{id}/vulnerabilities endpoint

PR body:
  ## Generated by SW360 Scaffolding Agent
  
  Files modified:
  - PackageController.java (new method)
  - SW360PackageService.java (new method)
  - PackageTest.java (new test)
  
  Context sources used:
  - PackageController::getPackageById (pattern reference)
  - vulnerabilities.thrift::getVulnerabilitiesByPackageId
  - PackageTest::should_get_package_by_id (test pattern)
  
  Validation: ✅ All checks passed
```

**Source file:** `sw360_agents/github/client.py → create_scaffold_pr()`

---

## 4. Decision Points and Branching Logic

```
              /scaffold command received
                      │
               ┌──────▼──────────────┐
               │  parse spec         │
               └──────┬──────────────┘
                      │
           ┌──────────▼───────────────┐
           │ Entity valid?            │
           └──────────┬───────────────┘
               NO     │     YES
               ▼      │
          STOP (error) │
                      │
           ┌──────────▼───────────────┐
           │  RAG retrieval (Steps 2-6)│
           └──────────┬───────────────┘
                      │
           ┌──────────▼───────────────┐
           │ Thrift method found?     │
           └──────────┬───────────────┘
               NO     │     YES
               ▼      │
         WARN (agent  │
         generates    │
         stub method) │
               └──────┤
                      │
           ┌──────────▼───────────────┐
           │  LLM generation (Step 7) │
           └──────────┬───────────────┘
                      │
           ┌──────────▼───────────────┐
           │  Validate (Step 8)       │
           └──────────┬───────────────┘
              PASS     │    FAIL
               │       ▼
               │  ┌──────────────────┐
               │  │ attempts < 3?    │
               │  └────┬─────────────┘
               │  YES  │     NO
               │  ▼    ▼
               │  FIX  STOP (partial output)
               │  │
               │  └──► Validate again
               │
        ┌──────▼──────────────┐
        │  Output (Step 10)   │
        └──────┬──────────────┘
               │
          ┌────▼──────────────────────────────┐
          │ Mode?                              │
          ├── GitHub → Create PR               │
          ├── API    → Return JSON             │
          └── IDE    → Apply workspace edits   │
          └───────────────────────────────────┘
```

---

## 5. RAG Queries Reference

| Step | Query | Filter | k | Returns |
|------|-------|--------|---|---------|
| 2 | `"{entity} {method} endpoint"` | `type=controller_method, entity={entity}` | 3 | Similar controller methods |
| 3 | `"{entity} {description} thrift service"` | `type=thrift_service_method` | 5 | Available Thrift operations |
| 4 | `"{entity} integration test {method}"` | `type=test_method, entity={entity}` | 3 | Test method patterns |
| 5 | `"endpoint annotations rules"` | `type=rule` | 5 | Coding conventions |
| 6 | `"{entity} JacksonCustomizations mixin"` | `type=jackson_mixin` | 1 | Mixin definition (if exists) |

---

## 6. Validation Checks Reference

| # | Check | Applies to | Detection method | Error message |
|---|-------|-----------|-----------------|---------------|
| 1 | Java syntax valid | All 3 blocks | tree-sitter parse | `SYNTAX: Parse error at line X` |
| 2 | @Operation present | Controller | String search | `CONTROLLER: Missing @Operation` |
| 3 | @ApiResponse present | Controller | String search | `CONTROLLER: Missing @ApiResponse` |
| 4 | @PreAuthorize on writes | Controller | Regex + HTTP method check | `CONTROLLER: Write endpoint missing @PreAuthorize` |
| 5 | User extraction | Controller | String: `getSw360UserFromAuthentication` | `CONTROLLER: Missing user extraction` |
| 6 | SW360Assert validation | Service | String: `assertUser` or `assertNotEmpty` | `SERVICE: Missing input validation` |
| 7 | SW360Exception handling | Service | String: `SW360Exception` | `SERVICE: Missing exception handling` |
| 8 | @Test annotation | Test | String: `@Test` | `TEST: Missing @Test` |
| 9 | HTTP call present | Test | Regex: `testRestTemplate\|mockMvc.perform` | `TEST: No HTTP call — ArchUnit rejects` |
| 10 | Compile check | All (optional) | `mvn compile -pl rest/resource-server` | `COMPILE: {error message}` |

---

## 7. Error Handling per Step

| Step | Possible failure | Agent behaviour |
|------|-----------------|-----------------|
| 0 | Webhook parsing fails | Return 400 with error message |
| 1 | Cannot determine entity from path | Agent asks user for clarification |
| 2 | No similar endpoints found (new entity) | Agent proceeds with rules only; generates full class |
| 3 | No Thrift method found | Agent warns; generates a TODO stub in service method |
| 4 | No test patterns found | Agent uses generic TestRestTemplate pattern |
| 5 | Rules retrieval empty | Agent uses built-in minimum rules |
| 6 | No mixin found | Agent skips mixin; notes in output |
| 7 | LLM returns malformed response | Retry once; if still bad, report error |
| 8 | Validation fails | Enter fix loop (Step 9) |
| 9 | 3 fix attempts all fail | Output partial result with error list |
| 10 | GitHub PR creation fails | Report error; return JSON as fallback |

> **Recovery tip:** If the agent outputs partial results, the developer can manually fix the remaining issues. The output always includes the validation error list.

---

## 8. Agent Tool Map

```
TOOLS registry (ScaffoldingAgent)
│
├── parse_endpoint_spec            → scaffold._parse_spec()
│
├── retrieve_similar_endpoints     → retriever.retrieve(type=controller_method)
├── retrieve_thrift_methods        → retriever.retrieve(type=thrift_service_method)
├── retrieve_test_patterns         → retriever.retrieve(type=test_method)
├── retrieve_rules                 → retriever.retrieve(type=rule)
├── retrieve_mixin_context         → retriever.retrieve(type=jackson_mixin)
│
├── generate_endpoint_code         → scaffold._generate()
│                                       └── llm.generate(system_prompt + context)
│
├── validate_generated_code        → java_validator.validate()
│                                       ├── tree_sitter_parse()
│                                       ├── check_annotations()
│                                       ├── check_test_http_call()
│                                       └── run_compile() [optional]
│
├── fix_generated_code             → scaffold._fix()
│                                       └── llm.generate(fix_prompt + errors)
│
└── deliver_results                → github.create_scaffold_pr()
                                    │   or api.return_json()
                                    │   or editor.apply_edits()
```

---

## 9. Full Sequence Diagram

```
User       Webhook    Orchestrator   ScaffoldAgent   VectorStore   LLM(GPT-4o)   GitHub API
  │           │              │              │              │              │             │
  │─/scaffold─►│              │              │              │              │             │
  │           │─classify────►│              │              │              │             │
  │           │              │─run_scaffold─►│              │              │             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 1: parse spec          │             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 2──────►│              │             │
  │           │              │              │◄─similar eps─│              │             │
  │           │              │              │─Step 3──────►│              │             │
  │           │              │              │◄─thrift mtds─│              │             │
  │           │              │              │─Step 4──────►│              │             │
  │           │              │              │◄─test ptrns──│              │             │
  │           │              │              │─Step 5──────►│              │             │
  │           │              │              │◄─rules───────│              │             │
  │           │              │              │─Step 6──────►│              │             │
  │           │              │              │◄─mixin───────│              │             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 7: generate───────────►│             │
  │           │              │              │◄─3 code blocks──────────────│             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 8: validate            │             │
  │           │              │              │  [local checks]             │             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 9 (if fail): fix──────►│             │
  │           │              │              │◄─fixed code─────────────────│             │
  │           │              │              │─re-validate                 │             │
  │           │              │              │              │              │             │
  │           │              │              │─Step 10: create PR──────────────────────►│
  │           │              │              │◄─PR #142─────────────────────────────────│
  │           │              │              │              │              │             │
  │◄─PR link──│◄─────────────│◄─────────────│              │              │             │
```

---

## 10. How the LLM Orchestrates the Agent

The scaffolding agent uses a function-calling loop. The LLM sees:

1. A **system prompt** defining the scaffolding workflow steps.
2. A **user message** with the parsed endpoint specification.
3. **Tool results** (RAG chunks, validation results) appended after each call.

**Message history for a successful run:**
```
system:    "You are the SW360 Endpoint Scaffolding Agent..."
user:      "Generate GET /{id}/vulnerabilities for Package entity..."
assistant: <tool_call: retrieve_similar_endpoints(entity="Package", method="GET")>
tool:      [{"source":"PackageController::getPackageById", "content":"@Operation..."}]
assistant: <tool_call: retrieve_thrift_methods(query="Package vulnerabilities")>
tool:      [{"source":"vulnerabilities.thrift", "content":"list<Vulnerability> getVuln..."}]
assistant: <tool_call: retrieve_test_patterns(entity="Package", method="GET")>
tool:      [{"source":"PackageTest::should_get_package", "content":"@Test void..."}]
assistant: <tool_call: retrieve_rules(query="endpoint annotations")>
tool:      [{"content":"Write endpoints MUST have @PreAuthorize..."}]
assistant: <tool_call: generate_endpoint_code(spec=..., context=...)>
tool:      {"controller":"@Operation...", "service":"public List...", "test":"@Test void..."}
assistant: <tool_call: validate_generated_code(code=...)>
tool:      {"passed": true, "errors": []}
assistant: <tool_call: deliver_results(mode="github", files=...)>
tool:      {"pr_number": 142, "pr_url": "https://github.com/.../pull/142"}
assistant: "✅ PR #142 created with GET /packages/{id}/vulnerabilities endpoint."
```

**Message history for a run with fix loop:**
```
...
assistant: <tool_call: validate_generated_code(code=...)>
tool:      {"passed": false, "errors": ["TEST: No HTTP call — ArchUnit rejects"]}
assistant: <tool_call: fix_generated_code(code=..., errors=["TEST: No HTTP call..."])>
tool:      {"controller":"...", "service":"...", "test":"@Test void... testRestTemplate.exchange(...)"}
assistant: <tool_call: validate_generated_code(code=...)>
tool:      {"passed": true, "errors": []}
assistant: <tool_call: deliver_results(...)>
...
```

---

## 11. Debugging Tips

### Enable verbose logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or set env variable
export SW360_AGENTS_LOG_LEVEL=DEBUG
```

### Inspect RAG retrieval results

```python
from sw360_agents.rag.retriever import HybridRetriever
from sw360_agents.config import load_config

config = load_config()
retriever = HybridRetriever(config)

# Check what the agent retrieves for "Package GET endpoint"
results = retriever.retrieve(
    query="Package GET endpoint",
    filter={"type": "controller_method", "entity": "Package"},
    k=3
)
for r in results:
    print(f"Source: {r.metadata['file']}::{r.metadata.get('method_name','')}")
    print(f"Score: {r.score:.3f}")
    print(r.text[:200])
    print("---")
```

### Test validation without running the full agent

```python
from sw360_agents.validators.java_validator import JavaValidator

validator = JavaValidator()

test_code = '''
@Test
void should_get_vulnerabilities() {
    assertTrue(true);  // no HTTP call!
}
'''

result = validator.validate_test_method(test_code)
print(result)
# ValidationResult(passed=False, errors=["TEST: No HTTP call — ArchUnit rejects"])
```

### Inspect the full LLM conversation

```bash
# With LangSmith tracing enabled
export LANGSMITH_API_KEY=your_key
export LANGSMITH_PROJECT=sw360-agents

# Then check traces at: https://smith.langchain.com
```

### Test the full agent with a dry run

```python
from sw360_agents.agents.scaffold import ScaffoldingAgent

agent = ScaffoldingAgent(config)
result = agent.run(EndpointSpec(
    entity="Package",
    http_method="GET",
    path="/{id}/vulnerabilities",
    description="Get vulnerabilities for a package",
    auth_level="READ"
), dry_run=True)  # dry_run=True skips PR creation

print(result.files)
print(result.validation)
```

### Common errors and fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `No similar endpoints found` | Entity name mismatch in vector store | Re-index: `poetry run python scripts/index_codebase.py` |
| `No Thrift method found` | Method doesn't exist yet | Add it to `.thrift` file first, then re-index |
| `Validation: COMPILE failed` | Generated imports incorrect | Check LLM model; upgrade to GPT-4o if using mini |
| `LLM returned malformed response` | Context too long, response truncated | Reduce `k` values in retrieval config |
| `PR creation failed: 403` | GitHub App permissions | Check App has `contents: write` permission |
| `Vector store empty` | Indexing never ran | Run `poetry run python scripts/index_codebase.py` |
| `3 fix attempts failed` | Complex endpoint with unusual pattern | Generate manually, add as reference, re-index |

