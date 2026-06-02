#!/usr/bin/env python3
"""Configurable codebase indexer — indexes key patterns into ChromaDB.

This indexer reads its configuration from project_rules/indexing.yaml,
making it usable for any project without code changes.

Usage:
    python scripts/index_codebase.py [--repo-path /path/to/repo] [--rules-dir ./project_rules]
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import chromadb
import yaml

BATCH_SIZE = 10


def load_indexing_config(rules_dir: Path) -> dict:
    """Load indexing configuration from project_rules/indexing.yaml."""
    config_path = rules_dir / "indexing.yaml"
    if not config_path.exists():
        print(f"Warning: {config_path} not found, using defaults")
        return {
            "project_name": "project",
            "scan_dirs": [{"path": "src", "include_patterns": ["**/*.java"]}],
            "file_matchers": {
                "controller": {"suffix": "Controller.java", "exclude_suffix": "Test.java"},
                "service": {"suffix": "Service.java", "exclude_suffix": "Test.java"},
                "handler": {"suffix": "Handler.java"},
                "test": {"suffix": "Test.java"},
            },
            "exclude_patterns": ["target", ".git", "node_modules", "__pycache__"],
            "max_doc_length": 1500,
            "extraction_mode": "signatures",
            "references_dir": "project_rules/references",
        }

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_file_type(fname: str, file_matchers: dict) -> str | None:
    """Determine file type based on configured matchers."""
    for type_name, matcher in file_matchers.items():
        suffix = matcher.get("suffix", "")
        exclude_suffix = matcher.get("exclude_suffix", "")
        if suffix and fname.endswith(suffix):
            if exclude_suffix and fname.endswith(exclude_suffix):
                continue
            return type_name
    return None


def get_file_summary(file_path: Path, file_type: str, repo_path: Path, config: dict) -> list[tuple[str, str, dict]]:
    """Extract a compact summary from a source file."""
    max_length = config.get("max_doc_length", 1500)
    extraction_mode = config.get("extraction_mode", "signatures")

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []

    # Build entity name from filename
    stem = file_path.stem
    for suffix in ["Controller", "Service", "Handler", "DatabaseHandler", "Test", "SpecTest"]:
        stem = stem.replace(suffix, "")
    for prefix in ["Sw360", "SW360"]:
        stem = stem.replace(prefix, "")
    entity = stem

    rel_path = str(file_path.relative_to(repo_path))
    doc_id = f"{file_type}_{file_path.stem}"

    if extraction_mode == "signatures":
        lines = content.split("\n")
        summary_lines = []
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith("package ")
                or stripped.startswith("import ")
                or stripped.startswith("public class ")
                or stripped.startswith("public interface ")
                or re.match(r'\s*(public|protected)\s+\S+\s+\w+\s*\(', line)
                or stripped.startswith("@")
                or stripped.startswith("private static final Logger")
                or stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("async def ")):
                summary_lines.append(line)
        summary = "\n".join(summary_lines)[:max_length]
    else:
        summary = content[:max_length]

    if len(summary) < 50:
        return []

    return [(doc_id, summary, {
        "type": f"{file_type}_method",
        "entity": entity,
        "source": rel_path,
        "method": "class_summary",
    })]


def index_references(references_dir: Path, repo_path: Path, config: dict) -> list[tuple[str, str, dict]]:
    """Index reference files from the references/ directory."""
    if not references_dir.exists():
        return []

    max_length = config.get("max_doc_length", 1500)
    results = []

    for ref_file in references_dir.iterdir():
        if ref_file.is_file() and ref_file.suffix in (".md", ".java", ".py", ".ts", ".txt", ".yaml"):
            try:
                content = ref_file.read_text(encoding="utf-8", errors="ignore")[:max_length]
                if len(content) < 50:
                    continue
                doc_id = f"ref_{ref_file.stem}"
                results.append((doc_id, content, {
                    "type": "reference",
                    "source": ref_file.name,
                }))
            except OSError:
                pass

    return results


def main():
    parser = argparse.ArgumentParser(description="Index codebase into ChromaDB for RAG")
    parser.add_argument("--repo-path", type=str, help="Path to the source repository")
    parser.add_argument("--rules-dir", type=str, default="project_rules",
                        help="Path to project_rules directory (default: ./project_rules)")
    parser.add_argument("--chromadb-host", type=str, default="localhost",
                        help="ChromaDB host (default: localhost)")
    parser.add_argument("--chromadb-port", type=int, default=8000,
                        help="ChromaDB port (default: 8000)")
    parser.add_argument("--collection", type=str, help="Collection name (overrides config)")
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    config = load_indexing_config(rules_dir)

    project_name = config.get("project_name", "project")
    collection_name = args.collection or f"{project_name}_codebase"

    if args.repo_path:
        repo_path = Path(args.repo_path)
    else:
        # Try to infer from scan_dirs
        print("Error: --repo-path is required (path to the source code repository)")
        sys.exit(1)

    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)

    print(f"Project: {project_name}")
    print(f"Repository: {repo_path}")
    print(f"Rules dir: {rules_dir}")
    print(f"Collection: {collection_name}")
    print()

    # Connect to ChromaDB
    print("Connecting to ChromaDB...")
    client = chromadb.HttpClient(host=args.chromadb_host, port=args.chromadb_port)
    col = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Collection has {col.count()} docs before indexing")

    all_ids = []
    all_docs = []
    all_metas = []

    # Scan configured directories
    scan_dirs = config.get("scan_dirs", [])
    file_matchers = config.get("file_matchers", {})
    exclude_patterns = config.get("exclude_patterns", ["target", ".git"])

    for scan_config in scan_dirs:
        scan_path = repo_path / scan_config["path"]
        if not scan_path.exists():
            print(f"  Skipping (not found): {scan_path}")
            continue

        print(f"  Scanning: {scan_path}")
        for root, dirs, files in os.walk(scan_path):
            # Apply exclusions
            if any(excl in root for excl in exclude_patterns):
                dirs.clear()
                continue

            for fname in files:
                file_type = get_file_type(fname, file_matchers)
                if file_type:
                    fpath = Path(root) / fname
                    results = get_file_summary(fpath, file_type, repo_path, config)
                    for doc_id, text, meta in results:
                        all_ids.append(doc_id)
                        all_docs.append(text)
                        all_metas.append(meta)

    # Index reference files
    references_dir = rules_dir / "references"
    ref_results = index_references(references_dir, repo_path, config)
    for doc_id, text, meta in ref_results:
        all_ids.append(doc_id)
        all_docs.append(text)
        all_metas.append(meta)
    if ref_results:
        print(f"  Added {len(ref_results)} reference documents")

    print(f"\nPrepared {len(all_ids)} documents to index")

    # Batch upsert
    start = time.time()
    indexed = 0
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch_end = min(i + BATCH_SIZE, len(all_ids))
        col.upsert(
            ids=all_ids[i:batch_end],
            documents=all_docs[i:batch_end],
            metadatas=all_metas[i:batch_end],
        )
        indexed += batch_end - i
        elapsed = time.time() - start
        print(f"  Indexed {indexed}/{len(all_ids)} ({elapsed:.1f}s)")

    total_time = time.time() - start
    print(f"\nDone! {col.count()} total docs in collection ({total_time:.1f}s)")


if __name__ == "__main__":
    main()
