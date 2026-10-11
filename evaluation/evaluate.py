"""Retrieval evaluation for Rural Scheme Advisor.

Run from the project folder (virtual environment active):
    python evaluation/evaluate.py --check     # offline: do the expected keywords exist in the indexed documents? (no API calls)
    python evaluation/evaluate.py             # full run: Recall@K, MRR, per-type results, MIN_SCORE sweep (needs GEMINI_API_KEY)

dataset.csv columns: question, scheme_id, expected_keyword, answerable, type
 - expected_keyword: case-insensitive; use | to separate alternatives,
 - A retrieved chunk counts as RELEVANT if it comes from the row's scheme AND contains an expected keyword.
   This is a keyword-based proxy for relevance, so state it that way when you report results.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import config  # noqa: E402
from app.retriever import get_index  # noqa: E402

K = config.TOP_K


def load_rows():
    with open(Path(__file__).parent / "dataset.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def keywords(row):
    parts = re.split(r"(?<!\\)\|", row["expected_keyword"])
    return [p.strip().lower() for p in parts if p.strip()]


def is_relevant(row, chunk):
    if chunk["scheme_id"] != row["scheme_id"]:
        return False
    text = chunk["text"].lower()
    return any(k in text for k in keywords(row))


def check(idx, rows):
    print("Offline check: does each answerable question's keyword appear in its scheme's documents?\n")
    bad = 0
    for r in rows:
        if r["answerable"].strip().lower() != "yes":
            continue
        n = sum(is_relevant(r, c) for c in idx.chunks)
        if n == 0:
            bad += 1
            print(f"  NOT FOUND  [{r['scheme_id']}] {r['question']}   (keywords: {r['expected_keyword']})")
    total = sum(r["answerable"].strip().lower() == "yes" for r in rows)
    print(f"\n{total - bad}/{total} answerable questions have supporting text in the index.")
    print("Fix NOT FOUND rows: change the keyword, or remove the row if the document simply doesn't cover it.")


def main():
    idx = get_index()
    if idx is None:
        sys.exit("No index found. Run: python -m app.ingest")
    rows = load_rows()
    if "--check" in sys.argv:
        return check(idx, rows)

    from app import llm

    print(f"Embedding {len(rows)} questions...")
    qvecs = llm.embed([r["question"] for r in rows], task="RETRIEVAL_QUERY")

    stats = defaultdict(lambda: {"n": 0, "hit": 0, "rr": 0.0})
    top1_answerable, top1_unanswerable = [], []
    for r, qv in zip(rows, qvecs):
        hits = idx.search(qv, K)
        if r["answerable"].strip().lower() == "yes":
            rank = next((i for i, h in enumerate(hits, 1) if is_relevant(r, h.chunk)), None)
            for key in ("ALL", r["type"]):
                s = stats[key]
                s["n"] += 1
                s["hit"] += rank is not None
                s["rr"] += 1 / rank if rank else 0.0
            top1_answerable.append(hits[0].score if hits else 0.0)
        else:
            top1_unanswerable.append(hits[0].score if hits else 0.0)

    print(f"\nRetrieval quality (K={K}, relevant = right scheme + keyword match)")
    print(f"{'subset':<20}{'n':>4}{'Recall@K':>10}{'MRR':>8}")
    for key in sorted(stats, key=lambda k: (k != "ALL", k)):
        s = stats[key]
        print(f"{key:<20}{s['n']:>4}{s['hit'] / s['n']:>10.3f}{s['rr'] / s['n']:>8.3f}")

    if top1_unanswerable:
        print(f"\nOut-of-scope questions: {len(top1_unanswerable)}; highest top-1 score = {max(top1_unanswerable):.3f}")
        print(f"Answerable questions: lowest top-1 score = {min(top1_answerable):.3f}")
        print("\nMIN_SCORE sweep (higher threshold = refuses more):")
        print(f"{'MIN_SCORE':>10}{'answerable kept':>18}{'out-of-scope refused':>24}")
        for t in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
            kept = sum(s >= t for s in top1_answerable) / len(top1_answerable)
            refused = sum(s < t for s in top1_unanswerable) / len(top1_unanswerable)
            print(f"{t:>10.2f}{kept:>18.0%}{refused:>24.0%}")
        print(f"\nCurrent MIN_SCORE = {config.MIN_SCORE}")


if __name__ == "__main__":
    main()
