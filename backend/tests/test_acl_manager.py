"""
Tests — ACL Manager
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.core.acl_manager import (
    get_user_acl_level, can_access, is_pii, chroma_where_clause
)


class TestACLManager:
    def test_alice_level_zero(self):
        assert get_user_acl_level("alice") == 0

    def test_bob_level_one(self):
        assert get_user_acl_level("bob") == 1

    def test_admin_level_three(self):
        assert get_user_acl_level("admin") == 3

    def test_unknown_user_defaults_zero(self):
        assert get_user_acl_level("unknown_user") == 0

    def test_alice_can_access_public(self):
        assert can_access("alice", 0) is True

    def test_alice_cannot_access_hr_only(self):
        assert can_access("alice", 1) is False

    def test_alice_cannot_access_admin(self):
        assert can_access("alice", 2) is False

    def test_alice_cannot_access_pii(self):
        assert can_access("alice", 3) is False

    def test_bob_can_access_public(self):
        assert can_access("bob", 0) is True

    def test_bob_can_access_hr_only(self):
        assert can_access("bob", 1) is True

    def test_bob_cannot_access_pii(self):
        assert can_access("bob", 3) is False

    def test_admin_can_access_all(self):
        assert can_access("admin", 0) is True
        assert can_access("admin", 1) is True
        assert can_access("admin", 2) is True
        assert can_access("admin", 3) is True

    def test_is_pii(self):
        assert is_pii(3) is True
        assert is_pii(2) is False
        assert is_pii(0) is False

    def test_chroma_where_alice(self):
        clause = chroma_where_clause("alice")
        assert clause == {"acl_level": {"$lte": 0}}

    def test_chroma_where_bob(self):
        clause = chroma_where_clause("bob")
        assert clause == {"acl_level": {"$lte": 1}}

    def test_chroma_where_admin(self):
        clause = chroma_where_clause("admin")
        assert clause == {"acl_level": {"$lte": 3}}
