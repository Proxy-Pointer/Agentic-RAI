"""
Integrity Checker — SHA-256 document hash verification.
Detects tampering by comparing stored hashes against current content.
"""
import hashlib
from typing import Optional


def compute_hash(content: str) -> str:
    """Compute SHA-256 hex digest of document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class IntegrityChecker:
    def __init__(self):
        # doc_id -> original SHA-256 hash (set at seed time)
        self._hashes: dict[str, str] = {}
        # doc_id -> tampered flag (toggled via admin demo UI)
        self._tampered: dict[str, bool] = {}

    def register(self, doc_id: str, content: str):
        """Register the original hash for a document at seed time."""
        self._hashes[doc_id] = compute_hash(content)
        self._tampered[doc_id] = False

    def verify(self, doc_id: str, content: str) -> tuple[bool, str]:
        """
        Verify document integrity.
        Returns (is_ok, message).
        """
        expected = self._hashes.get(doc_id)
        if expected is None:
            return True, "Hash not registered (skipping check)"

        actual = compute_hash(content)
        if actual == expected:
            return True, f"OK (sha256: {actual[:12]}...)"
        return False, f"HASH MISMATCH: {doc_id} — expected {expected[:12]}... got {actual[:12]}..."


    def toggle_tamper(self, doc_id: str) -> bool:
        """Toggle the tamper flag for a document. Returns new state."""
        self._tampered[doc_id] = not self._tampered.get(doc_id, False)
        return self._tampered[doc_id]

    def get_tamper_state(self, doc_id: str) -> bool:
        return self._tampered.get(doc_id, False)

    def get_all_states(self) -> dict[str, dict]:
        return {
            doc_id: {
                "hash": self._hashes.get(doc_id, ""),
                "tampered": self._tampered.get(doc_id, False),
            }
            for doc_id in self._hashes
        }


# Module-level singleton
integrity_checker = IntegrityChecker()
