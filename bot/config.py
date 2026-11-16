import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "alpine-ops")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

# Pinecone hosted embedding model (no local torch needed)
EMBED_MODEL = os.getenv("EMBED_MODEL", "llama-text-embed-v2")
CHAT_MODEL = os.getenv("CHAT_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

DATA_DIRS = [
    ROOT / "MV Star Challenger Email Trail" / "extracted_emails",
    ROOT / "Pre Arrival Docs Emails",
]
DATA_FILES = [
    ROOT / "Spares Clearance Query Email.eml",
    ROOT / "Standard Enquries response - Wheat Cargo.eml",
    ROOT / "Emails Sent for Crewing Queries.docx",
    ROOT / "Port Tariiff of PQA & KPT.xls",
]
