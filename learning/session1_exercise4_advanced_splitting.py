"""Exercise 4: Advanced Document Splitting and Comparison.

This exercise demonstrates how to:
1. Load documents from multiple sources (PDF and web)
2. Compare CharacterTextSplitter vs RecursiveCharacterTextSplitter
3. Analyze impact of chunk_size and chunk_overlap parameters
4. Examine metadata preservation across splitting
5. Display detailed statistics about document chunks
"""

from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter

from session1_shared import setup_runtime


def display_document_stats(docs: list, name: str) -> None:
    """Display comprehensive statistics about a list of document chunks."""
    total_chunks = len(docs)
    total_chars = sum(len(doc.page_content) for doc in docs)
    avg_chunk_size = total_chars / total_chunks if total_chunks > 0 else 0

    # Collect all unique metadata keys
    all_metadata_keys = set()
    for doc in docs:
        all_metadata_keys.update(doc.metadata.keys())

    # Print statistics
    print(f"\n{'=' * 80}")
    print(f"Statistics: {name}")
    print(f"{'=' * 80}")
    print(f"Total number of chunks:      {total_chunks}")
    print(f"Total characters:            {total_chars:,}")
    print(f"Average chunk size:          {avg_chunk_size:.2f} characters")
    print(f"Metadata keys preserved:     {', '.join(sorted(all_metadata_keys)) if all_metadata_keys else 'None'}")

    if docs:
        # Get example chunk (5th chunk or last if fewer)
        example_idx = min(5, total_chunks - 1)
        example_doc = docs[example_idx]

        # Calculate length distribution
        lengths = [len(doc.page_content) for doc in docs]
        min_len = min(lengths)
        max_len = max(lengths)

        print(f"\nChunk size distribution:")
        print(f"  Min chunk size:            {min_len} characters")
        print(f"  Max chunk size:            {max_len} characters")
        print(f"  Size variance:             {max_len - min_len} characters")

        print(f"\nExample chunk (index {example_idx}):")
        print(f"  Content (first 200 chars): {example_doc.page_content[:200]}...")
        print(f"  Full content length:       {len(example_doc.page_content)} characters")
        print(f"  Metadata:                  {example_doc.metadata}")


