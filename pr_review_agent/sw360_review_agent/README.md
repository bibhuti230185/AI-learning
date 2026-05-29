# SW360 PR Review Agent

> **Two-Layer Automated PR Review Agent** — catches mechanical pattern violations instantly so human reviewers can focus on logic.

## Architecture

```mermaid
graph TB
    subgraph MAL["Model Abstraction Layer"]
        A["Anthropic<br/>(Claude Opus 4.5/4.6)"]
        B["OpenAI-Compatible<br/>(GPT-4o, Azure, vLLM, Ollama)"]
        C["Custom HTTP<br/>(Siemens-trained models)"]
        A --> I["LLMProvider Interface"]
        B --> I
        C --> I
    end

    subgraph AGENT["PR Review Agent"]
        I --> L1["Layer 1: Deterministic Linter<br/>R01-R08 · regex/grep · &lt;10s · $0"]
        L1 --> L2["Layer 2: RAG + LLM Review<br/>L01-L06 · contextual · 30-60s · ~$0.05/PR"]

        subgraph RAG["RAG Components"]
            VS["Vector Store"]
            RR["Reference Retrieval"]
            CF["Cross-file Context"]
        end

        L2 --> RAG
        L2 --> MG["Merge + Deduplicate + Post GitHub Review"]
    end

    L1 --> MG
```

## Quick Start

### 1. Install

```bash
cd pr_review_agent/sw360_review_agent
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

Set environment variables:
```bash
export GITHUB_TOKEN="ghp_your_github_token"
export ANTHROPIC_API_KEY="sk-ant-your-key"  # Or OPENAI_API_KEY for OpenAI
```

### 3. Run

```bash
# Review a specific PR (dry run — prints results, does not post)
sw360-review review --repo eclipse-sw360/sw360 --pr 142

# Review and post to GitHub
sw360-review review --repo eclipse-sw360/sw360 --pr 142 --post

# Run Layer 1 lint on a local file
sw360-review lint --file src/main/java/MyController.java

# Start webhook server
sw360-review server
```

## Model Configuration

The agent is **model-agnostic** by design. Switch models by changing `config.yaml`:

### Claude (Anthropic) — Default

```yaml
model:
  provider: "anthropic"
  model_name: "claude-sonnet-4-20250514"  # or claude-opus-4-20250514
```

### OpenAI / Azure

```yaml
model:
  provider: "openai"
  model_name: "gpt-4o"
  # For Azure:
  # base_url: "https://your-deployment.openai.azure.com/openai/deployments/gpt-4o/v1"
  # api_key: "your-azure-key"
```

### Siemens-Trained Models (or any custom endpoint)

```yaml
model:
  provider: "openai"  # If your model exposes OpenAI-compatible API
  model_name: "siemens-codellm-v2"
  base_url: "https://your-internal-model.siemens.cloud/v1"
  api_key: "your-internal-key"
```

Or for fully custom endpoint formats:

```yaml
model:
  provider: "custom"
  model_name: "siemens-codellm-v2"
  base_url: "https://your-internal-model.siemens.cloud"
  api_key: "your-internal-key"
```

### Adding a New Provider Programmatically

```python
from sw360_review_agent.models import LLMProvider, LLMMessage, LLMResponse, register_provider

class SiemensLLMProvider(LLMProvider):
    async def generate(self, messages, **kwargs) -> LLMResponse:
        # Your custom implementation
        ...

    async def close(self):
        ...

# Register before creating the agent
register_provider("siemens_llm", SiemensLLMProvider)
```

Then in config:
```yaml
model:
  provider: "siemens_llm"
  model_name: "your-model"
