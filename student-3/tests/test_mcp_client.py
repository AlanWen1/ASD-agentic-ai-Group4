"""Exercise actual SDK result types without a running MCP server."""
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

from mcp.types import CallToolResult, TextContent

spec = importlib.util.spec_from_file_location('release1_mcp_client', Path(__file__).parents[1] / 'backend/mcp_client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

def invoke(monkeypatch, result):
    call = AsyncMock(return_value=result)
    monkeypatch.setattr(client, '_call_tool_async', call)
    actual = client.call_mcp_tool('get_income_sources', user_id=7)
    call.assert_awaited_once_with('get_income_sources', {'user_id': 7})
    return actual

def test_structured_sdk_result(monkeypatch):
    result = CallToolResult(content=[TextContent(type='text', text='ignored')],
                            structured_content={'items': [], 'count': 0})
    assert invoke(monkeypatch, result) == {'items': [], 'count': 0}

def test_sdk_protocol_error(monkeypatch):
    result = CallToolResult(content=[TextContent(type='text', text='denied')], is_error=True)
    assert invoke(monkeypatch, result) == {'error': 'denied'}

def test_all_text_blocks_are_preserved(monkeypatch):
    result = CallToolResult(content=[TextContent(type='text', text='{"id":1}'),
                                   TextContent(type='text', text='{"id":2}')])
    assert invoke(monkeypatch, result) == [{'id': 1}, {'id': 2}]

def test_malformed_result(monkeypatch):
    assert 'error' in invoke(monkeypatch, CallToolResult(content=[TextContent(type='text', text='bad JSON')]))

def test_empty_result(monkeypatch):
    assert invoke(monkeypatch, CallToolResult(content=[])) == []
