# PR Review Agent — Architecture

> Technical architecture of the Two-Layer PR Review Agent.

## System Overview

```mermaid
C4Context
    title SW360 PR Review Agent — System Context

    Person(dev, "Developer", "Pushes PRs to SW360")
    System(agent, "PR Review Agent", "Two-layer automated code reviewer")
    System_Ext(github, "GitHub", "Hosts SW360 repository")
    System_Ext(llm, "LLM Provider", "Claude / GPT / Siemens model")
    SystemDb(vectordb, "Vector Store", "ChromaDB — indexed SW360 patterns")

    Rel(dev, github, "Pushes PR")
    Rel(github, agent, "Webhook: pull_request event")
    Rel(agent, github, "Posts review comments via API")
    Rel(agent, llm, "Sends diff + context for analysis")
    Rel(agent, vectordb, "Retrieves rules, references, cross-file context")
```

## Component Architecture

```mermaid
graph TB
    subgraph External
        GH["GitHub API"]
        LLM["LLM Provider<br/>(Anthropic / OpenAI / Custom)"]
        VDB["ChromaDB<br/>Vector Store"]
    end

    subgraph Agent["PR Review Agent"]
        direction TB
        SRV["server.py<br/>FastAPI Webhook"] --> ORC["agent.py<br/>Orchestrator"]
        CLI["cli.py<br/>CLI Entry Point"] --> ORC

        ORC --> L1["lint_rules.py<br/>Layer 1: Deterministic"]
        ORC --> L2["llm_reviewer.py<br/>Layer 2: RAG + LLM"]
        ORC --> GHC["github_client.py<br/>GitHub Client"]

        L2 --> RET["retriever.py<br/>RAG Retriever"]
        L2 --> MOD["models.py<br/>LLM Provider Abstraction"]

        GHC --> GH
        MOD --> LLM
        RET --> VDB
    end

    subgraph Config
        CFG["config.py<br/>Configuration"]
        SCH["schemas.py<br/>Data Models"]
    end

    ORC --> CFG
    ORC --> SCH
```

## Model Provider Abstraction

The key extensibility point — swap models without code changes.

```mermaid
classDiagram
    class LLMProvider {
        <<abstract>>
        +generate(messages, temperature, max_tokens, response_format) LLMResponse
        +close()
    }

    class AnthropicProvider {
        -client: AsyncAnthropic
        -model: str
        +generate(...) LLMResponse
        +close()
    }

    class OpenAICompatibleProvider {
        -client: AsyncOpenAI
        -model: str
        +generate(...) LLMResponse
        +close()
    }

    class CustomHTTPProvider {
        -client: AsyncClient
        -model: str
        +generate(...) LLMResponse
        +close()
    }

    class LLMMessage {
        +role: str
        +content: str
    }

    class LLMResponse {
        +content: str
        +model: str
        +usage: dict
        +raw: Any
    }

    LLMProvider <|-- AnthropicProvider
    LLMProvider <|-- OpenAICompatibleProvider
    LLMProvider <|-- CustomHTTPProvider
    LLMProvider ..> LLMMessage : accepts
    LLMProvider ..> LLMResponse : returns
```

### Adding a New Provider

```mermaid
flowchart LR
    A[Implement LLMProvider ABC] --> B[Call register_provider]
    B --> C[Set provider name in config.yaml]
    C --> D[Agent uses your provider]
```

## Review Pipeline

```mermaid
flowchart TD
    START([GitHub Webhook]) --> FETCH[Fetch PR Diff]
    FETCH --> CLASSIFY[Classify Changed Files]
    CLASSIFY --> JAVA{Any .java files?}

    JAVA -- No --> SKIP([Skip review])
    JAVA -- Yes --> LAYER1

    subgraph LAYER1["Layer 1 — Deterministic (< 10s, $0)"]
        R01["R01: License header"]
        R02["R02: No System.out"]
        R03["R03: No printStackTrace"]
        R04["R04: No field @Autowired"]
        R05["R05: @PreAuthorize"]
        R06["R06: @Operation"]
        R07["R07: Log4j2 logger"]
        R08["R08: Signed-off-by"]
    end

    LAYER1 --> LAYER2

    subgraph LAYER2["Layer 2 — RAG + LLM (30-60s, ~$0.05)"]
        RAG1["Retrieve rules for file type"]
        RAG2["Retrieve reference implementation"]
        RAG3["Retrieve cross-file context"]
        ANALYZE["LLM analyzes diff vs context"]
        RAG1 --> ANALYZE
        RAG2 --> ANALYZE
        RAG3 --> ANALYZE
    end

    LAYER2 --> MERGE[Merge + Deduplicate]
    LAYER1 --> MERGE

    MERGE --> FINDINGS{Any findings?}
    FINDINGS -- No --> DONE([No review posted])
    FINDINGS -- Yes --> ERRORS{Any errors?}

    ERRORS -- Yes --> RC["POST: REQUEST_CHANGES"]
    ERRORS -- No --> CM["POST: COMMENT"]

    RC --> POST[Post GitHub Review]
    CM --> POST
    POST --> DONE2([Review visible on PR])
```

## Data Flow

```mermaid
flowchart LR
    subgraph Input
        DIFF["PR Diff<br/>(patches)"]
        COMMITS["Commit Messages"]
    end

    subgraph Processing
        PARSE["Parse added lines<br/>+ line numbers"]
        CLASS["Classify files<br/>(controller/service/test/...)"]
        LINT["Regex/grep<br/>rule checks"]
        LLM_CALL["LLM analysis<br/>with RAG context"]
    end

    subgraph Output
        COMMENTS["ReviewComment[]<br/>(file, line, severity,<br/>rule, message, suggestion)"]
        REVIEW["GitHub Review<br/>(inline comments)"]
    end

    DIFF --> PARSE --> CLASS
    CLASS --> LINT --> COMMENTS
    CLASS --> LLM_CALL --> COMMENTS
    COMMITS --> LINT
    COMMENTS --> REVIEW
```

## Deployment Options

```mermaid
flowchart TB
    subgraph Option1["Option A: Webhook Server"]
        GH1["GitHub"] -->|webhook| SRV1["FastAPI Server<br/>(Docker / VM)"]
        SRV1 --> AGENT1["PR Review Agent"]
    end

    subgraph Option2["Option B: CLI One-Shot"]
        DEV["Developer"] -->|sw360-review review| AGENT2["PR Review Agent"]
        AGENT2 -->|optional --post| GH2["GitHub API"]
    end

    subgraph Option3["Option C: GitHub Action"]
        GA["GitHub Actions<br/>on: pull_request"] --> AGENT3["PR Review Agent"]
        AGENT3 --> GH3["GitHub API"]
    end
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | Async-first, rich ecosystem |
| Web Framework | FastAPI | Webhook receiver |
| LLM (default) | Claude Opus 4.5/4.6 | Contextual code analysis |
| Vector Store | ChromaDB | RAG retrieval |
| HTTP Client | httpx | Async GitHub API calls |
| Config | Pydantic + YAML | Type-safe configuration |
| Logging | structlog | Structured JSON logging |
| Testing | pytest + pytest-asyncio | Unit & integration tests |
