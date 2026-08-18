"""
NovaCorp HR Policy Agent — FastAPI Backend
Serves the frontend as static files and exposes all REST + SSE endpoints.
"""
from __future__ import annotations
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import chromadb
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .core.config import CHROMA_COLLECTION, CHROMA_DISTANCE, log
from .core.audit_logger import audit_logger
from .core.hitl_queue import hitl_queue
from .core.integrity_checker import integrity_checker
from .core.trace_collector import tracer
from .agents import orchestrator
from .data.seed_documents import seed

# ── ChromaDB (in-memory, created once at startup) ────────────────────────────
_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None

FRONTEND_DIR = Path(__file__).parents[1] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _chroma_client, _collection
    log.info("Starting NovaCorp HR Policy Agent...")
    _chroma_client = chromadb.Client()
    _collection = _chroma_client.create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": CHROMA_DISTANCE},
    )
    log.info("Seeding ChromaDB with policy documents...")
    count = seed(_collection)
    log.info(f"Ready — {count} documents in vector store.")
    yield
    log.info("Shutting down.")


app = FastAPI(title="NovaCorp Responsible AI Demo", lifespan=lifespan)

# ── Serve frontend ────────────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ── Request/Response schemas ──────────────────────────────────────────────────
class QueryRequest(BaseModel):
    user: str
    query: str
    request_id: Optional[str] = None


class HITLDecisionRequest(BaseModel):
    note: str = ""


class TamperRequest(BaseModel):
    doc_id: str


# ── SSE event stream ──────────────────────────────────────────────────────────
@app.get("/api/stream")
async def event_stream(request: Request):
    """
    Persistent SSE connection. Frontend connects once on page load.
    All trace and response events for all requests stream here.
    """
    queue = tracer.subscribe()

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield {"data": json.dumps(event)}
                except asyncio.TimeoutError:
                    # heartbeat to keep connection alive
                    yield {"data": json.dumps({"type": "heartbeat"})}
        finally:
            tracer.unsubscribe(queue)

    return EventSourceResponse(generator())


# ── Query endpoint ────────────────────────────────────────────────────────────
@app.post("/api/query")
async def query(req: QueryRequest, background_tasks: BackgroundTasks):
    request_id = req.request_id or str(uuid.uuid4())

    async def _run():
        await orchestrator.run(
            query=req.query,
            user=req.user,
            collection=_collection,
            request_id=request_id,
        )

    background_tasks.add_task(_run)
    return {"request_id": request_id, "status": "processing"}


# ── HITL endpoints ────────────────────────────────────────────────────────────
@app.get("/api/hitl/pending")
async def get_pending_hitl():
    return hitl_queue.get_pending()


@app.get("/api/hitl/all")
async def get_all_hitl():
    return hitl_queue.get_all()


@app.post("/api/hitl/{task_id}/approve")
async def approve_hitl(task_id: str, req: HITLDecisionRequest, background_tasks: BackgroundTasks):
    task = hitl_queue.approve(task_id, note=req.note)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not pending")

    request_id = task["context"].get("request_id", str(uuid.uuid4()))

    async def _execute():
        from .agents.action_agent import execute_approved_action
        result = await execute_approved_action(task, request_id)
        await tracer.emit_response(request_id, {
            "type": "hitl_result",
            "request_id": request_id,
            "task_id": task_id,
            "decision": "APPROVED",
            "message": f"✅ **Action Approved & Executed**\n\n{result['message']}",
            "user": task["user"],
        })
        audit_logger.append(
            user=task["user"], query=task["query"], autonomy_tier="REQUIRES_HITL",
            safety_pre="PASS", safety_post="N/A",
            acl_level=-1, chunks_retrieved=0, chunks_denied=0,
            integrity_ok=True, action_taken=task["action_type"],
            hitl_decision="APPROVED", outcome="SUCCESS",
            request_id=request_id,
        )

    background_tasks.add_task(_execute)
    return {"status": "approved", "task_id": task_id}


