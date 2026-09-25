"""
RAG pipeline — Release 1 requirement.

Implements the three capabilities the Release 1 brief asks the shared RAG
server for: rebuilding a retrieval index (`refresh_corpus`), retrieving
relevant knowledge chunks for a query (`retrieve_context`), and answering
a question using only retrieved context, with citations and a confidence
category (`answer_question`).

Deliberately lightweight: this project's knowledge base is ~24 short
finance/app-help documents (see corpus/corpus.jsonl), not a large
enterprise corpus, so this uses a small hand-rolled TF-IDF + cosine
similarity index instead of a vector database and embedding model. That
avoids a heavy dependency (e.g. chromadb, sentence-transformers) for a
problem this size, while still giving genuine ranked retrieval rather
than a fixed/keyword-only lookup. Swapping in a real vector store later
would only mean rewriting `_build_index`/`_score` — the three public
functions and their return shapes would not need to change.

Grounded generation goes through the shared AI-Mode service (see
../ai-mode/), the same local Ollama-backed LLM every module's own
backend already calls — this does not talk to Ollama directly, so model
selection/timeouts/error-handling stay centralised in one place as
ai-mode's own README explains.
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = Path(os.environ.get("RAG_CORPUS_PATH", BASE_DIR / "corpus" / "corpus.jsonl"))

AI_MODE_URL = os.environ.get("AI_MODE_URL", "http://localhost:5099").rstrip("/")
AI_MODE_MODEL = os.environ.get("AI_MODE_MODEL", "qwen2.5:0.5b")
GENERATION_TIMEOUT = int(os.environ.get("RAG_GENERATION_TIMEOUT", "60"))

# Cosine-similarity thresholds for confidence_category / the
# insufficient-context fallback. Tuned for this corpus's short documents,
# not a general-purpose constant.
MIN_CONTEXT_SCORE = 0.05
HIGH_CONFIDENCE_SCORE = 0.35
MEDIUM_CONFIDENCE_SCORE = 0.15

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "how", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "was", "what", "when", "which", "who", "why",
    "will", "with", "does", "do", "can", "i", "my", "your", "you", "me",
    "about", "tell", "please", "could", "would", "should", "into", "than",
    "then", "if", "not", "no", "so", "just", "like", "get", "make", "let",
    "using", "use", "want", "know", "explain", "give", "show", "all",
    "some", "any", "there", "here", "am", "im", "we", "us", "our",
}

# Populated by refresh_corpus(); read by retrieve_context().
_state = {"chunks": [], "idf": {}, "vectors": []}


def _tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _term_freq_vector(tokens):
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {term: count / total for term, count in counts.items()}


def _cosine_similarity(vec_a, vec_b):
    shared_terms = set(vec_a) & set(vec_b)
    dot = sum(vec_a[t] * vec_b[t] for t in shared_terms)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _build_index(chunks):
    tokenised = [_tokenize(f"{c.get('title', '')} {c['text']}") for c in chunks]
    doc_count = len(chunks) or 1

    doc_freq = Counter()
    for tokens in tokenised:
        doc_freq.update(set(tokens))
    idf = {term: math.log((1 + doc_count) / (1 + df)) + 1 for term, df in doc_freq.items()}

    vectors = []
    for tokens in tokenised:
        tf = _term_freq_vector(tokens)
        vectors.append({term: weight * idf.get(term, 0.0) for term, weight in tf.items()})

    return idf, vectors


def _load_corpus_file(path):
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def refresh_corpus(caller=None):
    """Reload corpus/corpus.jsonl from disk and rebuild the TF-IDF index.

    Returns {"status": "success", "chunk_count": N, "collection": ...,
    "corpus_path": ...} on success, or {"status": "error", "error": ...}
    if the corpus file is missing or malformed — never raises.
    """
    try:
        chunks = _load_corpus_file(CORPUS_PATH)
    except FileNotFoundError:
        return {"status": "error", "error": f"Corpus file not found: {CORPUS_PATH}"}
    except (json.JSONDecodeError, OSError) as exc:
        return {"status": "error", "error": f"Could not read corpus: {exc}"}

    if not chunks:
        return {"status": "error", "error": f"Corpus file is empty: {CORPUS_PATH}"}

    idf, vectors = _build_index(chunks)
    _state["chunks"] = chunks
    _state["idf"] = idf
    _state["vectors"] = vectors

    return {
        "status": "success",
        "chunk_count": len(chunks),
        "collection": "personal_finance_knowledge_base",
        "corpus_path": str(CORPUS_PATH),
        "caller": caller,
    }


def _ensure_index_loaded():
    if not _state["chunks"]:
        refresh_corpus()


def retrieve_context(query, k=5, caller=None):
    """Retrieve the top-k most relevant knowledge chunks for `query`.

    Returns {"status": "success", "results": [{"chunk_id", "source_id",
    "authority_tier", "distance", "text"}, ...]} — `distance` here is
    `1 - cosine_similarity` (0 = perfect match, 1 = no overlap at all),
    matching the "distance" naming the Release 1 lab material uses for
    vector-store results, even though this index isn't a vector store.
    """
    if not query or not query.strip():
        return {"status": "error", "error": "query is required"}

    _ensure_index_loaded()
    if not _state["chunks"]:
        return {"status": "error", "error": "Knowledge base is empty or failed to load"}

    query_vector = {
        term: freq * _state["idf"].get(term, 0.0)
        for term, freq in _term_freq_vector(_tokenize(query)).items()
    }

    scored = []
    for chunk, vector in zip(_state["chunks"], _state["vectors"]):
        score = _cosine_similarity(query_vector, vector)
        scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = [
        {
            "chunk_id": chunk["id"],
            "source_id": chunk["source_id"],
            "authority_tier": chunk.get("authority_tier", "project-knowledge-base"),
            "distance": round(1 - score, 4),
            "text": chunk["text"],
        }
        for score, chunk in scored[: max(1, k)]
        if score > 0
    ]

    return {"status": "success", "results": results, "caller": caller}


def _confidence_category(top_score):
    if top_score >= HIGH_CONFIDENCE_SCORE:
        return "high"
    if top_score >= MEDIUM_CONFIDENCE_SCORE:
        return "medium"
    if top_score >= MIN_CONTEXT_SCORE:
        return "low"
    return "insufficient"


def _call_ai_mode(prompt):
    """Grounded generation via the shared AI-Mode service (see
    ../ai-mode/), not Ollama directly. Returns (text, error)."""
    try:
        response = requests.post(
            f"{AI_MODE_URL}/api/generate",
            json={"model": AI_MODE_MODEL, "prompt": prompt, "stream": False},
            timeout=GENERATION_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"Could not reach AI-Mode at {AI_MODE_URL}: {exc}"
    try:
        return response.json().get("response", "").strip(), None
    except ValueError:
        return None, f"AI-Mode at {AI_MODE_URL} returned a non-JSON response"


def answer_question(query, k=5, caller=None):
    """Answer `query` using only retrieved context, with citations and a
    confidence category. Returns an insufficient-context response instead
    of calling the LLM at all if nothing relevant enough was retrieved —
    see MIN_CONTEXT_SCORE."""
    if not query or not query.strip():
        return {"error": "query is required"}

    retrieval = retrieve_context(query, k=k, caller=caller)
    if retrieval.get("status") != "success":
        return {"error": retrieval.get("error", "Retrieval failed")}

    results = retrieval["results"]
    top_score = (1 - results[0]["distance"]) if results else 0.0
    confidence = _confidence_category(top_score)

    if confidence == "insufficient" or not results:
        return {
            "answer": (
                "I don't have enough information in the knowledge base to "
                "answer that question."
            ),
            "citations": [],
            "confidence_category": "insufficient",
            "retrieval_summary": f"{len(results)} chunk(s) retrieved, none met the relevance threshold",
        }

    context_block = "\n\n".join(f"[{r['source_id']}] {r['text']}" for r in results)
    prompt = (
        "Answer the question using ONLY the context below. "
        "If the context does not fully answer the question, say what is missing. "
        "Do not use outside knowledge.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {query}\n\n"
        "Answer in at most 3 sentences."
    )

    answer_text, error = _call_ai_mode(prompt)
    if error:
        return {"error": error}

    return {
        "answer": answer_text,
        "citations": [r["source_id"] for r in results],
        "confidence_category": confidence,
        "retrieval_summary": f"{len(results)} chunk(s) retrieved, top match score {round(top_score, 3)}",
    }


if __name__ == "__main__":
    print(json.dumps(refresh_corpus(), indent=2))
    print(json.dumps(retrieve_context("how do I set a budget"), indent=2))
    print(json.dumps(answer_question("what does an overdue bill mean"), indent=2))
