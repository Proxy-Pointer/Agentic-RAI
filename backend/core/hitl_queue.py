"""
HITL Queue — in-memory Human-in-the-Loop task store.
Resets on server restart (by design for demo).
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class HITLQueue:
    def __init__(self):
        self._tasks: dict[str, dict] = {}

    def enqueue(
        self,
        *,
        user: str,
        query: str,
        action_type: str,
        action_description: str,
        risk_label: str,
        context: Optional[dict] = None,
    ) -> dict:
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "decided_at": None,
            "user": user,
            "query": query,
            "action_type": action_type,
            "action_description": action_description,
            "risk_label": risk_label,
            "context": context or {},
            "decision": None,
            "decision_note": None,
        }
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[dict]:
        return self._tasks.get(task_id)

    def approve(self, task_id: str, note: str = "") -> Optional[dict]:
        task = self._tasks.get(task_id)
        if not task or task["status"] != "PENDING":
            return None
        task["status"] = "APPROVED"
        task["decision"] = "APPROVED"
        task["decision_note"] = note
        task["decided_at"] = datetime.now(timezone.utc).isoformat()
        return task

    def reject(self, task_id: str, note: str = "") -> Optional[dict]:
        task = self._tasks.get(task_id)
        if not task or task["status"] != "PENDING":
            return None
        task["status"] = "REJECTED"
        task["decision"] = "REJECTED"
        task["decision_note"] = note
        task["decided_at"] = datetime.now(timezone.utc).isoformat()
        return task

    def get_pending(self) -> list[dict]:
        return [t for t in self._tasks.values() if t["status"] == "PENDING"]

    def get_all(self) -> list[dict]:
        return list(self._tasks.values())

    def clear(self):
        self._tasks.clear()


# Module-level singleton
hitl_queue = HITLQueue()
