"""
Action Agent — executes HITL-gated write actions.

Actions are simulated for the demo (no real database writes).
All executions are logged to the audit store.
"""
from ..core.hitl_queue import hitl_queue
from ..core.audit_logger import audit_logger
from ..core.trace_collector import tracer
from ..core.policy_engine import REQUIRES_HITL, SUPERVISED


# ── Known action types and their descriptions ────────────────────────────────
ACTION_REGISTRY = {
    "salary_update": {
        "description": "Update employee salary record",
        "risk_label": "HIGH — Compensation data modification",
    },
    "bulk_email": {
        "description": "Send bulk email to all employees",
        "risk_label": "HIGH — Mass communication action",
    },
    "record_update": {
        "description": "Modify employee personal/HR record",
        "risk_label": "HIGH — Employee data modification",
    },
    "access_grant": {
        "description": "Grant/revoke system access permissions",
        "risk_label": "CRITICAL — Access control modification",
    },
    "termination": {
        "description": "Initiate employee termination process",
        "risk_label": "CRITICAL — Employment termination",
    },
    "leave_request": {
        "description": "Submit employee leave request",
        "risk_label": "MEDIUM — HR workflow action",
    },
}

# ── Supervised action simulated outcomes ─────────────────────────────────────
SUPERVISED_RESULTS = {
    "leave_request":   "✅ Your leave request has been submitted and logged. You will receive a confirmation from HR.",
    "expense_request": "✅ Your expense claim has been submitted to the finance team for processing.",
    "ticket":          "✅ Your support ticket has been raised. A reference number has been assigned.",
    "personal_update": "✅ Your personal details have been updated in the HR portal.",
    "reimbursement":   "✅ Your reimbursement request has been submitted for manager approval.",
}


def detect_action(query: str) -> tuple[str, dict]:
    """
    Detect which action type a query is requesting.
    Returns (action_type, action_meta).
    """
    q = query.lower()
    if any(kw in q for kw in ["salary", "pay ", "compensation", "wage"]):
        return "salary_update", ACTION_REGISTRY["salary_update"]
    if any(kw in q for kw in ["bulk email", "email to all", "notify all", "send email"]):
        return "bulk_email", ACTION_REGISTRY["bulk_email"]
    if any(kw in q for kw in ["terminate", "fire ", "dismiss", "let go"]):
        return "termination", ACTION_REGISTRY["termination"]
    if any(kw in q for kw in ["grant access", "revoke access", "permission"]):
        return "access_grant", ACTION_REGISTRY["access_grant"]
    if any(kw in q for kw in ["leave", "vacation request", "pto request", "time off"]):
        return "leave_request", ACTION_REGISTRY["leave_request"]
    return "record_update", ACTION_REGISTRY["record_update"]


async def queue_hitl_action(
    query: str,
    user: str,
    request_id: str,
) -> dict:
    """
    Enqueue a HITL task and emit trace event.
    Returns the pending task dict.
    """
    action_type, action_meta = detect_action(query)
    task = hitl_queue.enqueue(
        user=user,
        query=query,
        action_type=action_type,
        action_description=action_meta["description"],
        risk_label=action_meta["risk_label"],
        context={"request_id": request_id, "action_type": action_type},
    )

    await tracer.emit(
        request_id, "action_agent", "hitl_queued",
        f"Action '{action_type}' queued for human approval — task_id: {task['task_id'][:8]}",
        status="hitl",
    )

    return task


async def execute_approved_action(task: dict, request_id: str) -> dict:
    """
    Simulate execution of an approved HITL action.
    Returns a result dict.
    """
    action_type = task.get("action_type", "unknown")

    await tracer.emit(
        request_id, "action_agent", "executing",
        f"Executing approved action: {action_type}",
        status="ok",
    )

    # Simulated outcomes per action type
    simulated_results = {
        "salary_update": "Salary record updated in HRIS (simulated). Change effective next payroll cycle.",
        "bulk_email":    "Bulk email queued in notification system (simulated). Estimated delivery: 5 minutes.",
        "record_update": "Employee record updated in HR database (simulated).",
        "access_grant":  "Access permissions updated in IAM system (simulated).",
        "termination":   "Termination workflow initiated in HRIS (simulated). IT notified for offboarding.",
        "leave_request": "Leave request submitted to HR portal (simulated). Pending manager approval.",
    }

    result_message = simulated_results.get(action_type, "Action executed (simulated).")

    await tracer.emit(
        request_id, "action_agent", "completed",
        f"Action complete: {result_message}",
        status="done",
    )

    return {"success": True, "message": result_message, "action_type": action_type}


async def execute_supervised_action(
    query: str,
    user: str,
    action_type: str,
    request_id: str,
) -> dict:
    """
    Execute a SUPERVISED self-service action immediately — no approval gate.
    Logs to trace and audit. Returns a confirmation dict.
    """
    await tracer.emit(
        request_id, "action_agent", "supervised_executing",
        f"Executing supervised action '{action_type}' for user '{user}' — no approval required",
        status="ok",
    )

    # Match on action_type prefix for flexibility (e.g. "leave_request" matches "leave")
    message = next(
        (msg for key, msg in SUPERVISED_RESULTS.items() if action_type.startswith(key) or key in action_type),
        f"✅ Your request has been submitted and logged. A confirmation will follow from HR."
    )

    audit_logger.append(
        user=user, query=query, autonomy_tier=SUPERVISED,
        safety_pre="PASS", safety_post="N/A",
        acl_level=0, chunks_retrieved=0, chunks_denied=0,
        integrity_ok=True, action_taken=f"supervised:{action_type}",
        hitl_decision=None, outcome="SUCCESS",
        request_id=request_id,
    )

    await tracer.emit(
        request_id, "action_agent", "supervised_complete",
        f"Supervised action complete: {action_type}",
        status="done",
    )

    return {"success": True, "message": message, "action_type": action_type}
