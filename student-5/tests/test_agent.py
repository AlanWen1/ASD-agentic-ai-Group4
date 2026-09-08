import os
import sys
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
sys.path.insert(0, BACKEND_DIR)

import agent


def _ollama_message(content=None, tool_calls=None):
    return MagicMock(
        raise_for_status=lambda: None,
        json=lambda: {
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
        },
    )


@patch("agent.requests.get")
@patch("agent.requests.post")
def test_agent_loop_calls_tool_then_answers(mock_post, mock_get):
    mock_post.side_effect = [
        _ollama_message(
            tool_calls=[
                {
                    "function": {
                        "name": "get_savings_goals",
                        "arguments": {},
                    }
                }
            ]
        ),
        _ollama_message(
            content="The Home Deposit goal needs the most money."
        ),
    ]

    mock_get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [
            {
                "goal_id": 1,
                "goal_name": "Emergency Fund",
                "target_amount": 10000,
                "current_amount": 4000,
                "target_date": "2027-12-31",
            },
            {
                "goal_id": 2,
                "goal_name": "Home Deposit",
                "target_amount": 50000,
                "current_amount": 12000,
                "target_date": "2030-12-31",
            },
        ],
    )

    result = agent.run_agent_loop(
        "Which savings goal needs the most money?"
    )

    assert result["answer"] == (
        "The Home Deposit goal needs the most money."
    )

    phases = [item["phase"] for item in result["trace"]]

    assert "Plan" in phases
    assert "Act" in phases
    assert "Observe" in phases
    assert "Adapt" in phases

    assert mock_post.call_count == 2
    mock_get.assert_called()