import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag_pipeline


@pytest.fixture(autouse=True)
def _fresh_index():
    """Every test starts from a freshly loaded real corpus, not whatever
    state a previous test left behind."""
    rag_pipeline.refresh_corpus()
    yield


def test_refresh_corpus_loads_real_corpus_file():
    result = rag_pipeline.refresh_corpus()

    assert result["status"] == "success"
    assert result["chunk_count"] > 0
    assert result["chunk_count"] == len(rag_pipeline._state["chunks"])


def test_refresh_corpus_reports_error_for_missing_file():
    original_path = rag_pipeline.CORPUS_PATH
    rag_pipeline.CORPUS_PATH = "/nonexistent/corpus.jsonl"
    try:
        result = rag_pipeline.refresh_corpus()
    finally:
        rag_pipeline.CORPUS_PATH = original_path

    assert result["status"] == "error"
    assert "not found" in result["error"]


def test_retrieve_context_requires_query():
    result = rag_pipeline.retrieve_context("")

    assert result["status"] == "error"
    assert "query is required" in result["error"]


def test_retrieve_context_returns_relevant_chunks_for_a_real_question():
    result = rag_pipeline.retrieve_context("how do I create a budget", k=3)

    assert result["status"] == "success"
    assert len(result["results"]) > 0
    source_ids = [r["source_id"] for r in result["results"]]
    assert "faq-create-budget" in source_ids
    for r in result["results"]:
        assert set(r.keys()) >= {"chunk_id", "source_id", "authority_tier", "distance", "text"}


def test_retrieve_context_returns_empty_results_for_irrelevant_query():
    result = rag_pipeline.retrieve_context("what is the capital of france")

    assert result["status"] == "success"
    assert result["results"] == []


def test_answer_question_returns_insufficient_context_for_irrelevant_query():
    result = rag_pipeline.answer_question("what is the capital of france")

    assert result["confidence_category"] == "insufficient"
    assert result["citations"] == []
    assert "enough information" in result["answer"]


@patch("rag_pipeline.requests.post")
def test_answer_question_calls_ai_mode_and_returns_citations(mock_post):
    mock_post.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: {"response": "A budget sets a target spending amount per category."},
    )

    result = rag_pipeline.answer_question("how do I create a budget")

    assert result["answer"] == "A budget sets a target spending amount per category."
    assert "faq-create-budget" in result["citations"]
    assert result["confidence_category"] in {"high", "medium", "low"}
    called_url = mock_post.call_args.args[0]
    assert called_url == f"{rag_pipeline.AI_MODE_URL}/api/generate"
    sent_prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "ONLY the context" in sent_prompt


@patch("rag_pipeline.requests.post")
def test_answer_question_does_not_call_ai_mode_when_insufficient_context(mock_post):
    rag_pipeline.answer_question("what is the capital of france")

    mock_post.assert_not_called()


@patch("rag_pipeline.requests.post")
def test_answer_question_returns_structured_error_when_ai_mode_unreachable(mock_post):
    mock_post.side_effect = rag_pipeline.requests.RequestException("connection refused")

    result = rag_pipeline.answer_question("how do I create a budget")

    assert "error" in result
    assert "Could not reach AI-Mode" in result["error"]


def test_answer_question_requires_query():
    assert rag_pipeline.answer_question("") == {"error": "query is required"}
