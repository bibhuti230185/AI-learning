#!/usr/bin/env python3
"""Minimal indexer - indexes key SW360 patterns into ChromaDB in small batches.

This version avoids the embedding bottleneck by:
1. Indexing fewer, more valuable documents
2. Using batch size of 10 (ChromaDB embeds on add)
3. Only indexing controller/service/handler signatures, not full bodies
"""

import os
import re
import time
from pathlib import Path

import chromadb

REPO_PATH = Path(r"D:\workspace\sw360")
BATCH_SIZE = 10


def get_file_summary(java_file: Path, file_type: str) -> list[tuple[str, str, dict]]:
    """Extract a compact summary of key methods from a Java file."""
    try:
        content = java_file.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []

    entity = java_file.stem.replace("Controller", "").replace("Service", "")
    entity = entity.replace("Sw360", "").replace("SW360", "")
    entity = entity.replace("Handler", "").replace("DatabaseHandler", "")
    entity = entity.replace("Test", "").replace("SpecTest", "")

    rel_path = str(java_file.relative_to(REPO_PATH))

    # Index the whole file as a single document (truncated to 1500 chars)
    # This gives the LLM enough context without blowing up embedding time
    doc_id = f"{file_type}_{java_file.stem}"
    # Extract just the class-level overview: package, imports, class declaration, method signatures
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
            or stripped.startswith("private static final Logger")):
            summary_lines.append(line)

    summary = "\n".join(summary_lines)[:1500]
    if len(summary) < 50:
        return []

    return [(doc_id, summary, {
        "type": f"{file_type}_method",
        "entity": entity,
        "source": rel_path,
        "method": "class_summary",
    })]


def main():
    print("Connecting to ChromaDB...")
    client = chromadb.HttpClient(host="localhost", port=8000)
    col = client.get_or_create_collection(
        name="sw360_codebase",
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Collection has {col.count()} docs before indexing")

    all_ids = []
    all_docs = []
    all_metas = []

    # Scan key directories
    scan_dirs = [
        REPO_PATH / "rest" / "resource-server" / "src",
        REPO_PATH / "backend",
    ]

    file_matchers = {
        "controller": lambda f: f.endswith("Controller.java") and not f.endswith("Test.java"),
        "service": lambda f: f.endswith("Service.java") and not f.endswith("Test.java"),
        "handler": lambda f: f.endswith("Handler.java"),
        "test": lambda f: f.endswith("Test.java"),
    }

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for root, dirs, files in os.walk(scan_dir):
            if "target" in root or ".git" in root:
                dirs.clear()
                continue
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                for file_type, matcher in file_matchers.items():
                    if matcher(fname):
                        fpath = Path(root) / fname
                        results = get_file_summary(fpath, file_type)
                        for doc_id, text, meta in results:
                            all_ids.append(doc_id)
                            all_docs.append(text)
                            all_metas.append(meta)
                        break

    print(f"Prepared {len(all_ids)} documents to index")

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
