"""
Audit Logger — append-only in-memory audit log.
Every pipeline execution writes one structured entry.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


class AuditLogger:
    def __init__(self):
        self._log: list[dict] = []

    def append(
        self,
        *,
        user: str,
        query: str,
        autonomy_tier: str,
        safety_pre: str,
        safety_post: str,
        acl_level: int,
        chunks_retrieved: int,
        chunks_denied: int,
        integrity_ok: bool,
        action_taken: str,
        hitl_decision: Optional[str],
        outcome: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        request_id: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "request_id": request_id or str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user,
            "query": query,
            "autonomy_tier": autonomy_tier,
            "safety_pre": safety_pre,
            "safety_post": safety_post,
            "acl_level": acl_level,
            "chunks_retrieved": chunks_retrieved,
            "chunks_denied": chunks_denied,
            "integrity_ok": integrity_ok,
            "action_taken": action_taken,
            "hitl_decision": hitl_decision,
            "outcome": outcome,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            **(extra or {}),
        }
        self._log.append(entry)
        return entry

    def get_all(self) -> list[dict]:
        return list(self._log)

    def filter_by_user(self, user: str) -> list[dict]:
        return [e for e in self._log if e["user"].lower() == user.lower()]

    def get_summary(self) -> dict:
        total = len(self._log)
        return {
            "total_queries": total,
            "blocked_by_safety": sum(1 for e in self._log if e["safety_pre"] == "BLOCKED"),
            "acl_denials": sum(1 for e in self._log if e["chunks_denied"] > 0),
            "hitl_escalations": sum(1 for e in self._log if e["hitl_decision"] is not None),
            "hitl_approved": sum(1 for e in self._log if e["hitl_decision"] == "APPROVED"),
            "hitl_rejected": sum(1 for e in self._log if e["hitl_decision"] == "REJECTED"),
            "integrity_failures": sum(1 for e in self._log if not e["integrity_ok"]),
            "by_user": {
                u: sum(1 for e in self._log if e["user"] == u)
                for u in {"alice", "bob", "admin"}
            },
            "by_tier": {
                t: sum(1 for e in self._log if e["autonomy_tier"] == t)
                for t in {"AUTONOMOUS", "SUPERVISED", "REQUIRES_HITL"}
            },
        }

    def clear(self):
        self._log.clear()


# Module-level singleton
audit_logger = AuditLogger()
