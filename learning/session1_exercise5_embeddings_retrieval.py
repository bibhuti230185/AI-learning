"""Exercise 5: Embeddings, Vector Stores, and Retrieval Systems.

This exercise demonstrates how to:
1. Create embeddings using OpenAI-compatible embedding models
2. Build a vector store with ChromaDB
3. Use vector store-backed retrievers
4. Implement ParentDocumentRetriever for hierarchical retrieval
5. Build a RetrievalQA chain for question answering

INSTALLATION REQUIREMENTS:
    pip install chromadb langchain-chroma --user
"""

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import WebBaseLoader
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain.chains import RetrievalQA
from langchain_core.documents import Document

from session1_shared import (
    AVAILABLE_MODELS,
    BASE_URL,
    DEFAULT_MAX_TOKENS,
    build_chat_model,
    get_api_key_or_exit,
    get_available_chat_models,
    select_primary_secondary_models,
    setup_runtime,
)


# Available embedding models from the Siemens catalog
EMBEDDING_MODELS = [
    model_name
    for model_name, meta in AVAILABLE_MODELS.items()
    if "embedding" in meta["usage"]
]

DEFAULT_EMBEDDING_MODEL = "qwen3-embedding-8b"


def create_siemens_embeddings(api_key: str, model: str = DEFAULT_EMBEDDING_MODEL) -> OpenAIEmbeddings:
    """Create an embedding model client using the Siemens OpenAI-compatible endpoint."""
    return OpenAIEmbeddings(
        model=model,
        openai_api_key=api_key,
        openai_api_base=BASE_URL,
    )


