import json
import os
import requests

DATABASE_URL = os.environ.get(
    "DATABASE_API_URL",
    "http://savings-database:6005"
).rstrip("/")

OLLAMA_API_URL = os.environ.get(
    "OLLAMA_API_URL",
    "http://host.docker.internal:11434/api/generate"
)

OLLAMA_URL = OLLAMA_API_URL.replace("/api/generate", "").rstrip("/")

AGENT_MODEL = os.environ.get(
    "AGENT_MODEL",
    "qwen2.5:7b"
)

HTTP_TIMEOUT = 20

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_savings_goals",
            "description": (
                "Get all savings goals. Use this tool when the user asks "
                "about their savings goals, compares goals, asks which goal "
                "needs the most money, or asks about overall savings progress."
            ),
            "parameters": {
                "type": "object",
                "properties": {}
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_savings_goal",
            "description": (
                "Get one savings goal by its goal ID. Use this tool when the "
                "user asks about one specific savings goal and its ID is known."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {
                        "type": "integer",
                        "description": "The ID of the savings goal."
                    }
                },
                "required": ["goal_id"],
            },
        },
    },
]

SYSTEM_PROMPT = """
You are a savings goal assistant inside a personal finance application.

You have tools that retrieve the user's real savings goal data.

IMPORTANT:
- If the user asks a question that depends on their savings goal data,
  you MUST use the appropriate tool before answering.
- Do not ask the user for a goal ID if the answer can be found by first
  retrieving all savings goals.
- Never invent goal names, IDs, target amounts, current amounts, dates,
  remaining amounts, or progress.
- After receiving tool results, analyse the real data and answer the
  user's question.
- Keep answers short and practical.

Examples:
- "Which savings goal needs the most money?" -> call get_savings_goals.
- "Which goal is closest to completion?" -> call get_savings_goals.
- "How much have I saved in total?" -> call get_savings_goals.
- "Tell me about goal 3" -> call get_savings_goal with goal_id 3.
"""


def get_savings_goals():
    response = requests.get(
        f"{DATABASE_URL}/goals",
        timeout=HTTP_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def get_savings_goal(goal_id):
    response = requests.get(
        f"{DATABASE_URL}/goals/{goal_id}",
        timeout=HTTP_TIMEOUT
    )

    if response.status_code == 404:
        return {
            "error": "Savings goal not found."
        }

    response.raise_for_status()
    return response.json()


def _call_tool(name, args):
    if name == "get_savings_goals":
        return get_savings_goals()

    if name == "get_savings_goal":
        return get_savings_goal(args.get("goal_id"))

    return {
        "error": f"Unknown tool: {name}"
    }


def run_agent_loop(user_message, max_steps=4):
    """
    Plan -> Act -> Observe -> Adapt agentic loop.
    """

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    trace = []

    for step in range(max_steps):
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": AGENT_MODEL,
                "messages": messages,
                "tools": TOOLS,
                "stream": False
            },
            timeout=60
        )

        response.raise_for_status()

        data = response.json()
        message = data["message"]

        messages.append(message)

        tool_calls = message.get("tool_calls")

        if not tool_calls:
            trace.append({
                "step": step,
                "phase": "Adapt",
                "type": "final_answer"
            })

            return {
                "answer": message.get("content", ""),
                "trace": trace
            }

        trace.append({
            "step": step,
            "phase": "Plan",
            "type": "tool_selection"
        })

        for call in tool_calls:
            function_name = call["function"]["name"]
            function_args = call["function"].get(
                "arguments",
                {}
            )

            if isinstance(function_args, str):
                function_args = json.loads(function_args)

            trace.append({
                "step": step,
                "phase": "Act",
                "type": "tool_call",
                "tool": function_name,
                "args": function_args
            })

            result = _call_tool(
                function_name,
                function_args
            )

            trace.append({
                "step": step,
                "phase": "Observe",
                "type": "tool_result",
                "tool": function_name
            })

            messages.append({
                "role": "tool",
                "content": json.dumps(result)
            })

    return {
        "answer": (
            "I wasn't able to complete the savings goal analysis "
            "within the allowed number of steps."
        ),
        "trace": trace
    }