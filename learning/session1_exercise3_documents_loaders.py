"""Exercise 3: Documents, Loaders, and Text Splitting.

This exercise demonstrates how to:
1. Create Document objects with metadata
2. Load PDF files using PyPDFLoader
3. Load web content using WebBaseLoader
4. Split large documents into smaller chunks using CharacterTextSplitter
5. Inspect and work with document chunks
"""

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain.text_splitter import CharacterTextSplitter

from session1_shared import setup_runtime


def run() -> None:
    setup_runtime(__file__)

    print("=" * 80)
    print("EXERCISE 3: Documents, Loaders, and Text Splitting")
    print("=" * 80)

    # =========================================================================
    # Part 1: Creating Document objects with metadata
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 1: Creating Document Objects with Metadata")
    print("-" * 80)

    doc1 = Document(
        page_content="""Python is an interpreted high-level general-purpose programming language.
Python's design philosophy emphasizes code readability with its notable use of significant indentation.""",
        metadata={
            "document_id": 234234,
            "source": "About Python",
            "created_time": 1680013019,  # Unix timestamp: March 28, 2023
        },
    )

    doc2 = Document(
        page_content="""Python is an interpreted high-level general-purpose programming language. 
Python's design philosophy emphasizes code readability with its notable use of significant indentation.""",
    )

    print(f"Document 1 (with metadata):")
    print(f"  Content: {doc1.page_content[:100]}...")
    print(f"  Metadata: {doc1.metadata}")

    print(f"\nDocument 2 (minimal metadata):")
    print(f"  Content: {doc2.page_content[:100]}...")
    print(f"  Metadata: {doc2.metadata}")

    # =========================================================================
    # Part 2: Loading PDF files
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 2: Loading PDF Files with PyPDFLoader")
    print("-" * 80)

    try:
        pdf_url = "https://cf-courses-data.s3.us.cloud-object-storage.appdomain.cloud/96-FDF8f7coh0ooim7NyEQ/langchain-paper.pdf"
        pdf_loader = PyPDFLoader(pdf_url)
        pdf_documents = pdf_loader.load()

        print(f"PDF loaded successfully!")
        print(f"  Total pages: {len(pdf_documents)}")

        if len(pdf_documents) >= 2:
            print(f"\nPage 2 metadata:")
            print(f"  {pdf_documents[1].metadata}")
            print(f"\nFirst 500 characters of Page 2:")
            print(f"  {pdf_documents[1].page_content[:500]}...")

    except Exception as e:
        print(f"Error loading PDF: {e}")
        print("  (This may occur if the URL is unavailable or network access is restricted)")
        pdf_documents = []

    # =========================================================================
    # Part 3: Loading web content
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 3: Loading Web Content with WebBaseLoader")
    print("-" * 80)

    try:
        web_url = "https://python.langchain.com/v0.2/docs/introduction/"
        web_loader = WebBaseLoader(web_url)
        web_documents = web_loader.load()

        print(f"Web page loaded successfully!")
        print(f"  URL: {web_url}")
        print(f"  Total documents: {len(web_documents)}")

        if web_documents:
            print(f"\nWeb content metadata:")
            print(f"  {web_documents[0].metadata}")
            print(f"\nFirst 500 characters of web content:")
            print(f"  {web_documents[0].page_content[:500]}...")

    except Exception as e:
        print(f"Error loading web page: {e}")
        print("  (This may occur if the URL is unavailable or network access is restricted)")
        web_documents = []

    # =========================================================================
    # Part 4: Splitting text into chunks
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 4: Splitting Text into Chunks with CharacterTextSplitter")
    print("-" * 80)

    # Use PDF documents if available, otherwise create sample documents for splitting
    if pdf_documents:
        documents_to_split = pdf_documents[:3]  # Use first 3 pages
        source = "PDF"
    else:
        documents_to_split = [doc1, doc2]
        source = "Sample Documents"

    print(f"Splitting {source} into chunks...")

    text_splitter = CharacterTextSplitter(
        chunk_size=200,    # Each chunk will be ~200 characters
        chunk_overlap=20,  # Consecutive chunks overlap by 20 characters
        separator="\n",    # Split at newlines when possible
    )

    chunks = text_splitter.split_documents(documents_to_split)

    print(f"\nText Splitting Results:")
    print(f"  Original documents: {len(documents_to_split)}")
    print(f"  Chunks created: {len(chunks)}")
    print(f"  Average chunk size: {sum(len(c.page_content) for c in chunks) / len(chunks):.0f} characters")

    if chunks:
        print(f"\nChunk 0:")
        print(f"  Content: {chunks[0].page_content[:150]}...")
        print(f"  Length: {len(chunks[0].page_content)} characters")
        print(f"  Metadata: {chunks[0].metadata}")

        if len(chunks) > 5:
            print(f"\nChunk 5:")
            print(f"  Content: {chunks[5].page_content[:150]}...")
            print(f"  Length: {len(chunks[5].page_content)} characters")

    # =========================================================================
    # Part 5: Document inspection and statistics
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 5: Document Statistics and Inspection")
    print("-" * 80)

    if chunks:
        total_chars = sum(len(c.page_content) for c in chunks)
        print(f"Total characters across all chunks: {total_chars}")
        print(f"Min chunk size: {min(len(c.page_content) for c in chunks)} characters")
        print(f"Max chunk size: {max(len(c.page_content) for c in chunks)} characters")

        # Find chunks with specific content patterns
        chunks_with_python = [c for c in chunks if "Python" in c.page_content or "python" in c.page_content]
        print(f"\nChunks containing 'Python': {len(chunks_with_python)}")

    print("\n" + "=" * 80)
    print("Exercise 3 observations:")
    print("- Document objects preserve metadata alongside content")
    print("- PyPDFLoader and WebBaseLoader handle downloading and parsing")
    print("- CharacterTextSplitter with overlap maintains context between chunks")
    print("- Chunks are ideal for feeding into vector stores or RAG systems")
    print("=" * 80)


if __name__ == "__main__":
    run()
