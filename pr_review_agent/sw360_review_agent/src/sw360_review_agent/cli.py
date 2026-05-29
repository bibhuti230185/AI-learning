# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""CLI entry point for the SW360 PR Review Agent.

Usage:
    # Start webhook server
    sw360-review server

    # Review a specific PR (one-shot)
    sw360-review review --repo eclipse-sw360/sw360 --pr 142

    # Run Layer 1 only on a local diff
    sw360-review lint --file path/to/Controller.java
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configure structlog with the given level and format."""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def cmd_server(args: argparse.Namespace) -> None:
    """Start the webhook server."""
    import uvicorn

    from sw360_review_agent.config import load_config

    config = load_config(args.config)
    configure_logging(config.logging.level, config.logging.format)

    uvicorn.run(
        "sw360_review_agent.server:app",
        host=config.server.host,
        port=config.server.port,
        log_level=config.logging.level.lower(),
    )


def cmd_review(args: argparse.Namespace) -> None:
    """Review a specific PR (one-shot mode)."""
    from sw360_review_agent.agent import PRReviewAgent
    from sw360_review_agent.config import load_config

    config = load_config(args.config)
    configure_logging(config.logging.level, "console")

    # Parse owner/repo
    parts = args.repo.split("/")
    if len(parts) != 2:
        print(f"Error: --repo must be in format 'owner/repo', got '{args.repo}'")
        sys.exit(1)

    owner, repo = parts

    async def _run() -> None:
        agent = PRReviewAgent(config)
        await agent.initialize()
        try:
            if args.post:
                result = await agent.review_and_post(owner, repo, args.pr)
            else:
                result = await agent.review_pr(owner, repo, args.pr)

            # Print results
            print(f"\n{'=' * 60}")
            print(f"PR Review Results: {owner}/{repo}#{args.pr}")
            print(f"{'=' * 60}")
            print(f"Verdict: {result.verdict}")
            print(f"Layer 1 findings: {result.layer1_count}")
            print(f"Layer 2 findings: {result.layer2_count}")
            print(f"Total: {len(result.comments)}")
            print(f"{'=' * 60}")

            for comment in result.comments:
                severity_icons = {"error": "❌", "warning": "⚠️", "suggestion": "💡"}
                icon = severity_icons.get(comment.severity.value, "ℹ️")
                loc = f"{comment.file}:{comment.line}" if comment.file else "commit"
                print(f"\n{icon} [{comment.rule}] {loc}")
                print(f"   {comment.message}")
                if comment.suggestion:
                    print(f"   Fix: {comment.suggestion[:100]}")
        finally:
            await agent.close()

    asyncio.run(_run())


def cmd_lint(args: argparse.Namespace) -> None:
    """Run Layer 1 deterministic lint on a local file."""
    from pathlib import Path

    from sw360_review_agent.github_client import classify_file, _extract_added_lines
    from sw360_review_agent.lint_rules import DeterministicLinter
    from sw360_review_agent.schemas import ChangedFile

    configure_logging("INFO", "console")

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Treat all lines as "added" for local lint
    added_lines = [(i + 1, line) for i, line in enumerate(lines)]

    changed_file = ChangedFile(
        path=str(file_path),
        status="added",
        content=content,
        patch=content,
        added_lines=added_lines,
        classification=classify_file(str(file_path)),
    )

    linter = DeterministicLinter()
    findings = linter.check_file(changed_file)

    if not findings:
        print(f"✅ No issues found in {file_path}")
        return

    print(f"\n{'=' * 60}")
    print(f"Layer 1 Lint Results: {file_path}")
    print(f"{'=' * 60}")

    for f in findings:
        severity_icons = {"error": "❌", "warning": "⚠️", "suggestion": "💡"}
        icon = severity_icons.get(f.severity.value, "ℹ️")
        print(f"\n{icon} [{f.rule}] Line {f.line}")
        print(f"   {f.message}")
        if f.suggestion:
            print(f"   Fix: {f.suggestion[:120]}")

    print(f"\nTotal: {len(findings)} findings")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="sw360-review",
        description="SW360 Two-Layer PR Review Agent",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml (default: ./config.yaml)",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # server command
    server_parser = subparsers.add_parser("server", help="Start webhook server")
    server_parser.set_defaults(func=cmd_server)

    # review command
    review_parser = subparsers.add_parser("review", help="Review a specific PR")
    review_parser.add_argument("--repo", "-r", required=True, help="owner/repo")
    review_parser.add_argument("--pr", "-p", type=int, required=True, help="PR number")
    review_parser.add_argument(
        "--post", action="store_true", help="Post review to GitHub (default: dry run)"
    )
    review_parser.set_defaults(func=cmd_review)

    # lint command
    lint_parser = subparsers.add_parser("lint", help="Run Layer 1 lint on local file")
    lint_parser.add_argument("--file", "-f", required=True, help="Java file to lint")
    lint_parser.set_defaults(func=cmd_lint)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