```

## Layer 1 Rules (Deterministic)

These rules **complement** ArchUnit (78 tests) and CI — they catch what those tools miss.

| Rule | Check | Severity |
|------|-------|----------|
| R01 | Commits have Signed-off-by (DCO/ECA) | error |
| R02 | Thrift client return values null-checked | warning |
| R03 | No hardcoded credentials/secrets | error |
| R04 | Unbounded collection fetch (missing pagination) | warning |
| R05 | New Thrift fields need CouchDB migration script | warning |
| R06 | No `catch(Exception)` — use specific types | warning |

> **Note:** License headers, System.out, @Autowired, @PreAuthorize, @Operation, and LoggerFactory
> are already enforced by ArchUnit and CI. We don't duplicate those checks.

## Layer 2 Checks (AI-Powered)

Expert-level contextual analysis using RAG + LLM. Each file gets a **file-type-specific** review
(controller, service, handler, test, thrift) with tailored focus areas.

### REST API Layer
| Check | What it verifies |
|-------|-----------------|
| L01 | API backward compatibility — no breaking field/endpoint changes |
| L02 | JacksonCustomizations dual registration (ObjectMapper + SpringDoc) |
| L03 | HATEOAS/HAL responses — EntityModel, links, pagination format |

### Service & Thrift Layer
| Check | What it verifies |
|-------|-----------------|
| L04 | Thrift return values null-checked before use |
| L05 | Exception handling chain (SW360Exception → HTTP exceptions) |
| L06 | Cross-file consistency (Thrift → Handler → Service → Test) |

### Database & CouchDB Layer
| Check | What it verifies |
|-------|-----------------|
| L07 | CouchDB query efficiency — N+1 patterns, missing indexes |
| L08 | Pagination correctness — DB-side via PaginationData, not in-memory |
| L09 | CouchDB view design — type filters, reduce functions |

### Testing & Security
| Check | What it verifies |
|-------|-----------------|
| L10 | Test quality — real HTTP calls, meaningful assertions, error cases |
| L11 | Document-level permission checks — makePermission, isUserAtLeast |
| L12 | Resource management — stream/transport cleanup, no static mutability |

## Project Structure

```mermaid
graph LR
    subgraph sw360_review_agent
        PT["pyproject.toml"]
        CF["config.example.yaml"]
        DF["Dockerfile"]

        subgraph src/sw360_review_agent
            AGENT["agent.py — Orchestrator"]
            CLI["cli.py — CLI entry point"]
            CONFIG["config.py — Configuration"]
            GH["github_client.py — GitHub API"]
            LINT["lint_rules.py — Layer 1"]
            LLM["llm_reviewer.py — Layer 2"]
            MODELS["models.py — Provider abstraction"]
            RET["retriever.py — Vector store RAG"]
            SCH["schemas.py — Data models"]
            SRV["server.py — FastAPI webhook"]
        end

        subgraph tests
            T1["test_lint_rules.py"]
            T2["test_models.py"]
            T3["test_github_client.py"]
        end

        subgraph scripts
            IDX["index_codebase.py"]
        end
    end
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Lint
ruff check src/
```

## How It Works

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant WH as Webhook Server
    participant AG as PRReviewAgent
    participant L1 as Layer 1 (Linter)
    participant VS as Vector Store
    participant LLM as LLM Provider
    participant API as GitHub API

    GH->>WH: pull_request (opened/synchronize)
    WH->>AG: trigger review
    AG->>API: fetch PR diff + commits
    API-->>AG: changed files + patches
    AG->>AG: classify files

    AG->>L1: run deterministic rules (R01-R08)
    L1-->>AG: Layer 1 findings

    AG->>VS: retrieve rules + references
    VS-->>AG: RAG context
    AG->>LLM: analyze diff with context
    LLM-->>AG: Layer 2 findings

    AG->>AG: merge + deduplicate
    AG->>API: post review with inline comments
    API-->>GH: review visible on PR
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Provider abstraction** | Swap Claude/GPT/Siemens models with config change only |
| **Two-layer split** | Layer 1 is free+instant; Layer 2 only for what regex can't catch |
| **Sequential pipeline** | LLM is called once per file, not in a loop — predictable costs |
| **Graceful degradation** | If Layer 2 fails, Layer 1 still posts results |
| **50-comment cap** | GitHub API limit; errors prioritized over warnings |
