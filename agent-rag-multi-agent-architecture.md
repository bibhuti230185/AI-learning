<!--
Copyright Siemens AG, 2026.
Part of the SW360 Portal Project.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# SW360 RAG Multi-Agent System — Production Architecture

**Author:** Team Architect  
**Date:** April 2026 (updated May 2026 for standardized folder layout)  
**Status:** Architecture Finalized — Ready for Iterative Implementation  
**Version:** 2.0

**Background:** This architecture addresses the three problem areas identified in the [Feasibility Study](./agent-feasibility-study.md):
1. Endpoint development ceremony (score: 29/30)
2. PR review mechanical checks (score: 26/30)
3. License clearing workflow (score: 26/30)

## 0. Standardized Hackathon Structure (May 2026 Update)

The idea-level documents are standardized into three folders and should be used as canonical proposal references:

| Idea | Canonical proposal guide | Technical workflow guide |
|------|---------------------------|--------------------------|
| Endpoint Scaffolding Agent | `endpoint_scaffolding_agent/ENDPOINT_SCAFFOLDING_GUIDE.md` | `SCAFFOLD_WORKFLOW.md` |
| PR Review Agent | `pr_review_agent/PR_REVIEW_GUIDE.md` | `REVIEW_WORKFLOW.md` |
| FOSSology Clearing Agent | `clearing_agent/CLEARING_TEAM_GUIDE.md` | `WORKFLOW.md` |

---

## 1. Vision

A **production-grade RAG (Retrieval-Augmented Generation) multi-agent system** purpose-built for SW360 development and compliance workflows. The system addresses:

| Problem Area | Agent | How RAG Helps |
|-------------|-------|---------------|
| Endpoint scaffolding (5-6 files, 80% boilerplate) | Scaffolding Agent | Retrieves actual patterns from indexed codebase |
| PR review (60% mechanical, 2.5 rounds) | PR Review Agent | Retrieves rules + reference implementations for comparison |
| License clearing (6+ steps, 2 systems) | Clearing Agent | Tool-calling workflow (independent, non-RAG) |

The platform uses:
- **Vector-indexed SW360 knowledge base** (codebase, patterns, Thrift definitions, conventions)
- **Specialized agents** that share a common RAG engine (Scaffolding + Review)
- **Independent workflow agent** for clearing (tool-calling, no RAG needed)
- **Deployable as a service** (GitHub App / API server) with iterative improvement

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SW360 Multi-Agent Platform                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐               │
│  │  Scaffolding │   │  PR Review   │   │  Knowledge   │               │
│  │    Agent     │   │    Agent     │   │    Agent     │               │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘               │
│         │                   │                   │                       │
│         └───────────────────┼───────────────────┘                       │
│                             │                                           │
│                    ┌────────┴────────┐                                  │
│                    │   Orchestrator   │                                  │
│                    └────────┬────────┘                                  │
│                             │                                           │
│                    ┌────────┴────────┐                                  │
│                    │   RAG Engine    │                                   │
│                    │  (Vector Store) │                                   │
│                    └────────┬────────┘                                  │
│                             │                                           │
│              ┌──────────────┼──────────────┐                           │
│              │              │              │                             │
│        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐                     │
│        │  Codebase  │ │  Patterns │ │  Thrift   │                     │
│        │  Chunks    │ │  & Rules  │ │  Schemas  │                     │
│        └───────────┘ └───────────┘ └───────────┘                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│          FOSSology Clearing Agent (Independent — Tool-Calling)           │
├─────────────────────────────────────────────────────────────────────────┤
│  Agent 1 (Upload & Scan) ──► Human Review ──► Agent 2 (Report & Attach) │
│  Uses: SW360 REST API + FOSSology REST API + LLM function-calling       │
│  See: clearing_agent/CLEARING_TEAM_GUIDE.md / WORKFLOW.md               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Why RAG Multi-Agent (Not Simple Prompts)

