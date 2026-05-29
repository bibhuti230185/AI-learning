#!/usr/bin/env python3
"""Quick test script — reviews a PR from eclipse-sw360/sw360 using Siemens model.

Usage:
    cd pr_review_agent/sw360_review_agent
    python scripts/test_review.py <pr_number> [owner/repo]

Examples:
    python scripts/test_review.py 4168
    python scripts/test_review.py 4223 eclipse-sw360/sw360

Reads tokens from environment variables:
    GITHUB_TOKEN  — GitHub PAT with repo scope
    OPENAI_API_KEY — Siemens LLM API key (SIAK-...)
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sw360_review_agent.config import load_config, AgentConfig
from sw360_review_agent.agent import PRReviewAgent


async def main():
    # Load env from .github/.env file if not set
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".github" / ".env"
    if not env_file.exists():
        # Try alternate path
        env_file = Path(r"D:\OneDrive - Siemens AG\sw360-agent-hackathon\.github\.env")

    if env_file.exists():
        print(f"Loading env from: {env_file}")
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and value and key not in os.environ:
                        os.environ[key] = value
    else:
        print(f"WARNING: .env file not found at {env_file}")

    # Verify required env vars
    github_token = os.environ.get("GITHUB_TOKEN", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not github_token:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set (needed for Siemens LLM)")
        sys.exit(1)

    print(f"GitHub token: ...{github_token[-4:]}")
    print(f"LLM API key: ...{api_key[-4:]}")

    # Load config
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(config_path)

    # Inject secrets from env
    config.github.token = github_token
    config.model.api_key = api_key

    # Target PR from command-line args
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_review.py <pr_number> [owner/repo]")
        sys.exit(1)

    pr_number = int(sys.argv[1])
    if len(sys.argv) >= 3 and "/" in sys.argv[2]:
        owner, repo = sys.argv[2].split("/", 1)
    else:
        owner = "eclipse-sw360"
        repo = "sw360"

    print(f"\n{'='*60}")
    print(f"Reviewing: {owner}/{repo}#{pr_number}")
    print(f"Model: {config.model.model_name} @ {config.model.base_url}")
    print(f"{'='*60}\n")

    # Create agent and run review (DRY RUN — no posting to GitHub)
    agent = PRReviewAgent(config)

    try:
        await agent.initialize()
        result = await agent.review_pr(owner, repo, pr_number)

        # Print results
        print(f"\n{'='*60}")
        print(f"REVIEW RESULTS")
        print(f"{'='*60}")
        print(f"Verdict: {result.verdict}")
        print(f"Layer 1 findings: {result.layer1_count}")
        print(f"Layer 2 findings: {result.layer2_count}")
        print(f"Total comments: {len(result.comments)}")
        print(f"{'='*60}\n")

        if not result.comments:
            print("✅ No issues found — code looks clean!")
        else:
            for comment in result.comments:
                severity_icons = {"error": "❌", "warning": "⚠️", "suggestion": "💡"}
                icon = severity_icons.get(comment.severity.value, "ℹ️")
                loc = f"{comment.file}:{comment.line}" if comment.file else "commit-level"
                print(f"{icon} [{comment.rule}] {loc}")
                print(f"   {comment.message}")
                if comment.suggestion:
                    suggestion_preview = comment.suggestion[:120]
                    print(f"   💡 Fix: {suggestion_preview}")
                print()

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
