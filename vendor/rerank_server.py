"""
Rerank Server — FastAPI wrapper for Qwen3-Reranker via mlx-lm.

Qwen3-Reranker is a generative model that outputs "yes" or "no".
The relevance score is the softmax probability of "yes" vs "no" tokens.

Provides OpenAI-compatible /v1/rerank endpoint expected by EverMemOS.

Usage:
    python vendor/rerank_server.py
    # Starts on port 12000

Reference:
    https://docs.vllm.ai/en/v0.9.2/examples/offline_inference/qwen3_reranker.html
"""

import os
import logging
from typing import List, Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rerank_server")

RERANK_MODEL = os.getenv("RERANK_MODEL", "mlx-community/Qwen3-Reranker-4B-mxfp8")
PORT = int(os.getenv("RERANK_PORT", "12000"))

app = FastAPI(title="Rerank Server (MLX)")

# Lazy-loaded model
_model = None
_tokenizer = None
_yes_token_id = None
_no_token_id = None


def _load_model():
    global _model, _tokenizer, _yes_token_id, _no_token_id
    if _model is not None:
        return
    logger.info(f"Loading reranker model: {RERANK_MODEL}")
    from mlx_lm import load
    _model, _tokenizer = load(RERANK_MODEL)

    # Find token IDs for "yes" and "no"
    _yes_token_id = _tokenizer.encode("yes", add_special_tokens=False)[-1]
    _no_token_id = _tokenizer.encode("no", add_special_tokens=False)[-1]
    logger.info(f"Reranker loaded. yes_id={_yes_token_id}, no_id={_no_token_id}")


# ── Schemas ──

class RerankRequest(BaseModel):
    model: str = RERANK_MODEL
    query: str
    documents: List[str]
    top_n: Optional[int] = None


class RerankResult(BaseModel):
    index: int
    relevance_score: float


class RerankResponse(BaseModel):
    results: List[RerankResult]


# ── Qwen3-Reranker prompt format ──

_PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_DEFAULT_INSTRUCTION = "Given a question and a passage, determine if the passage contains information relevant to answering the question."


def _build_prompt(query: str, document: str, instruction: str = _DEFAULT_INSTRUCTION) -> str:
    return f"{_PREFIX}<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}{_SUFFIX}"


def _score_pair(query: str, document: str) -> float:
    """Score a query-document pair using Qwen3-Reranker logit probabilities."""
    import mlx.core as mx
    import mlx.nn as nn

    prompt = _build_prompt(query, document)
    tokens = _tokenizer.encode(prompt)
    input_ids = mx.array([tokens])

    # Forward pass to get logits
    logits = _model(input_ids)
    # Get logits for the last token position
    last_logits = logits[0, -1, :]

    # Extract yes/no logits and compute softmax probability
    yes_no_logits = mx.array([last_logits[_yes_token_id], last_logits[_no_token_id]])
    probs = nn.softmax(yes_no_logits)
    yes_prob = float(probs[0])

    return yes_prob


# ── Endpoints ──

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    _load_model()
    yield

app = FastAPI(title="Rerank Server (MLX)", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "model": RERANK_MODEL}


@app.post("/v1/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    """Rerank documents against a query using Qwen3-Reranker yes/no logit scoring."""
    if not req.documents:
        return RerankResponse(results=[])

    results = []
    for i, doc in enumerate(req.documents):
        try:
            score = _score_pair(req.query, doc)
            results.append(RerankResult(index=i, relevance_score=score))
        except Exception as e:
            logger.warning(f"Error scoring document {i}: {e}")
            results.append(RerankResult(index=i, relevance_score=0.0))

    # Sort by score descending
    results.sort(key=lambda r: r.relevance_score, reverse=True)

    if req.top_n and req.top_n > 0:
        results = results[:req.top_n]

    return RerankResponse(results=results)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
