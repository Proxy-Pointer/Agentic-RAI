"""
Document Seeder — embeds all 10 dummy documents into ChromaDB at startup.

Steps:
  1. Load JSON documents from data/documents/
  2. Compute SHA-256 hash and register with integrity_checker
  3. Embed content in batches (EMBEDDING_BATCH_SIZE, EMBEDDING_BATCH_DELAY)
  4. Upsert into ChromaDB collection with full metadata
"""
import json
import time
import logging
from pathlib import Path
from google.genai.types import EmbedContentConfig
import chromadb

from ..core.config import (
    gemini_client, EMBEDDING_MODEL, EMBEDDING_DIMS,
    EMBEDDING_BATCH_SIZE, EMBEDDING_BATCH_DELAY, CHROMA_COLLECTION,
)
from ..core.integrity_checker import integrity_checker, compute_hash

log = logging.getLogger("novacorp.seed")

DOCUMENTS_DIR = Path(__file__).parent / "documents"


def load_documents() -> list[dict]:
    docs = []
    for path in sorted(DOCUMENTS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        docs.append(doc)
        log.info(f"  Loaded: {doc['doc_id']} (acl={doc['acl']}, acl_level={doc['acl_level']})")
    return docs


def seed(collection: chromadb.Collection) -> int:
    """
    Seed ChromaDB with all policy documents.
    Returns number of documents seeded.
    Skips if collection already has documents.
    """
    if collection.count() > 0:
        log.info(f"Collection '{CHROMA_COLLECTION}' already seeded ({collection.count()} docs). Skipping.")
        return collection.count()

    log.info(f"Seeding ChromaDB collection '{CHROMA_COLLECTION}'...")
    docs = load_documents()

    # Register hashes for integrity checking
    for doc in docs:
        integrity_checker.register(doc["doc_id"], doc["content"])

    # Embed in batches
    all_ids, all_embeddings, all_texts, all_metas = [], [], [], []

    for i in range(0, len(docs), EMBEDDING_BATCH_SIZE):
        batch = docs[i : i + EMBEDDING_BATCH_SIZE]
        texts = [d["content"] for d in batch]

        log.info(f"  Embedding batch {i//EMBEDDING_BATCH_SIZE + 1}: {[d['doc_id'] for d in batch]}")
        response = gemini_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
            config=EmbedContentConfig(
                task_type="retrieval_document",
                output_dimensionality=EMBEDDING_DIMS,
            ),
        )
        embeddings = [e.values for e in response.embeddings]

        for doc, emb, text in zip(batch, embeddings, texts):
            sha = compute_hash(text)
            all_ids.append(doc["doc_id"])
            all_embeddings.append(emb)
            all_texts.append(text)
            all_metas.append({
                "doc_id":    doc["doc_id"],
                "title":     doc["title"],
                "acl":       doc["acl"],
                "acl_level": doc["acl_level"],   # scalar int — ChromaDB $lte pre-filter
                "category":  doc["category"],
                "sha256":    sha,
                "tampered":  False,
            })

        if i + EMBEDDING_BATCH_SIZE < len(docs):
            log.info(f"  Rate-limit pause: {EMBEDDING_BATCH_DELAY}s")
            time.sleep(EMBEDDING_BATCH_DELAY)

    collection.add(
        ids=all_ids,
        embeddings=all_embeddings,
        documents=all_texts,
        metadatas=all_metas,
    )

    log.info(f"Seeding complete: {len(all_ids)} documents in '{CHROMA_COLLECTION}'.")
    return len(all_ids)
