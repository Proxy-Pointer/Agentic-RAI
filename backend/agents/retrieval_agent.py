"""
Retrieval Agent — full RAG pipeline.

Pipeline:
  1. Resolve user ACL level
  2. Embed query (gemini-embedding-001, 1536 dims)
  3. ChromaDB pre-filtered cosine search (acl_level $lte user_level)
  4. Integrity check each retrieved doc
  5. Safety Guard post-filter (indirect injection scan)
  6. Return clean chunks + metadata
"""
import time
from google.genai.types import EmbedContentConfig

from ..core.config import gemini_client, EMBEDDING_MODEL, EMBEDDING_DIMS, RAG_TOP_K
from ..core.acl_manager import get_user_acl_level, chroma_where_clause, is_pii
from ..core.integrity_checker import integrity_checker
from ..core.trace_collector import tracer
from ..core.safety_guard import post_filter


async def retrieve(
    query: str,
    user: str,
    collection,            # ChromaDB collection
    request_id: str,
) -> dict:
    """
    Run the full pre-filtered RAG retrieval for a query and user.
    Returns a dict with chunks, metadata, and safety/integrity results.
    """
    user_acl_level = get_user_acl_level(user)
    where_clause   = chroma_where_clause(user)

    # ── Step 3: ACL resolution logged ────────────────────────────────────────
    await tracer.emit(
        request_id, "acl_manager", "acl_resolved",
        f"User '{user}' → acl_level={user_acl_level} — pre-filter: acl_level ≤ {user_acl_level}",
        status="ok",
    )

    # ── Step 4: Embed query ───────────────────────────────────────────────────
    await tracer.emit(
        request_id, "retrieval", "embedding_query",
        f"Calling {EMBEDDING_MODEL} (dims={EMBEDDING_DIMS}, task=retrieval_query)",
        status="ok",
    )
    embed_response = gemini_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[query],
        config=EmbedContentConfig(
            task_type="retrieval_query",
            output_dimensionality=EMBEDDING_DIMS,
        ),
    )
    query_embedding = embed_response.embeddings[0].values

    # ── Step 5: ChromaDB pre-filtered query ──────────────────────────────────
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=RAG_TOP_K,
        where=where_clause,
        include=["documents", "metadatas", "distances"],
    )

    docs      = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    await tracer.emit(
        request_id, "retrieval", "chroma_query",
        f"Retrieved {len(docs)} chunk(s) (ACL pre-filter: acl_level ≤ {user_acl_level})",
        status="ok" if docs else "warn",
    )

    # ── Step 6: Integrity check ───────────────────────────────────────────────
    chunks_ok        = []
    quarantined_integrity = []
    integrity_ok     = True
    for doc_text, meta, dist in zip(docs, metadatas, distances):
        doc_id = meta.get("doc_id", "unknown")
        ok, msg = integrity_checker.verify(doc_id, meta.get("content_hash_src", doc_text))
        chunk = {
            "doc_id": doc_id,
            "content": doc_text,
            "meta": meta,
            "distance": dist,
            "integrity_ok": ok,
            "integrity_msg": msg,
            "is_pii": is_pii(meta.get("acl_level", 0)),
        }
        if not ok:
            integrity_ok = False
            chunk["reason"] = f"SHA-256 mismatch — document may have been tampered with"
            quarantined_integrity.append(chunk)
            await tracer.emit(
                request_id, "integrity", "hash_fail",
                f"INTEGRITY FAILURE — quarantining '{doc_id}': {msg}",
                status="blocked",
            )
        else:
            chunks_ok.append(chunk)
            await tracer.emit(
                request_id, "integrity", "hash_ok",
                f"{doc_id}: {msg}",
                status="ok",
            )


    # ── Step 7: Safety post-filter (indirect injection scan) ─────────────────
    post_result = post_filter(chunks_ok)
    if not post_result["passed"]:
        for q in post_result["quarantined"]:
            await tracer.emit(
                request_id, "safety_guard", "indirect_injection",
                f"INDIRECT INJECTION in '{q['doc_id']}': {q['reason']}",
                status="blocked",
            )
    else:
        await tracer.emit(
            request_id, "safety_guard", "post_filter_pass",
            f"Post-filter: {len(post_result['clean_chunks'])} chunk(s) clean",
            status="ok",
        )

    return {
        "clean_chunks": post_result["clean_chunks"],
        "quarantined": quarantined_integrity + post_result["quarantined"],
        "integrity_ok": integrity_ok,
        "user_acl_level": user_acl_level,
        "total_retrieved": len(docs),
        "indirect_injection_detected": not post_result["passed"],
    }
