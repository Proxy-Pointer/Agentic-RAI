"""
NovaCorp HR Agent — Centralized Configuration
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# ── Load .env from project root ─────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parents[2]  # backend/core/ -> backend/ -> project root
load_dotenv(_PROJECT_ROOT / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    logging.warning("GOOGLE_API_KEY not set — Gemini API calls will fail.")

# ── Models ───────────────────────────────────────────────────────────────────
EMBEDDING_MODEL    = "models/gemini-embedding-001"
EMBEDDING_DIMS     = 1536
SYNTH_MODEL        = "gemini-3.1-flash-lite"

# ── Embedding throughput (rate-limit guard) ──────────────────────────────────
EMBEDDING_BATCH_SIZE  = 20
EMBEDDING_BATCH_DELAY = 1.0   # seconds between batches

# ── ACL numeric levels — ChromaDB scalar $lte pre-filtering ─────────────────
ACL_LEVELS: dict[str, int] = {
    "ALL":     0,
    "HR_ONLY": 1,
    "ADMIN":   2,
    "PII":     3,
}

# Max acl_level each user can access (inclusive)
USER_ACL: dict[str, int] = {
    "alice": 0,   # Regular employee — PUBLIC only
    "bob":   1,   # HR Manager — up to HR_ONLY
    "admin": 3,   # System Admin — all levels
}

# ── ChromaDB ─────────────────────────────────────────────────────────────────
CHROMA_COLLECTION = "novacorp_policies"
CHROMA_DISTANCE   = "cosine"
RAG_TOP_K         = 5

# ── Google GenAI client (singleton) ─────────────────────────────────────────
gemini_client = genai.Client(api_key=GOOGLE_API_KEY)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("novacorp")
