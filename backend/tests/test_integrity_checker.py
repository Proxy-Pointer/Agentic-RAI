"""
Tests — Integrity Checker
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.core.integrity_checker import IntegrityChecker, compute_hash


class TestIntegrityChecker:
    def setup_method(self):
        self.checker = IntegrityChecker()
        self.content = "NovaCorp vacation policy content."
        self.checker.register("vacation_policy", self.content)

    def test_compute_hash_deterministic(self):
        h1 = compute_hash("hello")
        h2 = compute_hash("hello")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_hash_different_content(self):
        h1 = compute_hash("content A")
        h2 = compute_hash("content B")
        assert h1 != h2

    def test_verify_passes_unmodified(self):
        ok, msg = self.checker.verify("vacation_policy", self.content)
        assert ok is True
        assert "OK" in msg

    def test_verify_fails_modified_content(self):
        ok, msg = self.checker.verify("vacation_policy", self.content + " MODIFIED")
        assert ok is False
        assert "MISMATCH" in msg

    def test_verify_unregistered_doc_passes(self):
        ok, msg = self.checker.verify("unknown_doc", "any content")
        assert ok is True  # no hash registered = skip check

    def test_toggle_tamper_fails_check(self):
        # Before toggle
        ok, _ = self.checker.verify("vacation_policy", self.content)
        assert ok is True

        # Toggle tamper on
        new_state = self.checker.toggle_tamper("vacation_policy")
        assert new_state is True

        # Verify fails even with correct content
        ok, msg = self.checker.verify("vacation_policy", self.content)
        assert ok is False
        assert "tampered" in msg.lower()

    def test_toggle_tamper_twice_restores(self):
        self.checker.toggle_tamper("vacation_policy")  # on
        self.checker.toggle_tamper("vacation_policy")  # off
        ok, _ = self.checker.verify("vacation_policy", self.content)
        assert ok is True

    def test_get_all_states(self):
        states = self.checker.get_all_states()
        assert "vacation_policy" in states
        assert "hash" in states["vacation_policy"]
        assert "tampered" in states["vacation_policy"]
        assert states["vacation_policy"]["tampered"] is False
