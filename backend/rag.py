"""
RAG Engine using LangChain + FAISS + HuggingFace Embeddings (no OpenAI key needed).
Loads clinic knowledge documents, builds a vector store, and provides query retrieval.
"""
import os
import logging
from typing import List

from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document

from config import DATA_DIR, FAISS_INDEX_PATH

logger = logging.getLogger(__name__)

# Using a lightweight, fast sentence-transformer model (no API key needed)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_embeddings = None
_vector_store = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Lazy-load the HuggingFace embedding model (downloads once, cached locally)."""
    global _embeddings
    if _embeddings is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Embedding model loaded successfully.")
    return _embeddings


def load_documents_from_directory(directory: str) -> List[Document]:
    """Load all .txt files from a directory."""
    docs = []
    if not os.path.exists(directory):
        logger.warning(f"Data directory not found: {directory}")
        return docs
    for fname in os.listdir(directory):
        if fname.endswith(".txt"):
            fpath = os.path.join(directory, fname)
            try:
                loader = TextLoader(fpath, encoding="utf-8")
                docs.extend(loader.load())
                logger.info(f"Loaded: {fname}")
            except Exception as e:
                logger.error(f"Failed to load {fname}: {e}")
    return docs


def build_vector_store(docs: List[Document]) -> FAISS:
    """Split documents and build a FAISS vector store."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=60,
        separators=["\n\n", "\n", ".", " "],
    )
    chunks = splitter.split_documents(docs)
    logger.info(f"Created {len(chunks)} chunks from {len(docs)} documents.")

    embeddings = get_embeddings()
    store = FAISS.from_documents(chunks, embeddings)
    store.save_local(FAISS_INDEX_PATH)
    logger.info(f"FAISS index saved to: {FAISS_INDEX_PATH}")
    return store


def load_or_build_vector_store() -> FAISS:
    """Load existing FAISS index from disk, or build one from clinic documents."""
    global _vector_store
    embeddings = get_embeddings()

    if os.path.exists(FAISS_INDEX_PATH):
        try:
            logger.info("Loading existing FAISS index from disk...")
            _vector_store = FAISS.load_local(
                FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True
            )
            logger.info("FAISS index loaded successfully.")
            return _vector_store
        except Exception as e:
            logger.warning(f"Could not load existing index ({e}), rebuilding...")

    docs = load_documents_from_directory(DATA_DIR)
    if not docs:
        # Create a minimal placeholder if no docs found
        logger.warning("No documents found. Creating minimal knowledge base.")
        docs = [Document(page_content="MedCare Clinic: A multi-specialty outpatient clinic.")]

    _vector_store = build_vector_store(docs)
    return _vector_store


def query_rag(question: str, k: int = 5) -> str:
    """Query the RAG system and return concatenated relevant context."""
    global _vector_store
    if _vector_store is None:
        _vector_store = load_or_build_vector_store()

    try:
        results = _vector_store.similarity_search(question, k=k)
        context = "\n\n---\n\n".join(doc.page_content for doc in results)
        return context
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        return "Unable to retrieve clinic information at this time."


def get_full_clinic_context() -> str:
    """Return a comprehensive context for the VAPI system prompt."""
    key_queries = [
        "clinic hours and location",
        "appointment booking process",
        "doctors and specialties",
        "services and facilities",
        "insurance and payment",
        "emergency protocol",
        "frequently asked questions",
    ]
    sections = set()
    for query in key_queries:
        result = query_rag(query, k=3)
        sections.add(result)
    return "\n\n---\n\n".join(sections)


def add_documents_to_store(texts: List[str], filenames: List[str] = None) -> int:
    """Add new text documents to the existing vector store and re-save."""
    global _vector_store
    if _vector_store is None:
        _vector_store = load_or_build_vector_store()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=60)
    new_docs = []
    for i, text in enumerate(texts):
        meta = {"source": filenames[i] if filenames else f"upload_{i}"}
        new_docs.append(Document(page_content=text, metadata=meta))

    chunks = splitter.split_documents(new_docs)
    embeddings = get_embeddings()
    new_store = FAISS.from_documents(chunks, embeddings)
    _vector_store.merge_from(new_store)
    _vector_store.save_local(FAISS_INDEX_PATH)
    logger.info(f"Added {len(chunks)} new chunks. Index updated.")
    return len(chunks)
