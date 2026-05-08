<!--
Copyright Siemens AG, 2026.
Part of the SW360 Portal Project.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# SW360 AI Agent — Feasibility Study

**Author:** Team Architect  
**Date:** April 2026 (updated May 2026 for standardized folder layout)  
**Purpose:** Background investigation to identify areas in SW360 workflows that would benefit from AI agent automation.

---

## 0. Standardized Hackathon Structure (May 2026 Update)

The hackathon content is now standardized into three idea folders. These folders are the source of truth for each idea's proposal narrative, diagrams, and idea-specific details.

| Idea | Standard folder | Canonical proposal document |
|------|-----------------|-----------------------------|
| Endpoint Scaffolding Agent | `endpoint_scaffolding_agent/` | `endpoint_scaffolding_agent/ENDPOINT_SCAFFOLDING_GUIDE.md` |
| PR Review Agent | `pr_review_agent/` | `pr_review_agent/PR_REVIEW_GUIDE.md` |
| FOSSology Clearing Agent | `clearing_agent/` | `clearing_agent/CLEARING_TEAM_GUIDE.md` |

Top-level workflow files remain as execution-level technical walkthroughs:
- `SCAFFOLD_WORKFLOW.md`
- `REVIEW_WORKFLOW.md`
- `WORKFLOW.md`

---

## 1. Study Objective

Investigate the SW360 development and operational workflows to identify:
- Repetitive, manual, high-ceremony tasks
- Error-prone areas where humans consistently fail
- Bottlenecks that slow down delivery and onboarding
- Processes that span multiple disconnected systems

**Outcome:** A prioritized list of problem areas where agentic AI workflows can deliver measurable improvement.

---

## 2. Methodology

| Activity | What we examined |
|----------|-----------------|
| Codebase analysis | ArchUnit rules, CI pipeline, file change patterns across 60+ endpoints |
| Contributor friction | Common CI failure reasons, PR review comment patterns, onboarding blockers |
| Workflow observation | Clearing team's manual steps across SW360 and FOSSology |
| Rule documentation | `.github/instructions/*.md` — rules that exist but aren't enforced programmatically |
| CI failure data | `build_and_test.yml` — where builds fail most often |

---

## 3. Problem Areas Identified

### 3.1 Endpoint Development Ceremony

**Observation:** Every new REST endpoint in SW360 requires touching 5-6 files across multiple architectural layers. The pattern is identical every time but is not automated.

**Current process:**
```
1. Controller method     → @Operation, @ApiResponse, @PreAuthorize, HATEOAS
2. Service method        → ThriftClient, exception handling, SW360Assert
3. Integration test      → TestRestTemplate/MockMvc call
4. REST docs spec test   → Spring REST Docs snippet
5. JacksonCustomizations → Mixin if new fields (dual registration)
6. AsciiDoc             → API documentation
```

**Evidence of pain:**

| Observation | Evidence |
|-------------|----------|
| Build fails if steps 1-3 incomplete | ArchUnit `TestCoverageCompletenessRulesTest` — enforced at CI |
| 7 classes already excluded from ArchUnit | `EXCLUDED_CLASSES` in test — pre-existing gaps because it's hard |
| ~30% of first PR pushes fail on ArchUnit | Tests miss `TestRestTemplate` call |
| New contributors take 140 min per endpoint | vs 60 min for experienced developers |
| 80% of endpoint code is boilerplate | Only ~20% is business-specific logic |
| No scaffolding tooling exists | No `mvn archetype:generate`, no codegen for endpoints |

**Key pain points:**
- **High ceremony-to-logic ratio** — developer spends most time on boilerplate
- **Late validation** — errors only surface at build time in CI
- **Pattern drift** — copy-paste leads to subtle inconsistencies over time
- **Annotation complexity** — `@Operation`, `@ApiResponse`, `@PreAuthorize`, `@Parameter` all required
- **Jackson mixin dual registration** — must register in both ObjectMapper AND SpringDocUtils

---

### 3.2 Pull Request Review Inefficiency

**Observation:** Human reviewers repeatedly catch the same categories of mechanical mistakes across PRs from 40+ contributors. ~60% of review comments are about pattern violations, not business logic.

**Current process:**
```
1. Developer submits PR
2. Wait hours/days for reviewer
3. Reviewer manually checks: license headers, annotations, DI patterns,
   exception handling, logger usage, test patterns, commit format
4. Author fixes → re-submits
5. Repeat 2-3 times until all patterns correct
6. Reviewer finally reviews business logic
```