> See [Feasibility Study §4](./agent-feasibility-study.md#4-analysis-suitability-for-agent-automation) for the full scoring matrix that led to this architecture decision.

| Approach | Limitation | RAG Multi-Agent Advantage |
|----------|-----------|--------------------------|
| Copilot prompts | Context window limit, no persistent knowledge | Retrieves exactly relevant code chunks |
| Shell linter | Only regex/pattern matching, no understanding | Understands intent, cross-file relationships |
| Single LLM call | Hallucination, no grounding in actual code | Grounded in indexed real codebase |
| Manual rules in instructions | Human must read and follow | Agent enforces automatically with full context |

**Key differentiator:** RAG ensures agents always reference the **actual current state** of the codebase, not stale training data.

**Note on Clearing Agent:** The FOSSology clearing workflow (Problem Area #3) does NOT require RAG — it uses a simpler tool-calling pattern because its steps are API calls, not code generation. It shares the platform's LLM but not the vector store.

---

## 3. System Architecture (Production)

### 3.1 Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        DEPLOYMENT                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  GitHub App (webhook receiver)                           │    │
│  │  - Receives PR events, issue events, slash commands     │    │
│  │  - Routes to Orchestrator                                │    │
│  └─────────────────────────────────┬───────────────────────┘    │
│                                    │                             │
│  ┌─────────────────────────────────┴───────────────────────┐    │
│  │  Orchestrator (FastAPI / LangGraph)                      │    │
│  │  - Task classification                                   │    │
│  │  - Agent routing                                         │    │
│  │  - Multi-step coordination                               │    │
│  │  - Memory (conversation state)                           │    │
│  └──────┬──────────────┬──────────────┬────────────────────┘    │
│         │              │              │                          │
│  ┌──────┴──────┐ ┌────┴──────┐ ┌────┴──────┐                  │
│  │ Scaffold    │ │ Review    │ │ Knowledge │                   │
│  │ Agent       │ │ Agent     │ │ Agent     │                   │
│  └──────┬──────┘ └────┬──────┘ └────┬──────┘                  │
│         │              │              │                          │
│  ┌──────┴──────────────┴──────────────┴────────────────────┐    │
│  │  RAG Engine                                              │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐    │    │
│  │  │ Embeddings │  │ Vector DB  │  │ Retriever      │    │    │
│  │  │ (OpenAI /  │  │ (ChromaDB/ │  │ (Hybrid:       │    │    │
│  │  │  local)    │  │  Qdrant/   │  │  semantic +    │    │    │
│  │  │            │  │  Pinecone) │  │  keyword)      │    │    │
│  │  └────────────┘  └────────────┘  └────────────────┘    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  LLM Backend                                             │    │
│  │  - GPT-4o / Claude 3.5 Sonnet (primary)                 │    │
│  │  - Local model fallback (CodeLlama / DeepSeek)           │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Framework** | LangGraph (Python) | Multi-agent orchestration, state machines, production-ready |
| **RAG Engine** | LangChain + ChromaDB | Mature ecosystem, easy embedding swap |
| **Vector Store** | ChromaDB (dev) / Qdrant (prod) | ChromaDB for local dev, Qdrant for scalable prod |
| **Embeddings** | OpenAI `text-embedding-3-small` or local `nomic-embed-text` | Balance of quality and cost |
| **LLM** | GPT-4o (primary) / Claude 3.5 Sonnet (fallback) | Best code understanding |
| **API Server** | FastAPI | Async, webhook handling, production-grade |
| **GitHub Integration** | PyGithub + GitHub App | Full PR/review/comment API access |
| **Deployment** | Docker + GitHub Actions self-hosted runner | Portable, reproducible |
| **Observability** | LangSmith / OpenTelemetry | Trace agent decisions, debug issues |
| **Config** | YAML + environment variables | 12-factor app principles |

### 3.3 Knowledge Base Schema

```
sw360-knowledge-base/
├── codebase/           # Chunked .java files (Controllers, Services, Handlers)
├── thrift/             # Chunked .thrift definitions with entity relationships
├── patterns/           # Extracted patterns from instructions.md
├── rules/              # Lint rules, ArchUnit rules, conventions
├── examples/           # Good PR examples, test examples
├── migrations/         # Migration script patterns
└── metadata/           # File relationships, dependency graph
```

#### Indexing Strategy

| Source | Chunk Strategy | Metadata |
|--------|---------------|----------|
| Controller `.java` files | Per-method (each endpoint is a chunk) | entity, httpMethod, path, annotations |
| Service `.java` files | Per-method | entity, thriftService, errorHandling |
| `.thrift` files | Per-entity + per-service-method | entity, fields, relationships |
| `instructions.md` | Per-section (H3 headings) | category, severity, rule_id |
| Test files | Per-test-method | entity, httpMethod, testPattern |
| `JacksonCustomizations.java` | Per-mixin-class | entity, hiddenFields, renamedFields |
| Migration scripts | Per-script | pattern_type, entity, operation |

---

## 4. Agent Specifications

### 4.1 Scaffolding Agent

**Role:** Generate complete, compilable endpoint code across multiple files.

```python
class ScaffoldingAgent:
    """
    Given an endpoint specification, generates Controller + Service + Test code
    grounded in the actual codebase patterns via RAG retrieval.
    """
    
    def run(self, spec: EndpointSpec) -> ScaffoldResult:
        # 1. Retrieve similar endpoints from vector store
        similar_endpoints = self.rag.retrieve(
            query=f"{spec.entity} {spec.http_method} endpoint",
            filter={"type": "controller_method", "entity": spec.entity},
            k=3
        )
        
        # 2. Retrieve Thrift definition for the entity
        thrift_def = self.rag.retrieve(
            query=f"{spec.entity} service methods",
            filter={"type": "thrift", "entity": spec.entity},
            k=5
        )
        
        # 3. Retrieve test patterns for the entity
        test_patterns = self.rag.retrieve(
            query=f"{spec.entity} integration test",
            filter={"type": "test_method", "entity": spec.entity},
            k=3
        )
        
        # 4. Retrieve Jackson mixin if entity has one
        mixin_context = self.rag.retrieve(
            query=f"{spec.entity} mixin JacksonCustomizations",
            filter={"type": "jackson_mixin"},
            k=1
        )
        
        # 5. Generate code using LLM with RAG context
        result = self.llm.generate(
            system=SCAFFOLD_SYSTEM_PROMPT,
            context={
                "similar_endpoints": similar_endpoints,
                "thrift_definition": thrift_def,
                "test_patterns": test_patterns,
                "mixin_context": mixin_context,
                "conventions": self.rag.retrieve("SW360 coding conventions", k=5)
            },
            user=spec.to_prompt()
        )
        
        # 6. Validate generated code
        validation = self.validator.check(result)
        if not validation.passed:
            result = self.fix_loop(result, validation.errors, max_retries=3)
        
        return result
```

**Inputs:**
```json
{
  "entity": "Package",
  "http_method": "GET",
  "path": "/{id}/vulnerabilities",
  "description": "Get all vulnerabilities associated with a package",
  "auth_level": "READ",
  "return_type": "list",
  "return_entity": "Vulnerability"
}
```

**Outputs:**
```json
{
  "files": [
    {"path": "rest/.../PackageController.java", "action": "patch", "content": "..."},
    {"path": "rest/.../SW360PackageService.java", "action": "patch", "content": "..."},
    {"path": "rest/.../test/.../PackageTest.java", "action": "patch", "content": "..."}
  ],
  "validation": {"compiles": true, "archunit_passes": true},
  "explanation": "Added GET /{id}/vulnerabilities endpoint..."
}
```

---

### 4.2 PR Review Agent

**Role:** Analyze PR diffs using RAG-retrieved pattern rules and post contextual review comments.

```python
class PRReviewAgent:
    """
    Analyzes PR diffs against SW360 conventions retrieved from the knowledge base.
    Produces structured, actionable review comments.
    """
    
    def run(self, pr: PullRequest) -> ReviewResult:
        # 1. Get changed files and diff
        changed_files = pr.get_changed_files()
        
        reviews = []
        for file in changed_files:
            # 2. Classify file type
            file_type = self.classify(file)  # controller, service, test, thrift, etc.
            
            # 3. Retrieve relevant rules for this file type
            rules = self.rag.retrieve(
                query=f"coding rules for {file_type} files in SW360",
                filter={"type": "rule", "applies_to": file_type},
                k=10
            )
            
            # 4. Retrieve reference implementation (how it SHOULD look)
            reference = self.rag.retrieve(
                query=f"good example of {file_type} in SW360",
                filter={"type": file_type, "quality": "reference"},
                k=2
            )
            
            # 5. For cross-file checks, retrieve related files
            if file_type == "controller":
                # Check if corresponding service and test exist
                related = self.rag.retrieve(
                    query=f"{file.entity} service test JacksonCustomizations",
                    filter={"entity": file.entity},
                    k=5
                )
            
            # 6. Analyze with LLM
            file_reviews = self.llm.analyze(
                system=REVIEW_SYSTEM_PROMPT,
                context={
                    "rules": rules,
                    "reference": reference,
                    "related_files": related,
                    "diff": file.diff
                }
            )
            reviews.extend(file_reviews)
        
        # 7. Deduplicate and prioritize
        reviews = self.prioritize(reviews)
        
        # 8. Post to GitHub
        self.github.post_review(pr, reviews)
        
        return ReviewResult(reviews=reviews)
```

**Outputs:**
```json
{
  "reviews": [
    {
      "file": "rest/.../PackageController.java",
      "line": 142,
      "severity": "error",
      "rule": "SW360-R02",
      "message": "Use Log4j2 logger instead of System.out.println()",
      "suggestion": "log.info(\"Processing package: {}\", packageId);",
      "reference": "See ProjectController.java:85 for correct pattern"
    }
  ],
  "summary": {
    "errors": 1,
    "warnings": 2,
    "suggestions": 1,
    "verdict": "REQUEST_CHANGES"
  }
}
```

---

### 4.3 Knowledge Agent

**Role:** Answer questions about SW360 architecture, patterns, and conventions. Serves as context provider for other agents.

```python
class KnowledgeAgent:
    """
    Answers questions about SW360 codebase, grounded entirely in RAG retrieval.
    Used by other agents as a sub-agent for context gathering.
    """
    
    def query(self, question: str, context_filter: dict = None) -> KnowledgeResult:
        # 1. Retrieve relevant chunks
        chunks = self.rag.retrieve(
            query=question,
            filter=context_filter,
            k=10
        )
        
        # 2. Generate answer grounded in retrieved context
        answer = self.llm.generate(
            system="Answer based ONLY on the provided context. Cite source files.",
            context=chunks,
            user=question
        )
        
        return KnowledgeResult(
            answer=answer,
            sources=[c.metadata["source"] for c in chunks]
        )
```

---

## 5. RAG Pipeline (Detailed)

### 5.1 Indexing Pipeline

```python
# sw360_agents/indexing/pipeline.py

class SW360IndexingPipeline:
    """
    Indexes the SW360 codebase into the vector store.
    Runs on: git push to main, scheduled daily, manual trigger.
    """
    
    def index_all(self):
        self.index_java_files()
        self.index_thrift_files()
        self.index_instructions()
        self.index_test_files()
        self.index_jackson_customizations()
        self.index_migration_patterns()
    
    def index_java_files(self):
        """Index Controller and Service files, chunked per method."""
        for file in glob("rest/**/src/main/**/*Controller.java"):
            methods = self.java_parser.extract_methods(file)
            for method in methods:
                self.vector_store.upsert(
                    id=f"{file}::{method.name}",
                    text=method.source,
                    metadata={
                        "type": "controller_method",
                        "entity": self.extract_entity(file),
                        "http_method": method.http_method,
                        "path": method.path,
                        "annotations": method.annotations,
                        "file": file,
                        "line_start": method.line_start,
                        "line_end": method.line_end
                    }
                )
    
    def index_thrift_files(self):
        """Index Thrift entity definitions and service methods."""
        for file in glob("libraries/datahandler/src/main/thrift/*.thrift"):
            entities = self.thrift_parser.extract_entities(file)
            services = self.thrift_parser.extract_services(file)
            
            for entity in entities:
                self.vector_store.upsert(
                    id=f"thrift::{entity.name}",
                    text=entity.source,
                    metadata={
                        "type": "thrift_entity",
                        "entity": entity.name,
                        "fields": [f.name for f in entity.fields],
                        "file": file
                    }
                )
            
            for service in services:
                for method in service.methods:
                    self.vector_store.upsert(
                        id=f"thrift::{service.name}::{method.name}",
                        text=method.source,
                        metadata={
                            "type": "thrift_service_method",
                            "service": service.name,
                            "method": method.name,
                            "params": method.params,
                            "return_type": method.return_type,
                            "file": file
                        }
                    )
    
    def index_instructions(self):
        """Index coding rules and conventions from instructions.md."""
        for file in glob(".github/instructions/*.md"):
            sections = self.markdown_parser.split_by_heading(file, level=3)
            for section in sections:
                self.vector_store.upsert(
                    id=f"rule::{file}::{section.heading}",
                    text=section.content,
                    metadata={
                        "type": "rule",
                        "category": section.parent_heading,
                        "applies_to": self.classify_rule_target(section),
                        "file": file
                    }
                )
```

### 5.2 Retrieval Strategy

```python
class HybridRetriever:
    """
    Combines semantic search with keyword matching for best results.
    """
    
    def retrieve(self, query: str, filter: dict = None, k: int = 5):
        # Semantic search (cosine similarity on embeddings)
        semantic_results = self.vector_store.similarity_search(
            query=query,
            filter=filter,
            k=k * 2  # Over-retrieve for reranking
        )
        
        # Keyword search (BM25 on raw text)
        keyword_results = self.bm25_index.search(
            query=query,
            filter=filter,
            k=k * 2
        )
        
        # Reciprocal Rank Fusion
        combined = self.rrf_merge(semantic_results, keyword_results)
        
        # Rerank with cross-encoder (optional, for precision)
        reranked = self.reranker.rerank(query, combined[:k*2])
        
        return reranked[:k]
```

### 5.3 Chunking Strategy

| File Type | Chunk Unit | Avg Chunk Size | Overlap |
|-----------|-----------|----------------|---------|
| Java Controller | Per method | ~50-100 lines | Method signature shared |
| Java Service | Per method | ~30-60 lines | Class context in metadata |
| Thrift definitions | Per entity / per service method | ~20-50 lines | File-level context |
| Instructions MD | Per H3 section | ~100-300 tokens | H2 heading as context |
| Test files | Per test method | ~30-50 lines | Setup/fixture shared |
| Jackson Customizations | Per mixin class | ~20-40 lines | Registration pattern |

---

## 6. Orchestrator Design (LangGraph)

```python
# sw360_agents/orchestrator/graph.py

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

class AgentState(TypedDict):
    task_type: str          # "scaffold", "review", "query"
    input: dict             # Task-specific input
    context: list           # RAG-retrieved context
    agent_outputs: dict     # Results from each agent
    final_output: dict      # Final response
    iteration: int          # For retry loops

def create_orchestrator() -> StateGraph:
    graph = StateGraph(AgentState)
    
    # Nodes
    graph.add_node("classify", classify_task)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("scaffold_agent", run_scaffold_agent)
    graph.add_node("review_agent", run_review_agent)
    graph.add_node("knowledge_agent", run_knowledge_agent)
    graph.add_node("validate", validate_output)
    graph.add_node("fix", fix_issues)
    graph.add_node("respond", format_response)
    
    # Edges
    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve_context")
    
    graph.add_conditional_edges("retrieve_context", route_to_agent, {
        "scaffold": "scaffold_agent",
        "review": "review_agent",
        "query": "knowledge_agent"
    })
    
    graph.add_edge("scaffold_agent", "validate")
    graph.add_edge("review_agent", "respond")
    graph.add_edge("knowledge_agent", "respond")
    
    graph.add_conditional_edges("validate", check_validation, {
        "pass": "respond",
        "fail": "fix"
    })
    
    graph.add_conditional_edges("fix", check_retries, {
        "retry": "validate",
        "give_up": "respond"
    })
    
    graph.add_edge("respond", END)
    
    return graph.compile()
```

### State Machine Visualization

```
┌─────────┐     ┌──────────────┐     ┌─────────────────┐
│ Classify │────→│ Retrieve Ctx │────→│ Route to Agent  │
└─────────┘     └──────────────┘     └────────┬────────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        │                      │                      │
                        ▼                      ▼                      ▼
               ┌────────────────┐    ┌─────────────────┐    ┌────────────────┐
               │ Scaffold Agent │    │  Review Agent    │    │ Knowledge Agent│
               └───────┬────────┘    └────────┬────────┘    └───────┬────────┘
                       │                      │                      │
                       ▼                      │                      │
               ┌──────────────┐               │                      │
               │   Validate   │               │                      │
               └───────┬──────┘               │                      │
                       │                      │                      │
                  pass/│\fail                  │                      │
                      │ │                     │                      │
                      │ ▼                     │                      │
                      │ ┌─────┐              │                      │
                      │ │ Fix │──retry──→validate                   │
                      │ └─────┘              │                      │
                      │                      │                      │
                      ▼                      ▼                      ▼
               ┌──────────────────────────────────────────────────────┐
               │                      Respond                          │
               └──────────────────────────────────────────────────────┘
```

---

## 7. GitHub Integration (Production)

### 7.1 GitHub App Configuration

```yaml
# github-app-manifest.yml
name: SW360 Agent
description: RAG-powered multi-agent for SW360 development workflows
url: https://sw360-agents.internal.company.com
webhook_url: https://sw360-agents.internal.company.com/webhook
permissions:
  contents: read
  pull_requests: write
  issues: read
  checks: write
events:
  - pull_request
  - pull_request_review
  - issue_comment
  - issues
```

### 7.2 Webhook Handler

```python
# sw360_agents/api/webhooks.py

from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/webhook")
async def handle_webhook(request: Request):
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()
    
    if event == "pull_request" and payload["action"] in ["opened", "synchronize"]:
        # Trigger PR Review Agent
        await orchestrator.run({
            "task_type": "review",
            "input": {
                "pr_number": payload["pull_request"]["number"],
                "repo": payload["repository"]["full_name"],
                "diff_url": payload["pull_request"]["diff_url"]
            }
        })
    
    elif event == "issue_comment":
        body = payload["comment"]["body"]
        if body.startswith("/scaffold"):
            # Trigger Scaffolding Agent via slash command
            spec = parse_scaffold_command(body)
            await orchestrator.run({
                "task_type": "scaffold",
                "input": spec
            })
        elif body.startswith("/ask"):
            # Trigger Knowledge Agent
            question = body.replace("/ask", "").strip()
            await orchestrator.run({
                "task_type": "query",
                "input": {"question": question}
            })
```

### 7.3 Slash Commands

| Command | Agent | Example |
|---------|-------|---------|
| `/scaffold GET /api/packages/{id}/vulns "Get vulns for package"` | Scaffolding | Creates endpoint + service + test |
| `/review` | Review | Re-runs review on current PR |
| `/ask "How does clearing state work?"` | Knowledge | Answers grounded in codebase |
| `/fix SW360-R02` | Scaffolding | Auto-fixes a specific lint violation |

---

## 8. Project Structure

```
sw360-agents/
├── pyproject.toml                 # Python package config (Poetry)
├── Dockerfile                     # Production container
├── docker-compose.yml             # Local dev setup
├── .env.example                   # Environment variables template
├── README.md                      # Setup and usage guide
│
├── sw360_agents/
│   ├── __init__.py
│   ├── config.py                  # Configuration management
│   │
│   ├── api/                       # FastAPI server
│   │   ├── __init__.py
│   │   ├── main.py                # App entry point
│   │   ├── webhooks.py            # GitHub webhook handlers
│   │   └── routes.py              # REST API for manual invocation
│   │
│   ├── orchestrator/              # LangGraph orchestrator
│   │   ├── __init__.py
│   │   ├── graph.py               # State machine definition
│   │   ├── state.py               # State schema
│   │   └── router.py              # Task classification/routing
│   │
│   ├── agents/                    # Specialized agents
│   │   ├── __init__.py
│   │   ├── base.py                # Base agent class
│   │   ├── scaffold.py            # Endpoint Scaffolding Agent
│   │   ├── review.py              # PR Review Agent
│   │   └── knowledge.py           # Knowledge/Q&A Agent
│   │
│   ├── rag/                       # RAG engine
│   │   ├── __init__.py
│   │   ├── indexer.py             # Indexing pipeline
│   │   ├── retriever.py           # Hybrid retrieval
│   │   ├── chunkers/              # File-type-specific chunkers
│   │   │   ├── java_chunker.py
│   │   │   ├── thrift_chunker.py
│   │   │   └── markdown_chunker.py
│   │   └── reranker.py            # Cross-encoder reranking
│   │
│   ├── github/                    # GitHub integration
│   │   ├── __init__.py
│   │   ├── client.py              # GitHub API wrapper
│   │   ├── pr_analyzer.py         # PR diff parsing
│   │   └── reviewer.py            # Review comment posting
│   │
│   ├── validators/                # Output validation
│   │   ├── __init__.py
│   │   ├── java_compiler.py       # mvn compile check
│   │   ├── archunit_check.py      # ArchUnit pre-validation
│   │   └── lint_rules.py          # Deterministic lint rules
│   │
│   └── prompts/                   # LLM prompt templates
│       ├── scaffold_system.py
│       ├── review_system.py
│       └── knowledge_system.py
│
├── tests/                         # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/                  # Sample diffs, code, Thrift defs
│
├── scripts/
│   ├── index_codebase.py          # Manual indexing trigger
│   ├── evaluate.py                # RAG quality evaluation
│   └── seed_knowledge.py          # Initial knowledge base setup
│
└── data/
    ├── chroma_db/                 # Local vector store (dev)
    └── evaluation/                # Test cases for agent evaluation
```

---

## 9. Configuration

```yaml
# config.yml
llm:
  provider: openai  # openai | azure_openai | anthropic | local
  model: gpt-4o
  temperature: 0.1
  max_tokens: 4096
  fallback_model: gpt-4o-mini

embeddings:
  provider: openai
  model: text-embedding-3-small
  dimensions: 1536

vector_store:
  provider: chromadb  # chromadb | qdrant | pinecone
  collection: sw360_knowledge
  # For Qdrant (production):
  # url: http://qdrant:6333
  # api_key: ${QDRANT_API_KEY}

retrieval:
  top_k: 10
  rerank: true
  rerank_model: cross-encoder/ms-marco-MiniLM-L-6-v2
  hybrid_alpha: 0.7  # 0.7 semantic, 0.3 keyword

github:
  app_id: ${GITHUB_APP_ID}
  private_key_path: ${GITHUB_PRIVATE_KEY_PATH}
  webhook_secret: ${GITHUB_WEBHOOK_SECRET}

validation:
  compile_check: true
  compile_command: "mvn compile -pl rest/resource-server -q"
  max_fix_retries: 3

server:
  host: 0.0.0.0
  port: 8090
  workers: 2

observability:
  langsmith_api_key: ${LANGSMITH_API_KEY}
  project: sw360-agents
  tracing: true
```

---

## 10. Implementation Roadmap (Iterative)

### Iteration 1: Foundation (Week 1-2)
**Goal:** RAG engine + Knowledge Agent working end-to-end

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-2 | Project setup (Poetry, FastAPI, Docker) | `sw360-agents/` skeleton |
| 3-4 | Java/Thrift chunkers + indexing pipeline | Indexed SW360 codebase |
| 5-6 | Hybrid retriever (semantic + BM25) | Working RAG queries |
| 7-8 | Knowledge Agent + basic API | `/ask` endpoint working |
| 9-10 | Evaluation framework + quality checks | Measured retrieval quality |

**Exit Criteria:**
- Knowledge Agent answers "How do I add a new endpoint?" with correct, grounded references
- Retrieval precision >80% on 20 test queries
- API server runs in Docker

### Iteration 2: PR Review Agent (Week 3-4)
**Goal:** Automated PR review via GitHub webhook

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-2 | GitHub App setup + webhook handler | PR events received |
| 3-4 | PR diff parser + file classifier | Structured diff analysis |
| 5-6 | Review Agent with RAG rule retrieval | Review comments generated |
| 7-8 | Review posting to GitHub + formatting | Inline comments on PRs |
| 9-10 | Test on 5 real PRs, tune false positives | Stabilized agent |

**Exit Criteria:**
- Agent posts review within 60 seconds of PR update
- False positive rate <15%
- Catches at least 5/8 deterministic rules (R01-R08)
- Posts actionable inline comments with fix suggestions

### Iteration 3: Scaffolding Agent (Week 5-6)
**Goal:** Generate compilable endpoint code via slash command

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-2 | Scaffold Agent core + prompt engineering | Generated code for GET |
| 3-4 | Validation loop (compile check + fix) | Self-healing generation |
| 5-6 | Extend to POST/PUT/DELETE | All HTTP methods |
| 7-8 | GitHub integration (slash command → PR) | `/scaffold` creates PR |
| 9-10 | Test with 5 real scenarios | Stable scaffolding |

**Exit Criteria:**
- `/scaffold GET /api/packages/{id}/vulns "Get vulns"` produces compiling code
- Generated tests pass ArchUnit Rule 3
- Agent creates a PR with the changes (not just comments)
- Works for 4/5 test scenarios without manual intervention

### Iteration 4: Production Hardening (Week 7-8)
**Goal:** Production-ready deployment with observability

| Day | Task | Deliverable |
|-----|------|-------------|
| 1-2 | LangSmith tracing + error handling | Full observability |
| 3-4 | Rate limiting, caching, deduplication | Efficient at scale |
| 5-6 | Incremental indexing (only re-index changed files) | Fast updates |
| 7-8 | Security audit (secrets, permissions, input validation) | Hardened |
| 9-10 | Documentation, runbook, on-call guide | Operational readiness |

**Exit Criteria:**
- 99% uptime over 1 week
- P95 response time <30s for review, <60s for scaffold
- No secret leakage
- Incremental re-index on push to main

---

## 11. Production Deployment

### 11.1 Docker Compose (Local Dev)

```yaml
version: '3.8'
services:
  sw360-agents:
    build: .
    ports:
      - "8090:8090"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_APP_ID=${GITHUB_APP_ID}
      - GITHUB_PRIVATE_KEY_PATH=/app/keys/github-app.pem
      - VECTOR_STORE_PATH=/app/data/chroma_db
    volumes:
      - ./data:/app/data
      - ./keys:/app/keys
      - ../sw360:/app/sw360-repo:ro  # Mount SW360 repo for indexing
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant:v1.9
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

### 11.2 Production Deployment (Kubernetes / Docker Swarm)

```yaml
# k8s-deployment.yml (simplified)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sw360-agents
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: sw360-agents
          image: registry.company.com/sw360-agents:latest
          ports:
            - containerPort: 8090
          envFrom:
            - secretRef:
                name: sw360-agents-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
```

### 11.3 CI/CD for the Agent System

```yaml
# .github/workflows/sw360-agents-ci.yml
name: SW360 Agents CI
on:
  push:
    paths: ['sw360-agents/**']
jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: |
          cd sw360-agents
          pip install poetry
          poetry install
          poetry run pytest tests/ -v
          poetry run mypy sw360_agents/
  
  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    steps:
      - run: |
          docker build -t registry.company.com/sw360-agents:${{ github.sha }} .
          docker push registry.company.com/sw360-agents:${{ github.sha }}
          # Deploy to production...
```

---

## 12. Evaluation & Quality Assurance

### 12.1 RAG Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Retrieval Precision@5** | >80% | Human-labeled relevance on 50 test queries |
| **Retrieval Recall@10** | >90% | Critical patterns found in top-10 results |
| **Answer Groundedness** | >95% | LLM answer cites retrieved sources correctly |
| **Faithfulness** | >90% | Answer doesn't hallucinate beyond context |

### 12.2 Agent Quality Metrics

| Agent | Metric | Target |
|-------|--------|--------|
| **Scaffold** | Compile success rate (first try) | >80% |
| **Scaffold** | ArchUnit pass rate | >90% |
| **Scaffold** | Pattern consistency (human eval) | >85% |
| **Review** | True positive rate | >85% |
| **Review** | False positive rate | <15% |
| **Review** | Time to review | <60 seconds |
| **Knowledge** | Answer correctness (human eval) | >90% |

### 12.3 Evaluation Pipeline

```python
# scripts/evaluate.py
class AgentEvaluator:
    def evaluate_scaffold_agent(self):
        """Run scaffold agent on known test cases and validate."""
        test_cases = load_test_cases("data/evaluation/scaffold_cases.json")
        
        for case in test_cases:
            result = scaffold_agent.run(case.input)
            
            # Check: does it compile?
            assert self.compile_check(result.files)
            
            # Check: does it match expected pattern?
            assert self.pattern_check(result.files, case.expected_pattern)
            
            # Check: are all required annotations present?
            assert self.annotation_check(result.files, case.required_annotations)
    
    def evaluate_review_agent(self):
        """Run review agent on PRs with known issues."""
        test_prs = load_test_cases("data/evaluation/review_cases.json")
        
        for pr in test_prs:
            result = review_agent.run(pr.diff)
            
            # True positive: did it find known issues?
            tp = set(result.found_rules) & set(pr.known_issues)
            
            # False positive: did it flag correct code?
            fp = set(result.found_rules) - set(pr.known_issues)
            
            precision = len(tp) / (len(tp) + len(fp))
            recall = len(tp) / len(pr.known_issues)
```

---

## 13. Iterative Improvement Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                   Continuous Improvement Loop                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. DEPLOY → Agent runs on real PRs                              │
│         │                                                        │
│  2. OBSERVE → LangSmith traces, user feedback (👍/👎)            │
│         │                                                        │
│  3. EVALUATE → Weekly metrics review                             │
│         │     - False positive examples collected                 │
│         │     - Missing rules identified                          │
│         │     - Retrieval failures logged                         │
│         │                                                        │
│  4. IMPROVE → Based on observations:                             │
│         │     - Add/update chunks in knowledge base               │
│         │     - Refine prompts                                    │
│         │     - Add new rules                                     │
│         │     - Adjust retrieval parameters                       │
│         │                                                        │
│  5. RE-DEPLOY → Updated agent with improvements                  │
│         │                                                        │
│  └──────┴──→ (back to step 1)                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Feedback mechanisms:**
- 👍/👎 reactions on review comments → label training data
- `/feedback "false positive on line 42"` slash command
- Weekly review of LangSmith traces for failures
- Monthly recall evaluation on new test cases

---

## 14. Cost Estimation

| Component | Monthly Cost (estimate) |
|-----------|------------------------|
| OpenAI GPT-4o (review: ~100 PRs × $0.05) | $5 |
| OpenAI GPT-4o (scaffold: ~20 uses × $0.10) | $2 |
| OpenAI Embeddings (re-index weekly) | $1 |
| Qdrant Cloud (1GB vectors) | $25 |
| GitHub Actions (agent CI/CD) | Included |
| Hosting (2 pods, 2GB each) | $40 |
| **Total** | **~$73/month** |

**Alternative (local models):** Replace OpenAI with self-hosted models (DeepSeek-Coder, nomic-embed) → reduces to ~$40/month (hosting only).

---

## 15. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Secrets in code indexed | Exclude `.properties`, `.env`, secrets from indexing |
| LLM data leakage | Use Azure OpenAI (data stays in tenant) or local models |
| GitHub App permissions | Minimum required: read contents, write PRs |
| Prompt injection via PR | Sanitize PR content before LLM input |
| Vector store corruption | Periodic full re-index, version-controlled config |

---

## 16. What Ships First (Minimum Viable Agent)

**Week 1-2 deliverable for production:**

1. ✅ FastAPI server receiving GitHub webhooks
2. ✅ SW360 codebase indexed in ChromaDB (local) 
3. ✅ Knowledge Agent answers questions correctly
4. ✅ PR Review Agent posts comments on PRs (deterministic rules + RAG-powered suggestions)
5. ✅ Docker compose for local dev
6. ✅ Basic evaluation passing

**This is the MVP that demonstrates value and can be iteratively improved.**