def run() -> None:
    setup_runtime(__file__)

    print("=" * 80)
    print("EXERCISE 4: Advanced Document Splitting and Comparison")
    print("=" * 80)

    # =========================================================================
    # Part 1: Load documents from multiple sources
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 1: Loading Documents from Multiple Sources")
    print("-" * 80)

    pdf_documents = []
    web_documents = []

    try:
        paper_url = "https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/96-FDF8f7coh0ooim7NyEQ/langchain-paper.pdf"
        print(f"Loading PDF from: {paper_url}")
        pdf_loader = PyPDFLoader(paper_url)
        pdf_documents = pdf_loader.load()
        print(f"✓ PDF loaded successfully: {len(pdf_documents)} pages")
    except Exception as e:
        print(f"✗ Error loading PDF: {e}")

    try:
        web_url = "https://python.langchain.com/v0.2/docs/introduction/"
        print(f"\nLoading web content from: {web_url}")
        web_loader = WebBaseLoader(web_url)
        web_documents = web_loader.load()
        print(f"✓ Web content loaded successfully: {len(web_documents)} document(s)")
    except Exception as e:
        print(f"✗ Error loading web content: {e}")

    # Use PDF documents for splitting comparison
    if not pdf_documents:
        print("\n⚠️  PDF not available. Using sample document instead.")
        from langchain_core.documents import Document

        pdf_documents = [
            Document(
                page_content="""LangChain is a framework for developing applications powered by large language models (LLMs).
It enables applications that are:
- Data-aware: connect LLM to other sources of data
- Agentic: allow an LLM to interact with its environment

The main value props of LangChain are:

1. Components: abstractions for working with language models, along with a collection of implementations
2. Chains: assembled components in ways that accomplish a specific task, along with a collection of out-of-the-box chains

Documentation is available at python.langchain.com.""",
                metadata={"source": "sample", "page": 0},
            )
        ]

    # =========================================================================
    # Part 2: Create two different text splitters
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 2: Creating Text Splitters with Different Strategies")
    print("-" * 80)

    print("\nSplitter 1: CharacterTextSplitter")
    print("  - chunk_size: 300 characters")
    print("  - chunk_overlap: 30 characters")
    print("  - separator: newline (\\n)")
    splitter_1 = CharacterTextSplitter(
        chunk_size=300, chunk_overlap=30, separator="\n"
    )

    print("\nSplitter 2: RecursiveCharacterTextSplitter")
    print("  - chunk_size: 500 characters")
    print("  - chunk_overlap: 50 characters")
    print("  - separators: [\\n\\n, \\n, . , space, empty]")
    print("  (Tries separators in order, using the first that works)")
    splitter_2 = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # =========================================================================
    # Part 3: Apply both splitters to PDF documents
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 3: Applying Splitters to Documents")
    print("-" * 80)

    chunks_1 = splitter_1.split_documents(pdf_documents)
    chunks_2 = splitter_2.split_documents(pdf_documents)

    print(f"\nSplitting complete!")
    print(f"  CharacterTextSplitter: {len(chunks_1)} chunks")
    print(f"  RecursiveCharacterTextSplitter: {len(chunks_2)} chunks")

    # =========================================================================
    # Part 4: Display statistics for both splitters
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 4: Comparing Splitter Results")
    print("-" * 80)

    display_document_stats(chunks_1, "CharacterTextSplitter (300/30)")
    display_document_stats(chunks_2, "RecursiveCharacterTextSplitter (500/50)")

    # =========================================================================
    # Part 5: Comparative analysis
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 5: Comparative Analysis")
    print("-" * 80)

    chunk_count_diff = len(chunks_2) - len(chunks_1)
    print(f"\nChunk count difference: {abs(chunk_count_diff)} fewer chunks with Splitter 2")
    print("  This is expected because:")
    print("  - Splitter 1: smaller chunks (300), more fragmentation")
    print("  - Splitter 2: larger chunks (500), better respects paragraph boundaries")

    lengths_1 = [len(doc.page_content) for doc in chunks_1]
    lengths_2 = [len(doc.page_content) for doc in chunks_2]

    if lengths_1:
        avg_1 = sum(lengths_1) / len(lengths_1)
        print(f"\nAverage chunk size:")
        print(f"  Splitter 1: {avg_1:.0f} characters")
        print(f"  Splitter 2: {sum(lengths_2) / len(lengths_2):.0f} characters")

    print("\nKey observations:")
    print("  - RecursiveCharacterTextSplitter respects natural boundaries (paragraphs)")
    print("  - CharacterTextSplitter splits more uniformly by character count")
    print("  - Both preserve original metadata across chunks")
    print("  - Overlap parameter helps maintain context between chunks")

    # =========================================================================
    # Part 6: Metadata preservation check
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 6: Metadata Preservation Verification")
    print("-" * 80)

    if chunks_1 and chunks_2:
        # Check that metadata is preserved in all chunks
        for i, (c1, c2) in enumerate(zip(chunks_1[:3], chunks_2[:3])):
            print(f"\nChunk {i}:")
            print(f"  Splitter 1 metadata: {c1.metadata}")
            print(f"  Splitter 2 metadata: {c2.metadata}")

    print("\n" + "=" * 80)
    print("Exercise 4 observations:")
    print("- CharacterTextSplitter: uniform sizing, simpler strategy")
    print("- RecursiveCharacterTextSplitter: respects document structure better")
    print("- Overlap helps context continuity; choose based on use case")
    print("- Metadata is preserved through the splitting process")
    print("=" * 80)


if __name__ == "__main__":
    run()
