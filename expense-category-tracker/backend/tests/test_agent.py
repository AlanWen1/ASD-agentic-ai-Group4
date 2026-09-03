import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent


def _ollama_message(content=None, tool_calls=None):
    return MagicMock(
        raise_for_status=lambda: None,
        json=lambda: {"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}},
    )


@patch("agent.requests.get")
@patch("agent.requests.post")
def test_agent_calls_a_tool_then_answers(mock_post, mock_get):
    """Plan -> Act -> Observe -> Adapt: the model asks for spending data on
    step 1 (Plan/Act), gets the real result back (Observe), then uses it to
    answer on step 2 (Adapt) — this is the actual multi-step loop, not a
    single call."""
    mock_post.side_effect = [
        _ollama_message(tool_calls=[
            {"function": {"name": "get_spending_by_category", "arguments": {}}}
        ]),
        _ollama_message(content="You spend the most on Groceries ($85.40)."),
    ]
    mock_get.return_value = MagicMock(
        ok=True,
        raise_for_status=lambda: None,
        json=lambda: [
            {"amount": 85.40, "category_name": "Groceries"},
            {"amount": 12.50, "category_name": "Dining"},
        ],
    )

    result = agent.run_agent_loop("Which category am I spending the most on?", user_id=1)

    assert result["answer"] == "You spend the most on Groceries ($85.40)."
    tool_steps = [t for t in result["trace"] if t["type"] == "tool_call"]
    assert len(tool_steps) == 1
    assert tool_steps[0]["tool"] == "get_spending_by_category"

    # The tool call to expense-database must have been scoped to this user.
    called_params = mock_get.call_args.kwargs["params"]
    assert called_params["user_id"] == 1


@patch("agent.requests.post")
def test_agent_answers_directly_when_no_tool_needed(mock_post):
    mock_post.return_value = _ollama_message(content="Hi! Ask me about your spending.")

    result = agent.run_agent_loop("hello", user_id=1)

    assert result["answer"] == "Hi! Ask me about your spending."
    assert result["trace"] == [{"step": 0, "type": "final_answer"}]


@patch("agent.requests.post")
def test_agent_gives_up_after_max_steps(mock_post):
    # The model keeps asking for tools forever — the loop must still stop.
    mock_post.return_value = _ollama_message(tool_calls=[
        {"function": {"name": "get_categories", "arguments": {}}}
    ])
    with patch("agent.requests.get", return_value=MagicMock(ok=True, raise_for_status=lambda: None, json=lambda: [])):
        result = agent.run_agent_loop("keep looping", user_id=1, max_steps=2)

    assert "wasn't able to finish" in result["answer"]
    assert mock_post.call_count == 2


def test_get_spending_by_category_aggregates_and_sorts(monkeypatch):
    def fake_get_expenses(user_id, category_id=None):
        return [
            {"amount": 10, "category_name": "Dining"},
            {"amount": 5, "category_name": "Dining"},
            {"amount": 30, "category_name": "Groceries"},
            {"amount": 2, "category_name": None},
        ]

    monkeypatch.setattr(agent, "get_expenses", fake_get_expenses)

    result = agent.get_spending_by_category(user_id=1)

    assert result[0] == {"category": "Groceries", "total": 30}
    assert result[1] == {"category": "Dining", "total": 15}
    assert result[2] == {"category": "Uncategorised", "total": 2}
