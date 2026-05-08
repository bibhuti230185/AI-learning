# SW360 Agent Hackathon Proposals

> **Siemens AgentLab Hackathon · May 2026**

This repository contains four AI agent proposals for the SW360 ecosystem, each designed to automate repetitive, error-prone developer and compliance workflows.

---

## 📁 Repository Structure

```
sw360-agent-hackathon/
├── clearing_agent/                    # Foss360 Clearing Agent
│   ├── CLEARING_TEAM_GUIDE.md         # Proposal document
│   ├── WORKFLOW.md                    # Technical workflow
│   └── diagrams/                      # Visual assets
├── endpoint_scaffolding_agent/        # Endpoint Scaffolding Agent
│   ├── ENDPOINT_SCAFFOLDING_GUIDE.md  # Proposal document
│   ├── SCAFFOLD_WORKFLOW.md           # Technical workflow
│   └── diagrams/                      # Visual assets
├── pr_review_agent/                   # PR Review Agent
│   ├── PR_REVIEW_GUIDE.md             # Proposal document
│   ├── REVIEW_WORKFLOW.md             # Technical workflow
│   └── diagrams/                      # Visual assets
├── license_compliance_agent/          # LicenseLens AI
│   ├── LICENSE_COMPLIANCE_GUIDE.md    # Proposal document
│   └── diagrams/                      # Visual assets
├── agent-feasibility-study.md         # Cross-cutting feasibility analysis
└── agent-rag-multi-agent-architecture.md  # RAG architecture patterns
```

---

## 🚀 The Four Agent Ideas

### 1. Foss360 Clearing Agent
**Tagline:** Automate the handoff, not the decision.

Automates the mechanical portions of the FOSSology↔SW360 licence clearing workflow using a two-agent architecture with explicit human-in-the-loop state handoff.

| Metric | Before | After |
|--------|--------|-------|
| Manual steps | 7 per component | 2 commands |
| Active effort | ~45 min | ~3 min |

📄 [Full Proposal](clearing_agent/CLEARING_TEAM_GUIDE.md)

---

### 2. Endpoint Scaffolding Agent
**Tagline:** Let the agent write the boilerplate, so the developer can focus on business logic.

RAG-powered code generator that retrieves patterns from the SW360 codebase and generates Controller + Service + Test code in one shot, validated against ArchUnit rules.

| Metric | Before | After |
|--------|--------|-------|
| Time per endpoint | 60-140 min | <2 min |
| CI failure rate | ~40% | ~0% |

📄 [Full Proposal](endpoint_scaffolding_agent/ENDPOINT_SCAFFOLDING_GUIDE.md)

---

### 3. PR Review Agent
**Tagline:** Let the agent catch the patterns, so the reviewer can think about the logic.

Two-layer automated review system: Layer 1 (deterministic regex rules, $0 cost) + Layer 2 (RAG-powered contextual checks, ~$0.05/PR).

| Metric | Before | After |
|--------|--------|-------|
| Time to first feedback | Hours/days | <60 seconds |
| Review rounds | 2.5 average | 1.0 average |

📄 [Full Proposal](pr_review_agent/PR_REVIEW_GUIDE.md)

---

### 4. LicenseLens AI — Compliance Guardian
**Tagline:** Detect Early, Decide Fast, Comply by Design.

IDE-native AI agent (VS Code) that detects dependency changes in real-time, classifies license obligations into three tiers (🔴🟡🔵), and enforces compliance gates at commit/build time.

| Metric | Before | After |
|--------|--------|-------|
| Time to feedback | Weeks | Seconds |
| Rework cycles | 2-3 | 0-1 |

📄 [Full Proposal](license_compliance_agent/LICENSE_COMPLIANCE_GUIDE.md)

---

## 📋 Each Proposal Includes

- **📌 Idea Title & Team Name** — Hackathon submission metadata
- **📌 Problem Abstract** (~1000 chars) — The pain point being solved
- **📌 Solution Abstract** (~1000 chars) — The proposed approach
- **📋 Invention Disclosure Questionnaire** — 6 questions for IP review
  1. Technical problem basis
  2. How solved until now
  3. Technical features solving the problem
  4. Differences from known solutions (table)
  5. Detection
  6. Related Siemens disclosures
- **🗺️ Mind Map** — Visual overview of the idea
- **❓ Problem & Solution Diagrams** — Before/After workflows
- **🏢 Value for Siemens** — Metrics table with impact
- **🏁 Hackathon Scope** — In-scope vs out-of-scope
- **❓ Q&A** — Anticipated questions and answers

---

## 🛠️ Technical Documents

- [Agent Feasibility Study](agent-feasibility-study.md) — Cross-cutting analysis of agentic patterns
- [RAG Multi-Agent Architecture](agent-rag-multi-agent-architecture.md) — Shared RAG infrastructure patterns

---

## 📅 Hackathon Timeline

| Phase | Date | Deliverable |
|-------|------|-------------|
| Idea Submission | May 2026 | This repository |
| Prototype Build | Hackathon Event | Working demo |
| Demo & Judging | End of Event | Presentation |

---

## 👥 Contributors

- Bibhuti Bhusan Dash
- (Add team members)

---

## 📜 License

Internal Siemens use. See individual proposal documents for IP considerations.
