# FOSSology Clearing Agent — Workflow Guide

> **Audience:** Developers and compliance engineers who want to understand exactly what each agent does at each step, why it does it, and how to trace or debug it.

---

## Standardized Folder Context (May 2026)

This repository now organizes the three hackathon ideas under dedicated folders. This file remains the execution-level workflow for the clearing idea.

| Item | Location | Purpose |
|------|----------|---------|
| Clearing idea proposal (canonical) | `CLEARING_TEAM_GUIDE.md` | Business problem, value, scope, and proposal framing |
| Clearing execution workflow (this file) | `WORKFLOW.md` | Step-by-step technical runtime behavior |
| Clearing diagrams | `diagrams/` | Visual assets referenced by the proposal guide |

Cross-idea folder mapping (relative to `agentt_hackathon/`):
- `endpoint_scaffolding_agent/` -> Endpoint scaffolding idea and diagrams
- `pr_review_agent/` -> PR review idea and diagrams
- `clearing_agent/` -> License clearing idea and diagrams (this folder)
- `license_compliance_agent/` -> LicenseLens AI idea and diagrams

When proposal and workflow wording diverge, treat the folder guide as idea truth and this document as the technical execution truth.

---

## Table of Contents

1. [Overview](#1-overview)
2. [High-Level Workflow Diagram](#2-high-level-workflow-diagram)
3. [Agent 1 — Upload & Scan (Step-by-Step)](#3-agent-1--upload--scan-step-by-step)
   - [Step 0 — Start Agent 1](#step-0--start-agent-1)
   - [Step 1 — Fetch Release Metadata](#step-1--fetch-release-metadata)
   - [Step 2 — Identify Source Attachments](#step-2--identify-source-attachments)
   - [Step 3 — User Selects Attachment](#step-3--user-selects-attachment-if-needed)
   - [Step 4 — List FOSSology Folders](#step-4--list-fossology-folders)
   - [Step 5 — User Selects or Creates Folder](#step-5--user-selects-or-creates-target-folder)
   - [Step 6 — Upload Attachment to FOSSology](#step-6--upload-attachment-to-fossology)
   - [Step 7 — Trigger Automated Scan](#step-7--trigger-automated-scan)
   - [Step 8 — Wait for Scan to Complete](#step-8--wait-for-scan-to-complete)
   - [Step 9 — Save Handoff State](#step-9--save-handoff-state)
4. [Human Clearing Review](#4-human-clearing-review)
5. [Agent 2 — Report & Attach (Step-by-Step)](#5-agent-2--report--attach-step-by-step)
   - [Step 10 — Start Agent 2](#step-10--start-agent-2)
   - [Step 11 — Load Handoff State](#step-11--load-handoff-state)
   - [Step 12 — Check Clearing Status](#step-12--check-clearing-status)
   - [Step 13 — Generate Clearing Report](#step-13--generate-clearing-report)
   - [Step 14 — Attach Report to SW360](#step-14--attach-report-to-sw360)
   - [Step 15 — Mark Complete](#step-15--mark-complete)
6. [Decision Points and Branching Logic](#6-decision-points-and-branching-logic)
7. [API Calls Reference](#7-api-calls-reference)
8. [Error Handling per Step](#8-error-handling-per-step)
9. [Agent Tool Maps](#9-agent-tool-maps)
10. [Full Sequence Diagram](#10-full-sequence-diagram)
11. [How the LLM Orchestrates Each Agent](#11-how-the-llm-orchestrates-each-agent)
12. [Debugging Tips](#12-debugging-tips)

---

## 1. Overview

The workflow is split across **two independent agents**, with a human clearing review step between them.

| | Agent 1 | Human step | Agent 2 |
|---|---|---|---|
| **Command** | `python main.py upload` | (in FOSSology UI) | `python main.py report` |
| **Automated?** | Yes (2 interactive prompts) | No — manual review | Yes (0 prompts) |
| **Handoff** | Writes `state/<release_id>.json` | Sets upload status to "Closed" | Reads state file, polls status |

The two agents share no live connection — Agent 2 can run on the same machine hours or days after Agent 1, triggered by any team member.

---

## 2. High-Level Workflow Diagram

```
         User
          │
          │  python main.py upload --release-id <id>
          ▼
   ┌──────────────────┐
   │     AGENT 1      │  ◄── OpenAI gpt-4o (function-calling loop)
   └────────┬─────────┘
            │
            ├─ Step 1 ──► SW360 REST API   GET /releases/{id}
            ├─ Step 2 ──► Filter SOURCE / SOURCE_SELF attachments
            ├─ Step 3 ──► [Interactive] User picks attachment (if >1)
            ├─ Step 4 ──► FOSSology REST   GET /folders
            ├─ Step 5 ──► [Interactive] User picks / creates folder
            ├─ Step 6 ──► SW360 download → FOSSology POST /uploads
            ├─ Step 7 ──► FOSSology POST /jobs
            ├─ Step 8 ──► FOSSology GET /jobs/{id}  (poll until done)
            └─ Step 9 ──► Write state/<release_id>.json

                  ╔══════════════════════════════════════╗
                  ║   HUMAN CLEARING REVIEW (FOSSology)  ║
                  ║   → set upload status to "Closed"    ║
                  ╚═══════════════╤══════════════════════╝

          │  python main.py report --release-id <id>
          ▼
   ┌──────────────────┐
   │     AGENT 2      │  ◄── OpenAI gpt-4o (function-calling loop)
   └────────┬─────────┘
            │
            ├─ Step 10 ─► Read state/<release_id>.json
            ├─ Step 11 ─► FOSSology GET /uploads/{id}  (check clearingStatus)
            ├─ Step 12 ─► FOSSology POST /report
            ├─ Step 13 ─► FOSSology GET /report/{id}   (poll until ready)
            ├─ Step 14 ─► SW360 POST /releases/{id}/attachments
            └─ Step 15 ─► Update state file → REPORT_ATTACHED
```

---

## 3. Agent 1 — Upload & Scan (Step-by-Step)

---

### Step 0 — Start Agent 1

**Triggered by:**
```bash
python main.py upload --release-id <RELEASE_ID>
```

**What happens:**
- `config.yaml` is loaded (SW360 token, FOSSology token, OpenAI key).
- `run_upload_agent()` is called in `agent_upload.py`.
- The OpenAI loop starts with the system prompt:
  > *"You are FOSSology Upload Agent (Agent 1 of 2)…"*

**Files involved:**
```
main.py            ← CLI subcommand dispatch
config.py          ← config loading
agent_upload.py    ← run_upload_agent() and tool loop
```

---

### Step 1 — Fetch Release Metadata

**Agent 1 calls:** `get_release`

```
GET /resource/api/releases/{release_id}
Authorization: Bearer <sw360-token>
```

**Data returned to agent:**
```json
{
  "id": "abc123",
  "name": "libcurl",
  "version": "7.85.0",
  "clearingState": "NEW_CLEARING",
  "attachments": [
    {"id": "att001", "filename": "libcurl-7.85.0.tar.gz", "attachmentType": "SOURCE"},
    {"id": "att002", "filename": "libcurl-7.85.0.pdf",    "attachmentType": "DOCUMENT"}
  ]
}
```

**Source file:** `tools/sw360_tools.py → get_release()`

---

### Step 2 — Identify Source Attachments

**Agent 1 calls:** `get_source_attachments`

Filters the attachment list to only `SOURCE` and `SOURCE_SELF` types — the only types meaningful for FOSSology license scanning.

| Result | Next action |
|--------|-------------|
| 0 source attachments | Agent 1 informs user and **stops** |
| 1 source attachment | Auto-selected, no prompt |
| ≥ 2 source attachments | → Step 3 |

**Source file:** `tools/sw360_tools.py → get_source_attachments()`

---

### Step 3 — User Selects Attachment *(if needed)*

**Agent 1 calls:** `ask_user_attachment_selection`  
**Only triggered when:** ≥ 2 source attachments exist.

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  #  │  ID     │  Filename                    │  Type   │  Date  │
  │  1  │  att001 │  libcurl-7.85.0.tar.gz       │  SOURCE │  2024  │
  │  2  │  att003 │  libcurl-7.85.0-patched.tgz  │  SOURCE │  2024  │
  └──────────────────────────────────────────────────────────────────┘
  Select attachment to send [1-2]: _
```

**Source file:** `agent_upload.py → _ask_user_attachment_selection()`

---

### Step 4 — List FOSSology Folders

**Agent 1 calls:** `list_fossology_folders`

```
GET /repo/api/v1/folders
Authorization: Bearer <fossology-token>
```

Returns a list of `{id, name, description, parent}` — passed directly to Step 5.

**Source file:** `tools/fossology_tools.py → list_folders()`

---

### Step 5 — User Selects or Creates Target Folder

**Agent 1 calls:** `ask_user_folder_selection`

```
  ┌──────────────────────────────────────────────────────────────┐
  │  #  │  ID  │  Name                │  Description            │
  │  1  │   1  │  Software Repository │                         │
  │  2  │   5  │  Networking Libs     │  curl, openssl…         │
  │  3  │  —   │  Create new folder…  │                         │
  └──────────────────────────────────────────────────────────────┘
  Select folder [1-3]: _
```

**If user creates a new folder:**
```
POST /repo/api/v1/folders
Body: {"name": "...", "description": "...", "parent": <parent_id>}
```

**Source file:** `agent_upload.py → _ask_user_folder_selection()`  
**FOSSology tool:** `tools/fossology_tools.py → create_folder()`

---

### Step 6 — Upload Attachment to FOSSology

**Agent 1 calls:** `upload_to_fossology`

#### 6a — Download from SW360
```
GET /resource/api/releases/{release_id}/attachments/{attachment_id}
```
File is streamed into a temporary directory.

#### 6b — Upload to FOSSology
```
POST /repo/api/v1/uploads
folderId: <selected_folder_id>
Content-Type: multipart/form-data
fileInput: <binary>
```

Response returns the new `upload_id` (e.g. `42`).

**Source file:** `agent_upload.py → _upload_to_fossology()`

---

### Step 7 — Trigger Automated Scan

**Agent 1 calls:** `run_fossology_scan`

```
POST /repo/api/v1/jobs
Body:
{
  "uploadId": 42,
  "uploadTreeId": 0,
  "folder": 5,
  "agents": {"nomos": true, "monk": true, "ojo": true, "package": true, "keyword": true}
}
```

| Agent | Purpose |
|-------|---------|
| `nomos` | SPDX-style license text detection |
| `monk` | Bulk license match against known texts |
| `ojo` | Package URL and SPDX ID detection |
| `package` | Package metadata extraction |
| `keyword` | Custom keyword search |

**Source file:** `tools/fossology_tools.py → trigger_scan()`

---

### Step 8 — Wait for Scan to Complete

Polls every **20 seconds**:
```
GET /repo/api/v1/jobs/{job_id}
```

| Status | Action |
|--------|--------|
| `Processing` | Wait 20 s, poll again |
| `Completed` | Proceed to Step 9 |
| `Failed` | Agent 1 reports failure and stops |

**Timeout:** 3600 s (1 hour). **Source file:** `tools/fossology_tools.py → wait_for_scan()`

---

### Step 9 — Save Handoff State

**Agent 1 calls:** `save_handoff_state`

Writes `state/<release_id>.json`:

```json
{
  "release_id": "abc123def456",
  "release_name": "libcurl",
  "release_version": "7.85.0",
  "attachment_filename": "libcurl-7.85.0.tar.gz",
  "upload_id": 42,
  "folder_id": 5,
  "job_id": 117,
  "saved_at": "2026-04-30T09:15:00+00:00",
  "agent1_status": "SCAN_COMPLETE"
}
```

Agent 1 then prints the next-step instructions and exits.

**Source file:** `state.py → save_state()`

---

## 4. Human Clearing Review

This step is **entirely manual** — the agents do not interact with it.

1. Open FOSSology in a browser.
2. Navigate to the uploaded file in the folder selected in Step 5.
3. Review all license findings (nomos results, monk matches, etc.).
4. Make clearing decisions: accept licenses, add copyright statements, resolve ambiguities.
5. When the review is complete → set the upload **Clearing Status → Closed**.

FOSSology clearing status values:

| Status | Meaning |
|--------|---------|
| `open` | Scan done, review not started |
| `in progress` | Clearing engineer is actively reviewing |
| `closed` | Review complete ✅ — Agent 2 can proceed |
| `rejected` | Clearing rejected ❌ — must be resolved manually |

---

## 5. Agent 2 — Report & Attach (Step-by-Step)

---

### Step 10 — Start Agent 2

**Triggered by:**
```bash
python main.py report --release-id <RELEASE_ID>          # check once
python main.py report --release-id <RELEASE_ID> --wait   # poll until closed
```

**Files involved:**
```
main.py           ← CLI subcommand dispatch
config.py         ← config loading
agent_report.py   ← run_report_agent() and tool loop
```

---

### Step 11 — Load Handoff State

**Agent 2 calls:** `load_handoff_state`

Reads `state/<release_id>.json` written by Agent 1. If the file does not exist (Agent 1 was never run), Agent 2 stops with a clear error.

Returns: `upload_id`, `folder_id`, `attachment_filename`, `release_name`, `release_version`.

**Source file:** `state.py → load_state()`

---

### Step 12 — Check Clearing Status

**Agent 2 calls:** `check_clearing_status`

```
GET /repo/api/v1/uploads/{upload_id}
```

Reads the `clearingStatus` field from the FOSSology upload object.

| Status returned | Agent 2 action |
|-----------------|----------------|
| `closed` | Proceed to Step 13 immediately |
| `open` / `in progress` | Report status to user; stop (or poll if `--wait`) |
| `rejected` | Inform user and stop |

**With `--wait`:** Agent 2 calls `wait_for_clearing_closed` which polls every **60 seconds** until status is `closed` (timeout: 24 hours).

**Source file:** `tools/fossology_tools.py → get_upload_clearing_status()`, `wait_for_clearing_closed()`

---

### Step 13 — Generate Clearing Report

**Agent 2 calls:** `generate_and_attach_report`

#### 13a — Request report
```
POST /repo/api/v1/report?uploadId=42&reportFormat=spdx2
```
Response: `{"message": "Report is being generated, id: 88"}`

#### 13b — Poll until ready
```
GET /repo/api/v1/report/88
accept: application/octet-stream
```

| HTTP | Meaning | Action |
|------|---------|--------|
| `202` | Not ready | Wait 10 s, retry |
| `200` | Report ready | Download file |

**Timeout:** 600 s (10 min).

**Supported report formats:**

| `--report-format` | Extension | Standard |
|---|---|---|
| `spdx2` *(default)* | `.spdx` | SPDX 2.x |
| `spdx2tv` | `.spdx` | SPDX 2.x tag:value |
| `dep5` | `.txt` | Debian DEP-5 |
| `readmeoss` | `.txt` | README_OSS |
| `unifiedreport` | `.xlsx` | FOSSology Excel report |

**Source file:** `tools/fossology_tools.py → request_report()`, `download_report()`

---

### Step 14 — Attach Report to SW360

Still within `generate_and_attach_report`:

```
POST /resource/api/releases/{release_id}/attachments
Content-Type: multipart/form-data

file:            <report binary>
attachmentType:  CLEARING_REPORT
checkStatus:     ACCEPTED
comment:         "FOSSology SPDX2 clearing report"
```

The report appears in SW360 → release → Attachments tab with type `CLEARING_REPORT`.

**Source file:** `tools/sw360_tools.py → attach_report_to_release()`

---

### Step 15 — Mark Complete

**Agent 2 calls:** `mark_workflow_complete`

Updates `state/<release_id>.json`:
```json
{
  "agent2_status": "REPORT_ATTACHED",
  "completed_at": "2026-04-30T14:32:00+00:00"
}
```

This release will no longer appear in `python main.py status`.

**Source file:** `state.py → mark_complete()`

---

## 6. Decision Points and Branching Logic

```
              python main.py upload
                      │
               ┌──────▼──────┐
               │ get_release  │
               └──────┬───────┘
                      │
           ┌──────────▼───────────────┐
           │ Source attachments found? │
           └──────────┬───────────────┘
               NO     │     YES
               ▼      │
             STOP      │
                  ┌────▼──────────────┐
                  │ count == 1?       │
                  └────┬──────────────┘
               YES     │   NO
               │       ▼
               │   ask user to pick
               └────────┬────────────
                        │
               ┌────────▼──────────────────┐
               │  list FOSSology folders    │
               └────────┬──────────────────┘
                        │
               ┌────────▼──────────────────────────────┐
               │  user picks folder or creates new one  │
               └────────┬──────────────────────────────┘
                        │
               ┌────────▼──────────────┐
               │  upload to FOSSology  │
               └────────┬──────────────┘
                        │
               ┌────────▼──────────────┐
               │  trigger scan + wait  │
               └────────┬──────────────┘
              FAIL       │    SUCCESS
               ▼         │
             STOP    ┌────▼──────────────┐
                     │  save state file  │
                     └────┬──────────────┘
                          │
                      AGENT 1 DONE
                    (human review now)

              python main.py report
                      │
               ┌──────▼──────────────┐
               │  load state file    │
               └──────┬──────────────┘
                      │
               ┌──────▼───────────────────────┐
               │  check FOSSology clearingStatus│
               └──────┬───────────────────────┘
          closed       │    open/in progress    rejected
            │          ▼            │              ▼
            │      inform user      │            STOP
            │      (stop or poll)   │
            │◄──────────────────────┘ (if --wait, poll until closed)
            │
     ┌──────▼──────────────────────┐
     │  generate + download report │
     └──────┬──────────────────────┘
            │
     ┌──────▼──────────────────────┐
     │  attach report to SW360     │
     └──────┬──────────────────────┘
            │
     ┌──────▼──────────────────────┐
     │  mark state complete        │
     └──────┬──────────────────────┘
            │
        AGENT 2 DONE
```

---

## 7. API Calls Reference

| Step | Agent | Method | Endpoint | System |
|------|-------|--------|----------|--------|
| 1 | 1 | `GET` | `/resource/api/releases/{id}` | SW360 |
| 2 | 1 | `GET` | `/resource/api/releases/{id}` | SW360 (reused) |
| 4 | 1 | `GET` | `/repo/api/v1/folders` | FOSSology |
| 5 (create) | 1 | `POST` | `/repo/api/v1/folders` | FOSSology |
| 6a | 1 | `GET` | `/resource/api/releases/{id}/attachments/{att_id}` | SW360 |
| 6b | 1 | `POST` | `/repo/api/v1/uploads` | FOSSology |
| 7 | 1 | `POST` | `/repo/api/v1/jobs` | FOSSology |
| 8 | 1 | `GET` | `/repo/api/v1/jobs/{job_id}` | FOSSology (polled) |
| 12 | 2 | `GET` | `/repo/api/v1/uploads/{upload_id}` | FOSSology |
| 13a | 2 | `POST` | `/repo/api/v1/report?uploadId=…&reportFormat=…` | FOSSology |
| 13b | 2 | `GET` | `/repo/api/v1/report/{report_id}` | FOSSology (polled) |
| 14 | 2 | `POST` | `/resource/api/releases/{id}/attachments` | SW360 |

---

## 8. Error Handling per Step

| Step | Possible failure | Agent behaviour |
|------|-----------------|-----------------|
| 1 | Release ID not found (404) | HTTP error → agent reports and stops |
| 2 | No source attachments | Agent 1 informs user and stops cleanly |
| 5 | Folder creation fails | HTTP error → agent 1 reports and stops |
| 6b | Upload timeout (large file) | `requests.Timeout` → agent 1 reports and stops |
| 7 | Job creation fails | HTTP error → agent 1 reports and stops |
| 8 | Scan status `Failed` | Agent 1 reports failure and stops (no state saved) |
| 8 | Scan timeout > 1 hour | `TimeoutError` → agent 1 reports and stops |
| 11 | State file missing | `FileNotFoundError` → agent 2 stops with instructions to run Agent 1 first |
| 12 | Status `rejected` | Agent 2 informs user and stops |
| 13b | Report timeout > 10 min | `TimeoutError` → agent 2 reports and stops |
| 14 | Attachment upload fails | HTTP error → agent 2 reports; report not attached (re-run Agent 2) |

> **Recovery tip for step 14 failure:** The FOSSology upload, scan, and report are already done. Just re-run Agent 2 — it will reload the state, re-check the status (still closed), and retry the report generation and attachment.

---

## 9. Agent Tool Maps

### Agent 1 (`agent_upload.py`)

```
TOOLS registry
│
├── get_release                    → sw360_tools.get_release()
├── get_source_attachments         → sw360_tools.get_source_attachments()
├── ask_user_attachment_selection  → agent_upload._ask_user_attachment_selection()
├── list_fossology_folders         → fossology_tools.list_folders()
├── ask_user_folder_selection      → agent_upload._ask_user_folder_selection()
│                                       └── fossology_tools.create_folder()  [if new]
├── upload_to_fossology            → agent_upload._upload_to_fossology()
│                                       ├── sw360_tools.download_attachment()
│                                       └── fossology_tools.upload_file()
├── run_fossology_scan             → agent_upload._run_fossology_scan()
│                                       ├── fossology_tools.trigger_scan()
│                                       └── fossology_tools.wait_for_scan()
└── save_handoff_state             → state.save_state()
```

### Agent 2 (`agent_report.py`)

```
TOOLS registry
│
├── load_handoff_state             → state.load_state()
├── check_clearing_status          → agent_report._check_clearing_status()
│                                       └── fossology_tools.get_upload_clearing_status()
├── wait_for_clearing_closed       → agent_report._wait_for_clearing_closed()
│                                       └── fossology_tools.wait_for_clearing_closed()
├── generate_and_attach_report     → agent_report._generate_and_attach_report()
│                                       ├── fossology_tools.request_report()
│                                       ├── fossology_tools.download_report()
│                                       └── sw360_tools.attach_report_to_release()
└── mark_workflow_complete         → state.mark_complete()
```

---

## 10. Full Sequence Diagram

```
User       main.py    agent_upload    OpenAI     SW360 API   FOSSology API
  │           │              │           │             │              │
  │─upload────►│              │           │             │              │
  │           │─run_upload───►│           │             │              │
  │           │              │─messages──►│             │              │
  │           │              │◄─tool_call─│ get_release │              │
  │           │              │────────────────────────── ►             │
  │           │              │◄────────────────────────               │
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ get_source_attachments     │
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ list_fossology_folders     │
  │           │              │─────────────────────────────────────── ►
  │           │              │◄────────────────────────────────────────
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ ask_user_folder_selection  │
  │◄─table────│◄─────────────│            │             │              │
  │─pick──────►│──────────────►│            │             │              │
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ upload_to_fossology        │
  │           │              │────────────────────────── ►             │
  │           │              │◄────────────────────────               │
  │           │              │──────────────────────────────────────── ►
  │           │              │◄────────────────────────────────────────
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ run_fossology_scan         │
  │           │              │──────────────────────────────────────── ►
  │           │              │  [poll every 20s until Completed]        │
  │           │              │◄────────────────────────────────────────
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ save_handoff_state         │
  │           │              │  [writes state/abc123.json]              │
  │           │              │─result────►│             │              │
  │           │              │◄─final msg─│             │              │
  │◄─summary──│◄─────────────│            │             │              │
  │           │              │            │             │              │
  │    ════════════════ HUMAN CLEARING REVIEW ════════════════════     │
  │                                                                    │
  │─report────►│                                                        │
  │           │   agent_report                                         │
  │           │─run_report───►│           │             │              │
  │           │              │─messages──►│             │              │
  │           │              │◄─tool_call─│ load_handoff_state         │
  │           │              │  [reads state/abc123.json]               │
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ check_clearing_status      │
  │           │              │──────────────────────────────────────── ►
  │           │              │◄────────────────────────────────────────
  │           │              │─result────►│  (status: closed)          │
  │           │              │◄─tool_call─│ generate_and_attach_report │
  │           │              │──────────────────────────────────────── ►
  │           │              │  [POST /report, poll /report/{id}]       │
  │           │              │◄────────────────────────────────────────
  │           │              │────────────────────────── ►             │
  │           │              │◄────────────────────────               │
  │           │              │─result────►│             │              │
  │           │              │◄─tool_call─│ mark_workflow_complete     │
  │           │              │  [updates state file]                    │
  │           │              │◄─final msg─│             │              │
  │◄─summary──│◄─────────────│            │             │              │
```

---

## 11. How the LLM Orchestrates Each Agent

Each agent is an independent OpenAI function-calling loop. The model never sees source code — it operates on:

1. A **system prompt** defining its role and the exact steps it must follow.
2. A **user message** containing the release ID and any flags (e.g. `--wait`, `--report-format`).
3. **Tool results** (JSON) appended to the message history after each call.

The model decides: which tool to call next, what arguments to pass (extracted from prior results), and when to stop (no more tool calls → produce final summary).

**Agent 1 message history:**
```
system:    "You are FOSSology Upload Agent (Agent 1 of 2)…"
user:      "Start upload workflow for release abc123…"
assistant: <tool_call: get_release("abc123")>
tool:      {"name":"libcurl","attachments":[…]}
assistant: <tool_call: get_source_attachments("abc123")>
tool:      [{"id":"att001","filename":"libcurl-7.85.0.tar.gz"}]
assistant: <tool_call: list_fossology_folders()>
tool:      [{"id":5,"name":"Networking Libs"},…]
assistant: <tool_call: ask_user_folder_selection(folders=[…])>
tool:      {"id":5,"name":"Networking Libs"}
assistant: <tool_call: upload_to_fossology(…)>
tool:      {"upload_id":42,"folder_id":5}
assistant: <tool_call: run_fossology_scan(upload_id=42,folder_id=5)>
tool:      {"status":"Completed","job_id":117}
assistant: <tool_call: save_handoff_state(…)>
tool:      {"state_file":"state/abc123.json","status":"saved"}
assistant: "Upload and scan complete…"   ← loop ends
```

**Agent 2 message history:**
```
system:    "You are FOSSology Report Agent (Agent 2 of 2)…"
user:      "Generate report for release abc123…"
assistant: <tool_call: load_handoff_state("abc123")>
tool:      {"upload_id":42,"folder_id":5,"attachment_filename":"libcurl-7.85.0.tar.gz"}
assistant: <tool_call: check_clearing_status(upload_id=42)>
tool:      {"clearing_status":"closed"}
assistant: <tool_call: generate_and_attach_report(upload_id=42,release_id="abc123")>
tool:      {"status":"attached"}
assistant: <tool_call: mark_workflow_complete("abc123")>
tool:      {"status":"complete"}
assistant: "Workflow complete. Report attached."   ← loop ends
```

---

## 12. Debugging Tips

### Enable HTTP request logging

In `main.py`, before calling `run_upload_agent()` or `run_report_agent()`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect the full message history

In `agent_upload.py` or `agent_report.py`, add after the `while True` loop:

```python
import json
print(json.dumps(messages, indent=2, default=str))
```

### Test individual tools without running the agent

```python
from config import load_config
from tools import get_release, list_folders, get_upload_clearing_status

cfg = load_config()

# Check SW360 connectivity
print(get_release(cfg, "abc123def456"))

# Check FOSSology folders
print(list_folders(cfg))

# Check upload clearing status (after Agent 1 has run)
print(get_upload_clearing_status(cfg, upload_id=42))
```

### Inspect the state file

```bash
cat state/abc123def456.json
```

### Common errors and fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `401 Unauthorized` on SW360 | Token expired | Regenerate: SW360 → Admin → REST API |
| `401 Unauthorized` on FOSSology | Token expired | Regenerate: FOSSology → Admin → API Tokens |
| `404 Not Found` on release | Wrong release ID | Confirm in SW360 UI → Releases |
| `No state file found for release '…'` | Agent 1 was never run | Run `python main.py upload --release-id <ID>` first |
| `TimeoutError` on scan | Very large source archive | Increase `timeout_sec` in `wait_for_scan()` |
| `No source attachments found` | Only binary/doc attachments | Add a SOURCE attachment in SW360 first |
| Clearing status `rejected` | Human cleared the upload as rejected | Resolve in FOSSology UI, then re-run Agent 2 |
   - [Step 2 — Identify Source Attachments](#step-2--identify-source-attachments)