**Evidence of pain:**

| Observation | Evidence |
|-------------|----------|
| 2.5 review rounds on average | Multiple round-trips before merge |
| 60% of comments are mechanical | Same issues flagged repeatedly across PRs |
| Different reviewers catch different things | No consistency in what gets flagged |
| Hours to days for first feedback | Reviewer availability bottleneck |
| CI already checks formatting (Spotless) but NOT patterns | Gap between formatting and architecture checks |

**Top 10 recurring review issues (by frequency):**

| # | Issue | Frequency | Category |
|---|-------|-----------|----------|
| 1 | Missing license header on new files | 3-4 PRs/week | Mechanical |
| 2 | Commit message format wrong | 3-4 PRs/week | Mechanical |
| 3 | Field injection (`@Autowired` on field) | 2-3 PRs/week | Pattern |
| 4 | Thrift return value not null-checked | 2-3 PRs/week | Safety |
| 5 | `System.out.println` used | 1-2 PRs/week | Mechanical |
| 6 | Missing `@Operation` annotation | 2 PRs/week | Pattern |
| 7 | Wrong exception handling pattern | 1-2 PRs/week | Pattern |
| 8 | Missing `@PreAuthorize` on write endpoint | 1 PR/week | Security |
| 9 | Jackson mixin not updated | 1 PR/week | Cross-file |
| 10 | Test without HTTP call (ArchUnit rejects) | 1 PR/week | Pattern |

**Key pain points:**
- **Reviewer fatigue** — humans tire of repeating the same feedback
- **Slow feedback loop** — author context-switches while waiting
- **Inconsistency** — what gets caught depends on who reviews
- **Onboarding friction** — new contributors fail 3-4 times before patterns are internalized
- **No SW360-specific linting** — Spotless checks formatting, ArchUnit checks structure, but nothing checks SW360 domain patterns

---

### 3.3 License Clearing Workflow

**Observation:** The clearing team performs a 6+ step manual process across two disconnected systems (SW360 and FOSSology) for every release that needs license compliance clearance.

**Current process:**
```
1. Open SW360 → navigate to release → find source attachment → download
2. Open FOSSology → decide folder → upload file → wait for processing
3. Schedule scan agents (nomos, monk, ojo, keyword) → wait 5-60 min
4. ── HUMAN CLEARING REVIEW ── (cannot be automated)
   Reviewer inspects findings, resolves license decisions, sets status to "Closed"
5. Generate report (SPDX, ReadmeOSS, etc.) → wait → download
6. Go back to SW360 → navigate to same release → upload report as CLEARING_REPORT
```

**Evidence of pain:**

| Observation | Evidence |
|-------------|----------|
| 6+ manual browser steps across 2 systems | Each step requires navigation, waiting, file transfer |
| No standard folder naming in FOSSology | Uploads go to wrong folders; hard to audit |
| Easy to forget step 6 | Report generated but never attached back to SW360 |
| Hard to hand off mid-process | If person who started is away, work stalls |
| 1 engineer × 20 releases = 120+ manual steps | Linear scaling, no parallelism |
| Active time per release: 30-60 min | Excluding the human review step itself |

**Key pain points:**
- **System fragmentation** — workflow spans SW360 + FOSSology with no integration
- **State loss** — no shared state between steps; person-dependent context
- **Forgotten steps** — step 6 (attaching report) is regularly missed
- **No automation boundary** — clear split between automatable steps (1-3, 5-6) and human step (4)
- **Scaling problem** — effort is linear per release with no tooling leverage

---

### 3.4 Additional Areas Considered (Lower Priority)

| Area | Observation | Why lower priority |
|------|-------------|-------------------|
| **CouchDB migrations** | Schema changes need Python migration scripts | Infrequent (per release only) |
| **Thrift definition changes** | Adding fields requires multi-file coordination | Well-documented; less error-prone in practice |
| **Dependency updates** | Dependabot handles CVE detection | Already automated |
| **Docker build issues** | Occasional failures in container builds | Not frequent enough |

---

## 4. Analysis: Suitability for Agent Automation

### 4.1 Evaluation Criteria

| Criterion | Definition |
|-----------|-----------|
| **Repetitive** | Same pattern executed identically many times |
| **Rule-based** | Clear rules exist (even if not enforced) |
| **Multi-step** | Involves multiple actions/files/systems in sequence |
| **Error-prone** | Humans frequently get it wrong |
| **High-frequency** | Happens daily or multiple times per sprint |
| **Measurable** | Success/failure can be objectively measured |

