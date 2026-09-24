"""
RAG server — Release 1 requirement.

Shared, non-containerised HTTP wrapper around rag_pipeline.py's three
capabilities (refresh_corpus, retrieve_context, answer_question). A
plain REST API rather than the MCP protocol (unlike ../mcp-server/) so
any of the five Flask backends can call it with a single `requests`
call, the same way they already call AI-Mode — see ../ai-mode/README.md
for why a shared HTTP service was chosen over a shared Python import.

Run this as a local host process (NOT a docker-compose service — Release
1 requires AI-Mode, the MCP server, the RAG server, and the agentic loop
to all be non-containerised):

    ./run_local.sh

or directly:

    python3 rag_server.py

Listens on http://localhost:5101 by default (override with PORT). Start
this BEFORE `docker compose up`, alongside ai-mode's and mcp-server's own
run_local.sh scripts.
"""
import os

from flask import Flask, jsonify, request

import rag_pipeline

app = Flask(__name__)


@app.get("/health")
def health():
    loaded = bool(rag_pipeline._state["chunks"])
    return jsonify({
        "status": "ok" if loaded else "degraded",
        "service": "rag-server",
        "corpus_loaded": loaded,
        "chunk_count": len(rag_pipeline._state["chunks"]),
    })


@app.post("/refresh_corpus")
def refresh_corpus_route():
    result = rag_pipeline.refresh_corpus(caller=request.remote_addr)
    status_code = 200 if result.get("status") == "success" else 500
    return jsonify(result), status_code


@app.route("/retrieve_context", methods=["GET", "POST"])
def retrieve_context_route():
    payload = request.get_json(silent=True) or {}
    query = request.args.get("query") or payload.get("query")
    k = request.args.get("k", type=int) or payload.get("k") or 5
    result = rag_pipeline.retrieve_context(query, k=k, caller=request.remote_addr)
    status_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), status_code


@app.route("/answer_question", methods=["GET", "POST"])
def answer_question_route():
    payload = request.get_json(silent=True) or {}
    query = request.args.get("query") or payload.get("query")
    k = request.args.get("k", type=int) or payload.get("k") or 5
    result = rag_pipeline.answer_question(query, k=k, caller=request.remote_addr)
    status_code = 200 if "error" not in result else 400
    return jsonify(result), status_code


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5101))
    startup = rag_pipeline.refresh_corpus()
    print("Starting Personal Finance RAG Server...")
    print("Server status: RUNNING")
    print(f"Corpus loaded: {startup}")
    print("Available tools:")
    print("- refresh_corpus (POST /refresh_corpus)")
    print("- retrieve_context (GET/POST /retrieve_context?query=...)")
    print("- answer_question (GET/POST /answer_question?query=...)")
    app.run(host="0.0.0.0", port=port)
