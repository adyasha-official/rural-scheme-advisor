"""Retrieval evaluation. Fill evaluation/dataset.csv with your own questions, then run:
    python evaluation/evaluate.py            (from backend/, needs GEMINI_API_KEY and a built index)

CSV columns: question,scheme_id,expected_keyword,answerable
 - expected_keyword: a word/phrase that must appear in a correct chunk (case-insensitive)
 - answerable: yes/no (no = should be refused; used to tune MIN_SCORE)
Reports Recall@K, MRR, and abstention behaviour at the current MIN_SCORE.
Answer faithfulness / citation accuracy: review a sample by hand and record it in the README."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import config, llm  # noqa: E402
from app.retriever import get_index  # noqa: E402

K = config.TOP_K


def main():
    idx = get_index()
    if idx is None:
        sys.exit("No index. Run: python -m app.ingest")
    rows = list(csv.DictReader(open(Path(__file__).parent / "dataset.csv", encoding="utf-8")))
    answerable = [r for r in rows if r["answerable"].strip().lower() == "yes"]
    unanswerable = [r for r in rows if r["answerable"].strip().lower() == "no"]

    recall = mrr = 0.0
    for r in answerable:
        q = llm.embed([r["question"]], task="RETRIEVAL_QUERY")[0]
        hits = idx.search(q, K)
        rank = next((i for i, h in enumerate(hits, 1) if r["expected_keyword"].lower() in h.chunk["text"].lower()), None)
        recall += rank is not None
        mrr += 1 / rank if rank else 0

    refused = 0
    top_scores_un = []
    for r in unanswerable:
        q = llm.embed([r["question"]], task="RETRIEVAL_QUERY")[0]
        hits = idx.search(q, 1)
        top_scores_un.append(hits[0].score if hits else 0)
        refused += (not hits) or hits[0].score < config.MIN_SCORE

    n = max(len(answerable), 1)
    print(f"Answerable questions: {len(answerable)}")
    print(f"  Recall@{K}: {recall / n:.3f}")
    print(f"  MRR:       {mrr / n:.3f}")
    print(f"Unanswerable questions: {len(unanswerable)}")
    if unanswerable:
        print(f"  Correctly refused at MIN_SCORE={config.MIN_SCORE}: {refused}/{len(unanswerable)}")
        print(f"  Highest top-score among them: {max(top_scores_un):.3f}  (set MIN_SCORE above this)")


if __name__ == "__main__":
    main()