@app.post("/api/hitl/{task_id}/reject")
async def reject_hitl(task_id: str, req: HITLDecisionRequest, background_tasks: BackgroundTasks):
    task = hitl_queue.reject(task_id, note=req.note)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not pending")

    request_id = task["context"].get("request_id", str(uuid.uuid4()))

    async def _notify():
        await tracer.emit_response(request_id, {
            "type": "hitl_result",
            "request_id": request_id,
            "task_id": task_id,
            "decision": "REJECTED",
            "message": f"❌ **Action Rejected**\n\nThe requested action was rejected by the human reviewer.\n\n**Note**: {req.note or 'No reason provided.'}",
            "user": task["user"],
        })
        audit_logger.append(
            user=task["user"], query=task["query"], autonomy_tier="REQUIRES_HITL",
            safety_pre="PASS", safety_post="N/A",
            acl_level=-1, chunks_retrieved=0, chunks_denied=0,
            integrity_ok=True, action_taken=task["action_type"],
            hitl_decision="REJECTED", outcome="REJECTED",
            request_id=request_id,
        )

    background_tasks.add_task(_notify)
    return {"status": "rejected", "task_id": task_id}


# ── Audit endpoints ───────────────────────────────────────────────────────────
@app.get("/api/audit")
async def get_audit(user: Optional[str] = None):
    if user:
        return audit_logger.filter_by_user(user)
    return audit_logger.get_all()


@app.get("/api/audit/summary")
async def get_audit_summary():
    return audit_logger.get_summary()


# ── Admin / demo control endpoints ───────────────────────────────────────────
@app.post("/api/admin/tamper/{doc_id}")
async def toggle_tamper(doc_id: str):
    """Toggle tamper state for a document (demo UI control)."""
    new_state = integrity_checker.toggle_tamper(doc_id)

    # Actually modify the document text in ChromaDB to trigger a real hash mismatch
    if _collection is not None:
        results = _collection.get(
            ids=[doc_id],
            include=["embeddings", "documents", "metadatas"]
        )
        if results and results["documents"]:
            original_text = results["documents"][0]
            original_embedding = results["embeddings"][0]  # preserve original embedding
            metadata = results["metadatas"][0]

            suffix = " [TAMPERED_UNAUTHORIZED_ALTERATION]"
            if new_state:
                new_text = original_text + suffix
            else:
                # Strip suffix to restore
                new_text = original_text
                if new_text.endswith(suffix):
                    new_text = new_text[:-len(suffix)]

            _collection.update(
                ids=[doc_id],
                embeddings=[original_embedding],   # keep original embedding — avoids re-embedding
                documents=[new_text],
                metadatas=[{**metadata, "tampered": new_state}]
            )

    return {"doc_id": doc_id, "tampered": new_state}




@app.get("/api/admin/integrity")
async def get_integrity_states():
    return integrity_checker.get_all_states()


@app.post("/api/admin/reset")
async def reset_demo():
    """Reset audit log and HITL queue (demo reset)."""
    audit_logger.clear()
    hitl_queue.clear()
    return {"status": "reset", "message": "Audit log and HITL queue cleared."}


@app.get("/api/documents")
async def list_documents():
    """Return all documents in the vector store with their metadata."""
    results = _collection.get(include=["metadatas"])
    docs = []
    for doc_id, meta in zip(results["ids"], results["metadatas"]):
        state = integrity_checker.get_all_states().get(doc_id, {})
        docs.append({**meta, "tampered": state.get("tampered", False)})
    return docs


@app.get("/api/users")
async def list_users():
    from .core.config import USER_ACL, ACL_LEVELS
    reverse = {v: k for k, v in ACL_LEVELS.items()}
    return [
        {"user": u, "acl_level": lvl, "acl_label": reverse.get(lvl, "ALL")}
        for u, lvl in USER_ACL.items()
    ]


@app.get("/")
async def root():
    return JSONResponse({"message": "NovaCorp HR Agent API. Open /app for the UI."})