### 4.2 Scoring Matrix

| Area | Repetitive | Rule-based | Multi-step | Error-prone | High-freq | Measurable | **Total** |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Endpoint scaffolding** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★ | ★★★★★ | **29/30** |
| **PR review (patterns)** | ★★★★★ | ★★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★★ | **26/30** |
| **License clearing** | ★★★★★ | ★★★★ | ★★★★★ | ★★★★ | ★★★★ | ★★★★ | **26/30** |
| CouchDB migration | ★★★ | ★★★ | ★★★★ | ★★★ | ★★ | ★★★ | **18/30** |
| Dependency management | ★★★★ | ★★★★ | ★★ | ★★ | ★★★ | ★★★★ | **19/30** |

### 4.3 Findings

The top three areas score significantly higher (26-29) than others (18-19), confirming they are prime candidates for agentic automation:

1. **Endpoint Scaffolding (29/30)** — Highest score. Perfectly repetitive, fully rule-based, patterns are well-defined, failure is immediate (CI), and frequency is high.

2. **PR Review Patterns (26/30)** — Rules exist in documentation but aren't enforced. Every PR is an opportunity. Cross-file checks require understanding context.

3. **License Clearing (26/30)** — Multi-system workflow with a clear automation boundary (human review cannot be automated, but everything else can).

---

## 5. Conclusion & Recommendation

### Problem Areas Confirmed for Agent Introduction

| # | Problem Area | Why an Agent | Type of Agent Needed |
|---|-------------|-------------|---------------------|
| 1 | **Endpoint development ceremony** | 80% boilerplate, 5-6 files, ArchUnit enforced, grounding needed in actual code patterns | Code generation agent (RAG-grounded) |
| 2 | **PR review mechanical checks** | 60% of comments are pattern violations that could be caught automatically with rules + context | Review/analysis agent (deterministic + LLM) |
| 3 | **License clearing workflow** | 6+ steps across 2 systems, clear automation boundary, state management needed | Multi-step workflow agent (tool-calling) |

### What We Ruled Out

| Area | Why not now |
|------|-----------|
| CouchDB migrations | Too infrequent to justify agent complexity |
| Dependency management | Already handled by Dependabot |
| Docker builds | Failures are rare and varied (not pattern-based) |

---

## 6. References

| Reference | What it tells us |
|-----------|-----------------|
| `.github/instructions/sw360_backend.instructions.md` | All the rules that exist but aren't enforced |
| `.github/workflows/build_and_test.yml` | CI pipeline structure, where failures happen |
| `rest/.../architecture/TestCoverageCompletenessRulesTest.java` | ArchUnit rules that block PRs |
| `rest/.../resourceserver/project/ProjectController.java` | Example of the endpoint pattern (4747 lines) |
| `clearing_agent/CLEARING_TEAM_GUIDE.md` / `WORKFLOW.md` | Documented clearing workflow pain and execution detail |
| PR history and review comments | Patterns in reviewer feedback |

---

## Appendix: Document Outputs from This Study

Based on the findings above, the following solution documents were produced:

| Document | Addresses Problem Area |
|----------|----------------------|
| [`endpoint_scaffolding_agent/ENDPOINT_SCAFFOLDING_GUIDE.md`](./endpoint_scaffolding_agent/ENDPOINT_SCAFFOLDING_GUIDE.md) | #1 Endpoint development (idea proposal) |
| [`SCAFFOLD_WORKFLOW.md`](./SCAFFOLD_WORKFLOW.md) | #1 Technical workflow |
| [`pr_review_agent/PR_REVIEW_GUIDE.md`](./pr_review_agent/PR_REVIEW_GUIDE.md) | #2 PR review (idea proposal) |
| [`REVIEW_WORKFLOW.md`](./REVIEW_WORKFLOW.md) | #2 Technical workflow |
| [`clearing_agent/CLEARING_TEAM_GUIDE.md`](./clearing_agent/CLEARING_TEAM_GUIDE.md) | #3 License clearing (idea proposal) |
| [`WORKFLOW.md`](./WORKFLOW.md) | #3 Technical workflow |
| [`agent-rag-multi-agent-architecture.md`](./agent-rag-multi-agent-architecture.md) | Platform architecture (shared) |
