"""Release 1 HTTP contracts; enabled-mode dependencies are mocked, never called live."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

backend = load('release1_backend', ROOT / 'backend/app.py')
frontend = load('release1_frontend', ROOT / 'frontend/app.py')
AUTH = {'Authorization': 'Bearer valid-token'}
ANSWER = {'answer': 'A pay schedule records expected payments.',
          'citations': ['faq-pay-schedule'], 'confidence_category': 'medium',
          'retrieval_summary': 'one relevant chunk'}

class Reply:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

@pytest.fixture
def client(monkeypatch):
    def auth(method, url, **kwargs):
        assert method == 'GET' and '/sessions/' in url
        return Reply({'user': {'id': 7}}, 200) if url.endswith('/valid-token') else Reply({}, 401)
    monkeypatch.setattr(backend.requests, 'request', auth)
    app = backend.create_app('http://database.test', 'http://auth.test')
    app.config.update(TESTING=True, AI_ENABLED=True, MCP_ENABLED=True,
                      RAG_ENABLED=True, RAG_SERVER_URL='http://rag.test', RAG_TIMEOUT_SECONDS=75)
    return app.test_client()

def mcp_stub(monkeypatch, result):
    call = Mock(return_value=result)
    monkeypatch.setitem(sys.modules, 'mcp_client', SimpleNamespace(call_mcp_tool=call))
    return call

@pytest.mark.parametrize('route', ['/api/mcp/query', '/api/rag/ask'])
@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer expired'}])
def test_authentication_precedes_shared_services(client, monkeypatch, route, headers):
    call = mcp_stub(monkeypatch, {})
    post = Mock(side_effect=AssertionError('RAG must not be contacted'))
    monkeypatch.setattr(backend.requests, 'post', post)
    assert client.post(route, json={'tool': 'get_income_sources', 'message': 'pay'}, headers=headers).status_code == 401
    call.assert_not_called()
    post.assert_not_called()

@pytest.mark.parametrize('tool', ['get_income_sources', 'get_pay_schedules'])
def test_mcp_only_uses_authenticated_owner(client, monkeypatch, tool):
    call = mcp_stub(monkeypatch, {'items': [], 'count': 0})
    response = client.post('/api/mcp/query', json={'tool': tool, 'user_id': 999,
                           'arguments': {'user_id': 999}}, headers=AUTH)
    assert response.status_code == 200
    assert response.json == {'tool': tool, 'result': {'items': [], 'count': 0}}
    call.assert_called_once_with(tool, user_id=7)

@pytest.mark.parametrize('body', [{'tool': 'get_bills'}, {'tool': 'delete_income_source'},
                                  {'tool': []}, {}, ['get_income_sources']])
def test_mcp_rejects_other_tools_and_bad_bodies(client, monkeypatch, body):
    call = mcp_stub(monkeypatch, {})
    assert client.post('/api/mcp/query', json=body, headers=AUTH).status_code == 400
    call.assert_not_called()

def test_mcp_dependency_error_is_not_success(client, monkeypatch):
    mcp_stub(monkeypatch, {'error': 'Database unreachable'})
    response = client.post('/api/mcp/query', json={'tool': 'get_income_sources'}, headers=AUTH)
    assert response.status_code == 502
    assert response.json['result']['error'] == 'Database unreachable'

@pytest.mark.parametrize('payload', [ANSWER, {'answer': 'Insufficient context', 'citations': [],
                                             'confidence_category': 'insufficient'}])
def test_rag_preserves_answer_contract_and_metadata(client, monkeypatch, payload):
    post = Mock(return_value=Reply(payload))
    monkeypatch.setattr(backend.requests, 'post', post)
    response = client.post('/api/rag/ask', json={'message': '  What is a pay schedule?  '}, headers=AUTH)
    assert response.status_code == 200 and response.json == payload
    post.assert_called_once_with('http://rag.test/answer_question',
                                 json={'query': 'What is a pay schedule?'}, timeout=75)

@pytest.mark.parametrize('body', [{}, {'message': None}, {'message': []}, {'message': '  '},
                                  {'message': 'x' * 2001}, ['pay']])
def test_rag_validates_input_before_forwarding(client, monkeypatch, body):
    post = Mock()
    monkeypatch.setattr(backend.requests, 'post', post)
    assert client.post('/api/rag/ask', json=body, headers=AUTH).status_code == 400
    post.assert_not_called()

@pytest.mark.parametrize('error,status', [(requests.Timeout('slow'), 504),
                                         (requests.ConnectionError('offline'), 502)])
def test_rag_dependency_failure(client, monkeypatch, error, status):
    monkeypatch.setattr(backend.requests, 'post', Mock(side_effect=error))
    response = client.post('/api/rag/ask', json={'message': 'pay'}, headers=AUTH)
    assert response.status_code == status
    if status == 504:
        assert response.json['code'] == 'RAG_TIMEOUT'

@pytest.mark.parametrize('payload,status', [(ValueError('not JSON'), 200), ([], 200),
    ({'error': 'AI offline'}, 400), ({**ANSWER, 'citations': []}, 200),
    ({**ANSWER, 'confidence_category': 'unknown'}, 200), ({**ANSWER, 'answer': ''}, 200),
    ({**ANSWER, 'citations': [12]}, 200), ({**ANSWER, 'confidence_category': 'insufficient'}, 200)])
def test_rag_rejects_invalid_upstream_contract(client, monkeypatch, payload, status):
    monkeypatch.setattr(backend.requests, 'post', Mock(return_value=Reply(payload, status)))
    assert client.post('/api/rag/ask', json={'message': 'pay'}, headers=AUTH).status_code == 502

@pytest.mark.parametrize('mode,method,route', [('AI', 'get', '/api/ai/status'),
    ('AI', 'post', '/api/ai/analyse'), ('AI', 'post', '/api/ai/chat'),
    ('MCP', 'post', '/api/mcp/query'), ('RAG', 'post', '/api/rag/ask')])
def test_disabled_modes_cannot_call_shared_services(client, monkeypatch, mode, method, route):
    client.application.config[f'{mode}_ENABLED'] = False
    call = mcp_stub(monkeypatch, {})
    forbidden = Mock(side_effect=AssertionError('Disabled service contacted'))
    for name in ['ask_ollama', 'check_ollama', 'run_agent_loop']:
        monkeypatch.setattr(backend, name, forbidden)
    monkeypatch.setattr(backend.requests, 'post', forbidden)
    response = getattr(client, method)(route, headers=AUTH)
    assert response.status_code == 503 and response.json['code'] == f'{mode}_DISABLED'
    call.assert_not_called()
    forbidden.assert_not_called()

def test_environment_switches(monkeypatch):
    for mode in ['AI', 'MCP', 'RAG']:
        monkeypatch.setenv(f'{mode}_ENABLED', 'false')
    app = backend.create_app()
    assert all(app.config[f'{mode}_ENABLED'] is False for mode in ['AI', 'MCP', 'RAG'])

@pytest.mark.parametrize('route,payload,status', [('mcp/query', {'result': {'items': []}}, 200),
    ('rag/ask', ANSWER, 200), ('rag/ask', {'error': 'slow', 'code': 'RAG_TIMEOUT'}, 504)])
def test_frontend_proxy_preserves_auth_body_and_status(monkeypatch, route, payload, status):
    content = json.dumps(payload).encode()
    upstream = SimpleNamespace(content=content, status_code=status, headers={'Content-Type': 'application/json'})
    call = Mock(return_value=upstream)
    monkeypatch.setattr(frontend.requests, 'request', call)
    app = frontend.create_app('http://backend.test')
    body = {'message': 'pay', 'tool': 'get_income_sources'}
    response = app.test_client().post('/api/' + route, json=body, headers=AUTH)
    assert response.status_code == status and response.json == payload
    args, kwargs = call.call_args
    assert args == ('POST', 'http://backend.test/api/' + route)
    assert kwargs['headers']['Authorization'] == AUTH['Authorization']
    assert json.loads(kwargs['data']) == body
