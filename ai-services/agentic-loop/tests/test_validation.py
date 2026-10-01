import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import validation
import agent_review


def test_expected_tools_match_actual_server_registration():
    tree = ast.parse((ROOT.parent / 'mcp-server/server.py').read_text(encoding="utf-8"))
    tools = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'AVAILABLE_TOOLS' for target in node.targets))
    assert validation.EXPECTED_TOOLS == set(tools)
    assert len(tools) == 9

@pytest.mark.parametrize('result', [SimpleNamespace(is_error=True, content=[]),
    SimpleNamespace(is_error=False, structured_content={'error': 'DB offline'}, content=[]),
    SimpleNamespace(is_error=False, content=[SimpleNamespace(text='not JSON')])])
def test_mcp_protocol_and_downstream_failures(result):
    with pytest.raises(ValueError):
        validation.decode_mcp_result(result)

def test_mcp_large_response_is_parsed_completely():
    import json
    payload = {'items': [{'source_name': 'x' * 1500}]}
    result = SimpleNamespace(is_error=False, content=[SimpleNamespace(text=json.dumps(payload))])
    assert validation.decode_mcp_result(result) == payload

def test_mcp_missing_or_failed_call_fails_overall():
    data = {'connected': True, 'tools': list(validation.EXPECTED_TOOLS), 'errors': [],
            'calls': [{'tool': name, 'passed': True} for name in validation.EXPECTED_TOOLS]}
    assert validation.mcp_passed(data)
    data['calls'][0]['passed'] = False
    assert not validation.mcp_passed(data)
    data['calls'] = data['calls'][1:]
    assert not validation.mcp_passed(data)

class Reply:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
    def json(self):
        return self.body
    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError('Upstream failed')

@pytest.fixture
def rag(monkeypatch):
    state = {'empty': False, 'bad_citations': False, 'generation_status': 200, 'bad_fallback': False}
    monkeypatch.setattr(validation.requests, 'get', lambda *a, **k: Reply(
        {'status': 'ok', 'service': 'rag-server', 'corpus_loaded': True, 'chunk_count': 24}))
    def post(url, **kwargs):
        if url.endswith('/refresh_corpus'):
            return Reply({'status': 'success', 'chunk_count': 24})
        if url.endswith('/retrieve_context'):
            return Reply({'status': 'success', 'results': [] if state['empty'] else
                          [{'source_id': 'income-faq', 'text': 'Pay schedule knowledge', 'distance': 0.2}]})
        if kwargs['json']['query'] == 'Quantum chromodynamics':
            return Reply({'answer': 'Insufficient context', 'citations': ['wrong'] if state['bad_fallback'] else [],
                          'confidence_category': 'insufficient'})
        return Reply({'answer': 'Expected pay dates', 'citations': ['invented'] if state['bad_citations'] else ['income-faq'],
                      'confidence_category': 'medium'}, state['generation_status'])
    monkeypatch.setattr(validation.requests, 'post', post)
    return state

def test_rag_success_covers_five_features_and_fallback(rag):
    result = validation.validate_rag('http://rag.test')
    assert result['passed'] and len(result['retrieval']) == 5
    assert result['insufficient']['citations'] == []

@pytest.mark.parametrize('key,value', [('empty', True), ('bad_citations', True),
                                      ('generation_status', 500), ('bad_fallback', True)])
def test_rag_failure_is_reported(rag, key, value):
    rag[key] = value
    result = validation.validate_rag('http://rag.test')
    assert not result['passed'] and result['errors']

@pytest.mark.parametrize('body', [{}, {'answer': '', 'citations': ['s'], 'confidence_category': 'high'},
    {'answer': 'ok', 'citations': [], 'confidence_category': 'high'},
    {'answer': 'ok', 'citations': ['s'], 'confidence_category': 'unknown'},
    {'answer': 'ok', 'citations': ['s'], 'confidence_category': []}])
def test_answer_field_presence_alone_does_not_pass(body):
    assert not validation.valid_answer(body)

def test_print_returns_actual_validation_status(capsys):
    assert not validation.print_validation('mcp', {'passed': False})
    assert '[FAIL] MCP overall' in capsys.readouterr().out

@pytest.mark.parametrize('passed,code', [(True, 0), (False, 1)])
def test_review_mode_returns_nonzero_on_validation_failure(monkeypatch, passed, code):
    monkeypatch.setattr(agent_review, 'validate_rag', lambda: {'passed': passed})
    assert agent_review.review_mode(ROOT, 'rag', 'unused', 'unused', 1) == code

def test_cli_propagates_failure(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['agent_review.py', '--mode', 'rag'])
    monkeypatch.setattr(agent_review, 'health', lambda *a: (True, []))
    monkeypatch.setattr(agent_review, 'review_mode', lambda *a: 1)
    assert agent_review.main() == 1
