"""Offline ingestion: PDFs -> cleaned, section-aware chunks -> embeddings -> index files.

Usage (from backend/):  python -m app.ingest
Expects PDFs in data/raw/<scheme_id>/<file>.pdf
"""
import json
import re
from collections import Counter

import numpy as np

from . import config, llm
from .nlp import get_scheme


def extract_pages(pdf_path) -> list[tuple[int, str]]:
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pages.append((i, page.get_text("text")))
    return pages


def clean_pages(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop lines repeated on many pages (headers/footers) and bare page numbers."""
    line_counts = Counter()
    for _, text in pages:
        for line in {l.strip() for l in text.splitlines() if l.strip()}:
            line_counts[line] += 1
    threshold = max(3, int(len(pages) * 0.4))
    cleaned = []
    for num, text in pages:
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                lines.append("")
                continue
            if len(pages) >= 5 and line_counts[s] >= threshold and len(s) < 120:
                continue
            if re.fullmatch(r"(page\s*)?\d{1,4}(\s*of\s*\d+)?", s, flags=re.I):
                continue
            lines.append(s)
        text = "\n".join(lines)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        cleaned.append((num, text))
    return cleaned


def looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 90 or s.endswith((".", ",", ";")):
        return False
    return bool(re.match(r"^(\d+(\.\d+)*[.)]?\s+\S|[A-Z][A-Z\s&/-]{3,}$)", s))


def chunk_page(text: str, words_per_chunk: int, overlap: int, section: str | None):
    """Split a page into paragraph-aligned chunks. Returns [(text, section)]."""
    chunks, current, current_words = [], [], 0
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        first = para.splitlines()[0]
        if looks_like_heading(first):
            section = first.strip()
        n = len(para.split())
        if current_words + n > words_per_chunk and current:
            body = "\n\n".join(current)
            chunks.append((body, section))
            tail = " ".join(body.split()[-overlap:]) if overlap else ""
            current, current_words = ([tail] if tail else []), len(tail.split())
        # very long paragraph: hard split by words
        if n > words_per_chunk:
            if current and current_words > overlap:
                chunks.append(("\n\n".join(current), section))
            words = para.split()
            step = max(1, words_per_chunk - overlap)
            for i in range(0, n, step):
                chunks.append((" ".join(words[i : i + words_per_chunk]), section))
            current, current_words = [], 0
            continue
        current.append(para)
        current_words += n
    if current:
        chunks.append(("\n\n".join(current), section))
    return [(t, s) for t, s in chunks if len(t.split()) >= 15], section


def build_chunks() -> list[dict]:
    sources = {}
    if config.SOURCES_FILE.exists():
        sources = json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    all_chunks = []
    for scheme_dir in sorted(p for p in config.RAW_DIR.glob("*") if p.is_dir()):
        scheme = get_scheme(scheme_dir.name)
        if not scheme:
            print(f"! Skipping {scheme_dir.name}: not in schemes.json")
            continue
        for pdf in sorted(list(scheme_dir.glob("*.pdf")) + list(scheme_dir.glob("*.txt"))):
            if pdf.suffix.lower() == ".txt":
                pages = [(1, pdf.read_text(encoding="utf-8", errors="replace"))]
            else:
                pages = clean_pages(extract_pages(pdf))
            empty = [n for n, t in pages if not t.strip()]
            if len(empty) == len(pages):
                print(f"! {pdf.name}: no extractable text (scanned PDF? OCR needed). Skipped.")
                continue
            key = f"{scheme['id']}/{pdf.name}"
            url = (sources.get(key) or {}).get("url") or scheme["official_url"]
            section = None
            for num, text in pages:
                pieces, section = chunk_page(
                    text, config.CHUNK_WORDS, config.CHUNK_OVERLAP_WORDS, section
                )
                for j, (body, sec) in enumerate(pieces, start=1):
                    all_chunks.append(
                        {
                            "id": f"{scheme['id']}_{pdf.stem}_p{num}_c{j:02d}",
                            "text": body,
                            "scheme_id": scheme["id"],
                            "scheme_name": scheme["name"],
                            "category": scheme["category"],
                            "document": pdf.name,
                            "document_title": f"{scheme['name']} - {pdf.stem.replace('_', ' ').title()}",
                            "page": num,
                            "section": sec,
                            "source_url": url,
                        }
                    )
            print(f"  {key}: {len(pages)} pages")
    return all_chunks


def save_index(chunks: list[dict], vectors: np.ndarray) -> None:
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.INDEX_DIR / "embeddings.npy", vectors)
    (config.INDEX_DIR / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False), encoding="utf-8"
    )


def embed_with_cache(chunks: list[dict]) -> np.ndarray:
    """Reuse vectors from the saved index for unchanged chunks; embed only new or changed ones."""
    cache = {}
    old_meta = config.INDEX_DIR / "chunks.json"
    old_vecs = config.INDEX_DIR / "embeddings.npy"
    if old_meta.exists() and old_vecs.exists():
        old_chunks = json.loads(old_meta.read_text(encoding="utf-8"))
        old_v = np.load(old_vecs)
        cache = {(c["id"], c["text"]): old_v[i] for i, c in enumerate(old_chunks)}
    todo = [i for i, c in enumerate(chunks) if (c["id"], c["text"]) not in cache]
    print(f"Reusing {len(chunks) - len(todo)} saved embeddings; embedding {len(todo)} new chunks.")
    new_vecs = llm.embed([chunks[i]["text"] for i in todo], task="RETRIEVAL_DOCUMENT") if todo else []
    todo_set, j, out = set(todo), 0, []
    for i, c in enumerate(chunks):
        if i in todo_set:
            out.append(new_vecs[j])
            j += 1
        else:
            out.append(cache[(c["id"], c["text"])])
    return np.array(out, dtype="float32")

def main() -> None:
    print("Reading PDFs from", config.RAW_DIR)
    chunks = build_chunks()
    if not chunks:
        print("No chunks produced. Put PDFs in data/raw/<scheme_id>/ first.")
        return
    print(f"Embedding {len(chunks)} chunks (this calls the Gemini API)...")
    vectors = embed_with_cache(chunks)
    save_index(chunks, vectors)
    print(f"Done. Saved index to {config.INDEX_DIR} - commit it so deployment needs no ingestion.")


if __name__ == "__main__":
    main()
