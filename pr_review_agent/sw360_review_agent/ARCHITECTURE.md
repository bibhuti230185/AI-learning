# PR Review Agent — Architecture

> Technical architecture of the Project-Agnostic Two-Layer PR Review Agent.

## System Overview

```mermaid
flowchart TB
    dev["Developer"] -->|pushes PR| github["GitHub"]
    github -->|webhook event| agent["PR Review Agent"]
    agent -->|posts review| github
    agent -->|sends diff + context| llm["LLM Provider"]
    agent -->|retrieves patterns| vectordb["ChromaDB"]
    agent -->|loads config| rules["project_rules/"]
```

## Component Architecture

```mermaid
graph TB
    SRV[server.py - Webhook] --> ORC[agent.py - Orchestrator]
    CLI[cli.py - CLI] --> ORC

    ORC --> RL[rules_loader.py]
    ORC --> L1[lint_rules.py - Layer 1]
    ORC --> L2[llm_reviewer.py - Layer 2]
    ORC --> GHC[github_client.py]
    ORC --> CFG[config.py]
    ORC --> SCH[schemas.py]

    RL --> PRULES[project_rules/]
    L1 --> RL
    L2 --> RL
    L2 --> RET[retriever.py - RAG]
    L2 --> MOD[models.py - LLM Abstraction]

    GHC --> GH[GitHub API]
    MOD --> LLM[LLM Provider]
    RET --> VDB[ChromaDB]
```

## Model Provider Abstraction

The key extensibility point — swap models without code changes.

```mermaid
classDiagram
    class LLMProvider {
        +generate(messages) LLMResponse
        +close()
    }

    class AnthropicProvider {
        -client
        -model
        +generate(messages) LLMResponse
        +close()
    }

    class OpenAICompatibleProvider {
        -client
        -model
        +generate(messages) LLMResponse
        +close()
    }

    class CustomHTTPProvider {
        -client
        -model
        +generate(messages) LLMResponse
        +close()
    }

    LLMProvider <|-- AnthropicProvider
    LLMProvider <|-- OpenAICompatibleProvider
    LLMProvider <|-- CustomHTTPProvider
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
    CLASSIFY --> RELEVANT{Any relevant files?}

    RELEVANT -- No --> SKIP([Skip review])
    RELEVANT -- Yes --> L1[Layer 1: Regex lint rules]

    L1 --> L2[Layer 2: RAG + LLM analysis]
    L2 --> MERGE[Merge + Deduplicate]
    L1 --> MERGE

    MERGE --> FINDINGS{Any findings?}
    FINDINGS -- No --> DONE([No review posted])
    FINDINGS -- Yes --> ERRORS{Any errors?}

    ERRORS -- Yes --> RC[Post REQUEST_CHANGES]
    ERRORS -- No --> CM[Post COMMENT]

    RC --> POST[GitHub Review]
    CM --> POST
    POST --> DONE2([Review visible on PR])
```

## Data Flow

```mermaid
flowchart LR
    DIFF[PR Diff] --> PARSE[Parse lines]
    COMMITS[Commit Messages] --> LINT
    RULES[project_rules/] --> CLASS[Classify files]
    PARSE --> CLASS
    RULES --> LINT[Regex rules]
    CLASS --> LINT
    CLASS --> LLM_CALL[LLM + RAG]
    LINT --> COMMENTS[ReviewComments]
    LLM_CALL --> COMMENTS
    COMMENTS --> REVIEW[GitHub Review]
```

## Deployment Options

```mermaid
flowchart LR
    GH1[GitHub] -->|webhook| SRV[FastAPI Server] --> A1[Agent]
    DEV[Developer] -->|CLI| A2[Agent] -->|--post| GH2[GitHub API]
    GA[GitHub Actions] --> A3[Agent] --> GH3[GitHub API]
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
| Rules Config | YAML + Markdown | Project-specific rules (no code changes) |
| Logging | structlog | Structured JSON logging |
| Testing | pytest + pytest-asyncio | Unit & integration tests |
