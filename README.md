# 🌾 Rural Scheme Advisor

**Live demo: https://rural-scheme-advisor-alpha.vercel.app**
(Backend on Render's free tier: the first request after a quiet period can take 30–60 seconds while the server wakes up.)

A multilingual (English / Hindi / Odia) RAG assistant that answers questions about Indian government welfare schemes **from official documents**, with page-level citations and a refusal path when the documents don't support an answer.

Schemes covered: PM-KISAN, PMAY-G, Ayushman Bharat PM-JAY, PM Ujjwala Yojana, MGNREGA.

| Stack | |
| --- | --- |
| Frontend | React + Vite (Vercel) |
| Backend | FastAPI, Pydantic (Render, Docker) |
| Retrieval | PyMuPDF extraction, section-aware chunking, Gemini multilingual embeddings, NumPy cosine search |
| Generation | Gemini API with backend-validated citations |

## How it works

```
OFFLINE (python -m app.ingest)
PDFs -> PyMuPDF text per page -> clean headers/footers -> section-aware chunks
     -> Gemini embeddings -> data/index/{chunks.json, embeddings.npy}

ONLINE (POST /api/chat)
question -> validate -> language / scheme / intent detection
         -> embed query -> cosine search (scheme-filtered when explicit)
         -> relevance threshold (MIN_SCORE) -> grounded Gemini prompt
         -> citation validation -> answer + sources (built from stored metadata)
```

Key design choices (good interview talking points):

- **Citations come from the backend, not the LLM.** The model only emits `[n]` markers; invalid markers are stripped, and an answer with no valid citation is refused.
- **Abstention.** If no chunk reaches `MIN_SCORE`, the LLM is never called.
- **Prompt-injection hygiene.** Excerpts are marked untrusted in the system prompt.
- **Index is a committed file** (numpy cosine search) rather than a hosted vector DB, so deployment needs no persistent disk. At this scale (thousands of chunks) it is fast and simple; ChromaDB/pgvector would be the next step if the corpus grows.
- **Hosted embeddings** (Gemini) keep the backend small enough for a free Render instance (no PyTorch model to load). Cross-lingual retrieval works because the embedding model is multilingual.
- **Recommendations** are transparent rule matching on scheme tags, and explicitly *not* an eligibility decision.
- **Honest limits:** Romanised Hindi ("kaun eligible hai") is detected as English; sessions are in-memory (single instance); no OCR for scanned PDFs.

## Run locally

Prerequisites: Python 3.11+, Node 18+, a free Gemini API key from https://aistudio.google.com/apikey

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                      # then put your GEMINI_API_KEY in it

# 2. Add official PDFs (see "Adding documents" below), then build the index
python -m app.ingest

# 3. Start the API
uvicorn app.main:app --reload                             # http://localhost:8000/docs

# 4. Frontend (new terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                                               # http://localhost:5173
```

Run the tests (no API key needed): `cd backend && pytest`

## Adding documents

1. Download official documents (guidelines, FAQs, operational guidelines) from each scheme's government portal.
2. Place them as `backend/data/raw/<scheme_id>/<file>.pdf` using ids: `pm_kisan`, `pmay_g`, `ayushman_bharat`, `ujjwala`, `mgnrega`.
3. Optionally record each file's official URL in `backend/data/sources.json` (`"pm_kisan/guidelines.pdf": {"url": "https://..."}`) so citations link to the exact source. Otherwise the scheme's portal link is used.
4. Run `python -m app.ingest`, then commit `backend/data/index/`.

Plain-text sources also work: put a `.txt` file (UTF-8) in the scheme's folder. This is useful for web pages that can't be saved as a text-based PDF. A `.txt` file counts as page 1 in citations.

`python -m app.ingest` reuses embeddings that are already saved in the index and only embeds new or changed chunks, so adding a document is quick and cheap. The Gemini free tier limits embedding requests per minute and per day. The script paces itself and waits when it hits the per-minute limit.

Raw PDFs are git-ignored by default: check each document's redistribution terms before committing them. Start with one scheme (PM-KISAN), verify answers, then add the rest.

## Evaluate

Edit `evaluation/dataset.csv` (aim for ~50 questions: direct, paraphrased, Hindi/Odia, ambiguous, and out-of-scope), then:

```bash
cd backend && python ../evaluation/evaluate.py --check   # offline: does each expected keyword exist in your indexed documents?
python ../evaluation/evaluate.py             # Recall@K, MRR, per-type results, MIN_SCORE sweep
```

A retrieved chunk counts as relevant if it comes from the right scheme and contains one of the row's expected keywords, so these numbers measure retrieval with a keyword-based proxy for relevance, not human-judged answer quality. The script also prints a `MIN_SCORE` sweep showing how many answerable questions are kept and how many out-of-scope questions are refused at each threshold. Record **your measured numbers** below; don't claim figures you haven't measured.

| Metric | Result |
| --- | --- |
| Recall@5 | _to measure_ |
| MRR | _to measure_ |
| Answer faithfulness (manual review of N answers) | _to measure_ |
| Citation accuracy (manual review) | _to measure_ |

## Deploy

**Backend → Render**
1. Push the repo to GitHub (make sure `backend/data/index/` is committed).
2. Render → New → Blueprint → select the repo (uses `render.yaml`), or New Web Service → Docker, root directory `backend`.
3. Set secrets in the Render dashboard: `GEMINI_API_KEY`, and `ALLOWED_ORIGINS` (your Vercel URL, no trailing slash).
4. Check `https://<your-service>.onrender.com/health` → `"index_loaded": true`.
(Free instances sleep when idle; the first request after a break is slow.)

**Frontend → Vercel**
1. Vercel → Add New Project → import the repo, set **Root Directory** to `frontend`.
2. Add env var `VITE_API_URL` = your Render URL.
3. Deploy, then put the Vercel URL into the backend's `ALLOWED_ORIGINS` and redeploy the backend.

The API key lives only in Render's secret settings, never in React or Git.

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/chat` | `{question, session_id, language?}` → answer, status, sources |
| `GET /api/schemes`, `/api/schemes/{id}`, `/api/categories` | Scheme catalogue |
| `POST /api/recommendations` | `{needs[], occupation?}` → suggested schemes with reasons |
| `GET /health` | Service and index status |

## Disclaimer

Answers are generated from the indexed documents and may not reflect the latest rules. This is not an official source or an eligibility decision. Confirm on the official scheme portal or at your local office.
