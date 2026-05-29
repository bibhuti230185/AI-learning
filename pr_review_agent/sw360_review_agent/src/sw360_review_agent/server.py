# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""FastAPI webhook server — receives GitHub PR events and triggers reviews."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Header, Request

from sw360_review_agent.agent import PRReviewAgent
from sw360_review_agent.config import load_config

logger = structlog.get_logger(__name__)

_agent: PRReviewAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and cleanup agent."""
    global _agent
    config = load_config()
    _agent = PRReviewAgent(config)
    await _agent.initialize()
    logger.info("agent_ready", repository=config.github.repository)
    yield
    if _agent:
        await _agent.close()


app = FastAPI(
    title="SW360 PR Review Agent",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
) -> dict[str, Any]:
    """Handle GitHub webhook events.

    Triggered by: pull_request (opened, synchronize)
    """
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    body = await request.body()

    # Verify webhook signature
    if not _agent._github.verify_webhook_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Only handle pull_request events
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event type: {x_github_event}"}

    payload = await request.json()
    action = payload.get("action", "")

    # Only review on opened or synchronize (new push)
    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "reason": f"action: {action}"}

    # Extract PR info
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})

    owner = repo_data.get("owner", {}).get("login", "")
    repo = repo_data.get("name", "")
    pr_number = pr_data.get("number", 0)

    if not owner or not repo or not pr_number:
        raise HTTPException(status_code=400, detail="Missing PR info in payload")

    logger.info(
        "webhook_received",
        event=x_github_event,
        action=action,
        pr=pr_number,
        repo=f"{owner}/{repo}",
    )

    # Run review asynchronously (fire and forget for webhook response)
    # In production, use a task queue. For hackathon, inline is fine.
    try:
        result = await _agent.review_and_post(owner, repo, pr_number)
        return {
            "status": "reviewed",
            "pr": pr_number,
            "findings": len(result.comments),
            "verdict": result.verdict,
        }
    except Exception as exc:
        logger.error("review_failed", pr=pr_number, error=str(exc))
        return {"status": "error", "message": str(exc)}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "sw360-pr-review-agent"}


@app.get("/api/agents/review/metrics")
async def metrics() -> dict[str, Any]:
    """Review agent metrics (placeholder for feedback tracking)."""
    return {
        "total_reviews": 0,
        "total_comments": 0,
        "true_positives": 0,
        "false_positives": 0,
    }
