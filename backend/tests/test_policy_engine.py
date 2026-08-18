"""
Tests — Policy Engine
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.core.policy_engine import classify, AUTONOMOUS, SUPERVISED, REQUIRES_HITL


class TestPolicyEngine:
    # ── AUTONOMOUS ────────────────────────────────────────────────────────────
    def test_info_query_autonomous(self):
        r = classify("What is the vacation policy?")
        assert r["tier"] == AUTONOMOUS

    def test_parental_leave_query_autonomous(self):
        r = classify("How many weeks of parental leave do I get?")
        assert r["tier"] == AUTONOMOUS

    def test_expense_query_autonomous(self):
        r = classify("What is the meal allowance for domestic travel?")
        assert r["tier"] == AUTONOMOUS

    def test_salary_info_query_autonomous(self):
        # Just asking about salary bands (info) — not updating
        r = classify("What are the salary bands at NovaCorp?")
        assert r["tier"] == AUTONOMOUS

    # ── SUPERVISED ────────────────────────────────────────────────────────────
    def test_leave_request_supervised(self):
        r = classify("Submit a leave request for 5 days starting Monday")
        assert r["tier"] == SUPERVISED

    def test_expense_request_supervised(self):
        r = classify("I want to request reimbursement for my travel expenses")
        assert r["tier"] == SUPERVISED

    # ── REQUIRES_HITL ────────────────────────────────────────────────────────
    def test_salary_update_hitl(self):
        r = classify("Update Bob's salary to $200,000")
        assert r["tier"] == REQUIRES_HITL

    def test_bulk_email_hitl(self):
        r = classify("Send an email to all employees about the new policy")
        assert r["tier"] == REQUIRES_HITL

    def test_termination_hitl(self):
        r = classify("I need to terminate John Smith's employment")
        assert r["tier"] == REQUIRES_HITL

    def test_access_grant_hitl(self):
        r = classify("Grant access to the finance system for the new hire")
        assert r["tier"] == REQUIRES_HITL

    def test_delete_record_hitl(self):
        r = classify("Delete the employee record for EMP-042")
        assert r["tier"] == REQUIRES_HITL
