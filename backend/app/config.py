"""Central configuration. Everything tunable lives here or in environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "index"
SCHEMES_FILE = DATA_DIR / "schemes.json"
SOURCES_FILE = DATA_DIR / "sources.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
GEN_MODEL = os.getenv("GEN_MODEL", "gemini-3.8-flash")

# Chunking (words, a simple proxy for tokens)
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "260"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))

# Retrieval
TOP_K = int(os.getenv("TOP_K", "5"))
# Minimum cosine similarity for a chunk to count as relevant.
# Tune this with evaluation/evaluate.py on your own documents.
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.6"))

MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 4
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))

ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]
