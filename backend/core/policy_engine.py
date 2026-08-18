"""
Policy Engine — classifies every incoming request into an autonomy tier.

Uses a lightweight LLM-based semantic intent classifier (gemini-3.1-flash-lite)
to determine:
  - Autonomy tier (AUTONOMOUS / SUPERVISED / REQUIRES_HITL)
  - Whether a hierarchical ACL target check is required
  - The target entity (resolved, including pronouns like "my" / "me")

Fail-closed: any LLM error or malformed response defaults to REQUIRES_HITL.
"""
import json

from .config import gemini_client, SYNTH_MODEL

AUTONOMOUS    = "AUTONOMOUS"
SUPERVISED    = "SUPERVISED"
REQUIRES_HITL = "REQUIRES_HITL"

_CLASSIFIER_PROMPT = """\
TASK: Classify the following user query into the correct autonomy tier for an enterprise HR AI assistant.
The current user making the request is: "{user}"

CRITICAL RULE — READ vs WRITE:
The MOST important distinction is whether the query is a READ (retrieving/viewing information)
or a WRITE (creating, updating, deleting, or sending something).

- READ queries (show, view, display, list, get, what is, tell me about, find) → ALWAYS AUTONOMOUS
- WRITE queries → classify further into SUPERVISED or REQUIRES_HITL based on risk

IMPORTANT: Access control on sensitive data (employee records, PII, salary bands) is enforced
by a separate ACL system — NOT by this classifier. Do NOT classify a read query as REQUIRES_HITL
just because the data being requested is sensitive. "Show me employee records" is AUTONOMOUS —
the ACL layer will decide what the user can actually see.

TIER DEFINITIONS:
- AUTONOMOUS: Any read-only information query. No state changes. No write actions.
  Examples: asking about policies, benefits, leave entitlements, salary bands,
  viewing employee records, requesting reports, looking up any company information.

- SUPERVISED: User-initiated write actions that affect ONLY the requesting user and are low-risk.
  Examples: submitting a leave request, filing an expense claim, updating own personal details,
  raising a support ticket, requesting reimbursement.

- REQUIRES_HITL: High-risk administrative write actions that affect other employees or the
  organization, or are irreversible. Examples: updating another employee's salary or compensation,
  sending bulk emails to all staff, terminating employment, granting/revoking system access,
  deleting employee records, overriding policies, promoting or demoting staff.

RULES:
- When in doubt between tiers, escalate to the higher-risk tier (fail safe).
- Classify ONLY based on the intent of the query, not its phrasing.
- "Show", "view", "display", "list", "get", "what is", "tell me" → always READ → always AUTONOMOUS.
- Only classify as REQUIRES_HITL if the query explicitly intends to CREATE, MODIFY, DELETE, or SEND on behalf of the org or another person.
- For SUPERVISED actions (self-service writes):
  - These always affect only the requesting user.
  - If the query is self-referential (I, my, me, mine, for myself), set target_entity to "self".
  - If the query names another person as the target, still classify as REQUIRES_HITL not SUPERVISED.
  - Always set requires_target_check to true for SUPERVISED (self-only enforcement).
- For REQUIRES_HITL actions that target a specific person:
  - If self-referential language is used, set target_entity to "self".
  - If a specific person is named, extract their first name in lowercase.
  - If no specific person is targeted (e.g. bulk action on all), set target_entity to null.
- requires_target_check must be true for any REQUIRES_HITL action targeting a specific person.
- Respond with ONLY a valid JSON object. No markdown, no explanation, no extra text.

JSON Schema:
{{
  "tier": "AUTONOMOUS" | "SUPERVISED" | "REQUIRES_HITL",
  "reason": "one-sentence explanation of the classification",
  "action_type": "brief snake_case label, e.g. salary_update | leave_request | policy_query | bulk_email | record_deletion | access_grant | termination | record_view",
  "risk_score": 0.0 to 1.0,
  "requires_target_check": true | false,
  "target_entity": "first name in lowercase, or self, or null"
}}

USER QUERY TO CLASSIFY:
{query}
"""


def classify(query: str, user: str = "alice") -> dict:
    """
    Classify the query into an autonomy tier using the Gemini intent classifier.
    Returns: {tier, reason, action_type, risk_score, requires_target_check, target_entity}

    Fails closed to REQUIRES_HITL on any LLM error or malformed JSON.
    """
    prompt = _CLASSIFIER_PROMPT.format(query=query, user=user)

    try:
        response = gemini_client.models.generate_content(
            model=SYNTH_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()

        # Strip markdown code fences if the model wraps the JSON
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        result = json.loads(raw)

        # Validate tier is a known value
        if result.get("tier") not in (AUTONOMOUS, SUPERVISED, REQUIRES_HITL):
            raise ValueError(f"Unknown tier: {result.get('tier')}")

        return result

    except Exception as exc:
        # Fail closed — any error escalates to REQUIRES_HITL
        return {
            "tier": REQUIRES_HITL,
            "reason": f"Policy classifier unavailable — escalating to REQUIRES_HITL for safety. ({type(exc).__name__}: {exc})",
            "action_type": "unknown",
            "risk_score": 1.0,
            "requires_target_check": False,
            "target_entity": None,
        }
