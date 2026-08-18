"""
ACL Manager — resolves the access level for a given user.
"""
from .config import USER_ACL, ACL_LEVELS


def get_user_acl_level(user: str) -> int:
    """Return the max acl_level the user is permitted to access."""
    return USER_ACL.get(user.lower(), 0)


def get_user_acl_label(user: str) -> str:
    level = get_user_acl_level(user)
    reverse = {v: k for k, v in ACL_LEVELS.items()}
    return reverse.get(level, "ALL")


def can_access(user: str, doc_acl_level: int) -> bool:
    """Return True if user's clearance >= document's acl_level."""
    return get_user_acl_level(user) >= doc_acl_level


def is_pii(doc_acl_level: int) -> bool:
    return doc_acl_level >= ACL_LEVELS["PII"]


def chroma_where_clause(user: str) -> dict:
    """
    Build the ChromaDB 'where' pre-filter for this user.
    Only fetches documents where acl_level <= user's max level.
    Denied docs are never retrieved from the vector store.
    """
    return {"acl_level": {"$lte": get_user_acl_level(user)}}