def run() -> None:
    setup_runtime(__file__)

    api_key = get_api_key_or_exit()
    chat_models = get_available_chat_models()
    model_primary, _ = select_primary_secondary_models(chat_models)

    print("=" * 80)
    print("EXERCISE 5: Embeddings, Vector Stores, and Retrieval Systems")
    print("=" * 80)

    print("\nAvailable embedding models:")
    for model_name in EMBEDDING_MODELS:
        meta = AVAILABLE_MODELS[model_name]
        print(f"  - {model_name} | max_tokens={meta['max_tokens']} | license={meta['license']}")

    # =========================================================================
    # Part 1: Creating Embeddings
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 1: Creating Embeddings")
    print("-" * 80)

    embedding_model = create_siemens_embeddings(api_key, DEFAULT_EMBEDDING_MODEL)
    print(f"Using embedding model: {DEFAULT_EMBEDDING_MODEL}")

    # Create embeddings for sample texts
    sample_texts = [
        "LangChain is a framework for developing applications powered by LLMs.",
        "Vector stores enable semantic search over documents.",
        "Embeddings convert text into numerical representations.",
    ]

    print("\nGenerating embeddings for sample texts...")
    try:
        embeddings = embedding_model.embed_documents(sample_texts)
        print(f"Generated {len(embeddings)} embeddings")
        print(f"Embedding dimension: {len(embeddings[0])}")
        print(f"First 5 values of first embedding: {embeddings[0][:5]}")
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        print("Using fallback sample embeddings for demonstration...")
        embeddings = [[0.1] * 384 for _ in sample_texts]

    # =========================================================================
    # Part 2: Loading and Splitting Documents
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 2: Loading and Splitting Documents")
    print("-" * 80)

    try:
        web_url = "https://python.langchain.com/v0.2/docs/introduction/"
        print(f"Loading document from: {web_url}")
        loader = WebBaseLoader(web_url)
        documents = loader.load()
        print(f"Loaded {len(documents)} document(s)")
    except Exception as e:
        print(f"Error loading web content: {e}")
        print("Using sample documents instead...")
        documents = [
            Document(
                page_content="""LangChain is a framework for developing applications powered by large language models (LLMs).
                
LangChain simplifies every stage of the LLM application lifecycle:
- Development: Build your applications using LangChain's open-source building blocks and components.
- Productionization: Use LangSmith to inspect, monitor and evaluate your chains.
- Deployment: Turn any chain into an API with LangServe.

The main value props of LangChain are:
1. Components: composable tools and integrations for working with language models.
2. Off-the-shelf chains: built-in assemblages of components for accomplishing higher-level tasks.

LangChain Expression Language (LCEL) is the foundation of many of LangChain's components.""",
                metadata={"source": "sample", "title": "LangChain Introduction"},
            )
        ]

    # Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks")

    # =========================================================================
    # Part 3: Creating a Vector Store
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 3: Creating a Vector Store with ChromaDB")
    print("-" * 80)

    try:
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embedding_model,
            collection_name="langchain_docs",
        )
        print(f"Vector store created with {len(chunks)} documents")

        # Perform similarity search
        query = "What is LangChain?"
        print(f"\nSimilarity search for: '{query}'")
        similar_docs = vector_store.similarity_search(query, k=3)

        print(f"Found {len(similar_docs)} similar documents:")
        for i, doc in enumerate(similar_docs):
            print(f"\n  Result {i + 1}:")
            print(f"    Content: {doc.page_content[:150]}...")
            print(f"    Metadata: {doc.metadata}")

    except Exception as e:
        print(f"Error creating vector store: {e}")
        vector_store = None

    # =========================================================================
    # Part 4: Vector Store-Backed Retriever
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 4: Vector Store-Backed Retriever")
    print("-" * 80)

    if vector_store:
        # Convert vector store to retriever
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
        print("Created retriever from vector store")

        # Test retrieval
        test_queries = [
            "What is LangChain?",
            "How do retrievers work?",
            "What are the main components?",
        ]

        for query in test_queries:
            print(f"\nQuery: {query}")
            docs = retriever.invoke(query)
            print(f"Retrieved {len(docs)} documents")
            if docs:
                print(f"  Top result: {docs[0].page_content[:100]}...")

    # =========================================================================
    # Part 5: ParentDocumentRetriever (Hierarchical Retrieval)
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 5: ParentDocumentRetriever (Hierarchical Retrieval)")
    print("-" * 80)

    try:
        # Parent splitter: larger chunks for context
        parent_splitter = CharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=20,
            separator="\n",
        )

        # Child splitter: smaller chunks for precise retrieval
        child_splitter = CharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=20,
            separator="\n",
        )

        # Create a separate vector store for hierarchical retrieval
        hierarchical_vectorstore = Chroma(
            collection_name="hierarchical_docs",
            embedding_function=embedding_model,
        )

        # In-memory store for parent documents
        parent_store = InMemoryStore()

        # Create ParentDocumentRetriever
        parent_retriever = ParentDocumentRetriever(
            vectorstore=hierarchical_vectorstore,
            docstore=parent_store,
            child_splitter=child_splitter,
            parent_splitter=parent_splitter,
        )

        # Add documents to the retriever
        parent_retriever.add_documents(documents)
        print(f"Added documents to ParentDocumentRetriever")
        print(f"Parent documents stored: {len(list(parent_store.yield_keys()))}")

        # Compare child vs parent retrieval
        query = "LangChain"

        # Child documents (small chunks from vector store)
        child_docs = hierarchical_vectorstore.similarity_search(query, k=1)
        if child_docs:
            print(f"\nChild document (small chunk):")
            print(f"  Length: {len(child_docs[0].page_content)} chars")
            print(f"  Content: {child_docs[0].page_content[:200]}...")

        # Parent documents (larger chunks with more context)
        parent_docs = parent_retriever.invoke(query)
        if parent_docs:
            print(f"\nParent document (larger chunk):")
            print(f"  Length: {len(parent_docs[0].page_content)} chars")
            print(f"  Content: {parent_docs[0].page_content[:200]}...")

    except Exception as e:
        print(f"Error with ParentDocumentRetriever: {e}")

    # =========================================================================
    # Part 6: RetrievalQA Chain
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 6: RetrievalQA Chain (Question Answering)")
    print("-" * 80)

    if vector_store:
        try:
            # Create LLM for QA
            llm = build_chat_model(
                model_name=model_primary,
                api_key=api_key,
                temperature=0.1,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            print(f"Using LLM: {model_primary}")

            # Create RetrievalQA chain
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",  # Concatenate all docs and pass to LLM
                retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
                return_source_documents=True,
            )
            print("Created RetrievalQA chain")

            # Test QA with multiple questions
            qa_queries = [
                "What is LangChain used for?",
                "What are the main components of LangChain?",
                "How does LangChain help with LLM development?",
            ]

            for query in qa_queries:
                print(f"\n{'=' * 60}")
                print(f"Question: {query}")
                print("-" * 60)

                result = qa_chain.invoke({"query": query})

                print(f"Answer: {result['result']}")

                if result.get("source_documents"):
                    print(f"\nSources used: {len(result['source_documents'])} documents")

        except Exception as e:
            print(f"Error with RetrievalQA: {e}")

    # =========================================================================
    # Part 7: Search Function Example
    # =========================================================================
    print("\n" + "-" * 80)
    print("Part 7: Custom Search Function")
    print("-" * 80)

    def search_documents(retriever, query: str, top_k: int = 3) -> list:
        """Search for documents relevant to a query."""
        docs = retriever.invoke(query)
        return docs[:top_k]

    if vector_store:
        simple_retriever = vector_store.as_retriever(search_kwargs={"k": 5})

        search_queries = [
            "What is LangChain?",
            "How do retrievers work?",
            "Why is document splitting important?",
        ]

        for query in search_queries:
            print(f"\nQuery: {query}")
            results = search_documents(simple_retriever, query, top_k=3)

            print(f"Found {len(results)} relevant documents:")
            for i, doc in enumerate(results):
                print(f"\n  Result {i + 1}: {doc.page_content[:150]}...")
                print(f"  Source: {doc.metadata.get('source', 'Unknown')}")

    print("\n" + "=" * 80)
    print("Exercise 5 observations:")
    print("- Embeddings convert text to vectors for semantic similarity")
    print("- ChromaDB provides efficient vector storage and retrieval")
    print("- ParentDocumentRetriever balances precision with context")
    print("- RetrievalQA combines retrieval with LLM-based answering")
    print("- The 'stuff' chain type works well for small document sets")
    print("=" * 80)


if __name__ == "__main__":
    run()
