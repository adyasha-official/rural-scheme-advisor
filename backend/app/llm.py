"""Thin wrapper around the Gemini API for embeddings and generation.
Swap this file to change providers; nothing else depends on the SDK."""
import time

import numpy as np

from . import config

_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        from google import genai

        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
    """Return L2-normalised embeddings, shape (len(texts), EMBED_DIM).
    task: RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY for questions.
    Paced to stay under the free tier limit (100 texts per minute)."""
    from google.genai import types

    client = _get_client()
    vectors: list[list[float]] = []
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for attempt in range(8):
            try:
                res = client.models.embed_content(
                    model=config.EMBED_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task, output_dimensionality=config.EMBED_DIM
                    ),
                )
                vectors.extend(e.values for e in res.embeddings)
                break
            except Exception as e:
                if attempt == 7:
                    raise
                limited = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                wait = 62 if limited else 2 ** (attempt + 1)
                print(f"  waiting {wait}s (API limit or busy)...")
                time.sleep(wait)
        if len(texts) > batch_size:
            print(f"  embedded {min(i + batch_size, len(texts))}/{len(texts)}")
            time.sleep(14)  # ~85 texts per minute
    arr = np.array(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)


def generate(prompt: str, system: str) -> str:
    from google.genai import types

    for attempt in range(4):
        try:
            res = _get_client().models.generate_content(
                model=config.GEN_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
            )
            return (res.text or "").strip()
        except Exception as e:
            overloaded = "503" in str(e) or "429" in str(e)
            if not overloaded or attempt == 3:
                raise
            time.sleep(2 ** attempt * 2)  # wait 2s, 4s, 8s, then give up