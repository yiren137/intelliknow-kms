"""LangChain-based document loader + text splitter."""
from __future__ import annotations
import os
from typing import List, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from config.settings import get_settings

settings = get_settings()

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def _load_docx(file_path: str) -> List[Tuple[str, int | None]]:
    """Return list of (text, page_number) for DOCX files."""
    import docx2txt
    text = docx2txt.process(file_path)
    return [(text, None)]


def _load_pdf(file_path: str) -> List[Tuple[str, int | None]]:
    """Return list of (text, page_number) per page."""
    loader = PyPDFLoader(file_path)
    pages = loader.load()
    return [(p.page_content, p.metadata.get("page", None)) for p in pages]


def process_document(file_path: str) -> List[dict]:
    """Parse a PDF or DOCX and return a list of chunk dicts.

    Each dict has: chunk_text, chunk_index, page_number
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        raw_pages = _load_pdf(file_path)
    elif ext in (".docx", ".doc"):
        raw_pages = _load_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    chunks = []
    chunk_index = 0

    for text, page_num in raw_pages:
        if not text.strip():
            continue
        splits = _splitter.split_text(text)
        for split in splits:
            if not split.strip():
                continue
            chunks.append(
                {
                    "chunk_text": split.strip(),
                    "chunk_index": chunk_index,
                    "page_number": page_num,
                }
            )
            chunk_index += 1

    return chunks
