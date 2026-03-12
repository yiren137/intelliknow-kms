#!/usr/bin/env python3
"""One-time setup: create directories, initialize DB, seed intent spaces."""
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_settings
from db.database import init_db

settings = get_settings()

DIRS = [
    settings.uploads_dir,
    settings.faiss_dir,
    os.path.join(settings.faiss_dir, "hr"),
    os.path.join(settings.faiss_dir, "legal"),
    os.path.join(settings.faiss_dir, "finance"),
    os.path.join(settings.faiss_dir, "general"),
    os.path.dirname(settings.db_path) or "data",
]


def main():
    print("Creating directories...")
    for d in DIRS:
        os.makedirs(d, exist_ok=True)
        print(f"  ✓ {d}")

    print("\nInitializing database...")
    init_db()
    print(f"  ✓ {settings.db_path}")

    print("\nSetup complete! Next steps:")
    print("  1. Copy .env.example to .env and fill in your API keys")
    print("  2. Run: uvicorn api.main:app --reload")
    print("  3. Run: streamlit run admin/app.py")


if __name__ == "__main__":
    main()
