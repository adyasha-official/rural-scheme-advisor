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
    task: RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY for questions."""
    from google.genai import types

    client = _get_client()
    vectors: list[list[float]] = []
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for attempt in range(5):
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
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** (attempt + 1))  # back off for free-tier rate limits
        if len(texts) > batch_size:
            time.sleep(1)
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