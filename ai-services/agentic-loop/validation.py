import asyncio
import os
import socket
import subprocess
import sys
import json
import time
from urllib.parse import urlparse

import requests

EXPECTED_TOOLS = {
    "get_expenses", "get_categories", "get_bills", "get_bills_summary",
    "get_income_sources", "get_pay_schedules", "get_savings_goals", "get_budgets",
    "get_budget_overview"
}


def _host_port(url):
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 80


def _port_open(url):
    host, port = _host_port(url)
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _start_local_mcp(repo_root, url):
    """Start the existing MCP server locally when it is not already listening."""
    if _port_open(url):
        return None, False

    server_dir = repo_root / "ai-services" / "mcp-server"
    server_file = server_dir / "server.py"
    if not server_file.is_file():
        return None, False

    env = os.environ.copy()
    env["PORT"] = str(_host_port(url)[1])
    try:
        process = subprocess.Popen(
            [sys.executable, str(server_file)],
            cwd=str(server_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError:
        return None, False

    deadline = time.time() + 12
    while time.time() < deadline:
        if _port_open(url):
            return process, True
        if process.poll() is not None:
            return process, True
        time.sleep(0.25)
    return process, True


def decode_mcp_result(result):
    """Check protocol AND downstream errors; don't truncate before parsing."""
    if getattr(result, 'is_error', getattr(result, 'isError', False)):
        raise ValueError('MCP tool reported a protocol error')
    payload = getattr(result, 'structured_content', getattr(result, 'structuredContent', None))
    if payload is None:
        blocks = [block.text for block in result.content if hasattr(block, 'text')]
        if result.content and not blocks:
            raise ValueError('MCP tool returned no readable data')
        decoded = [json.loads(text) for text in blocks]
        payload = decoded[0] if len(decoded) == 1 else decoded
    if not isinstance(payload, (dict, list)):
        raise ValueError('MCP tool returned an invalid data shape')
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if isinstance(item, dict) and 'error' in item:
            raise ValueError(str(item['error']))
    return payload


def mcp_passed(data):
    return bool(
        data.get('connected') and not data.get('errors')
        and len(data.get('tools', [])) == len(EXPECTED_TOOLS)
        and set(data.get('tools', [])) == EXPECTED_TOOLS
        and {call['tool'] for call in data.get('calls', [])} == EXPECTED_TOOLS
        and all(call.get('passed') for call in data.get('calls', []))
    )


async def validate_mcp(url=None, user_id=None, repo_root=None):
    url = url or os.environ.get('MCP_SERVER_URL', 'http://localhost:5100/mcp')
    user_id = user_id if user_id is not None else int(os.environ.get('VALIDATION_USER_ID', '1'))
    out = {'connected': False, 'auto_started': False, 'tools': [], 'calls': [],
           'errors': [], 'passed': False}
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        out['errors'].append('MCP SDK unavailable: ' + str(exc))
        return out

    process = None
    try:
        if repo_root is not None:
            process, out['auto_started'] = _start_local_mcp(repo_root, url)
        async with streamable_http_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                info = await session.initialize()
                out['connected'] = True
                out['server'] = getattr(getattr(info, 'server_info', None), 'name', 'unknown')
                listed = await session.list_tools()
                out['tools'] = [tool.name for tool in listed.tools]
                out['missing_tools'] = sorted(EXPECTED_TOOLS - set(out['tools']))
                out['unexpected_tools'] = sorted(set(out['tools']) - EXPECTED_TOOLS)
                for name in sorted(EXPECTED_TOOLS & set(out['tools'])):
                    try:
                        result = await session.call_tool(name, {'user_id': user_id})
                        payload = decode_mcp_result(result)
                        out['calls'].append({'tool': name, 'passed': True, 'response': payload})
                    except Exception as exc:
                        out['calls'].append({'tool': name, 'passed': False,
                                             'error': f'{type(exc).__name__}: {exc}'})
    except Exception as exc:
        out['errors'].append(f'MCP session failed at {url}: {type(exc).__name__}: {exc}')
    finally:
        if process is not None and out['auto_started'] and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    out['passed'] = mcp_passed(out)
    return out


RAG_QUERIES = (
    'how do I set a budget',
    'what does an overdue bill mean',
    'how do I add an expense',
    'What is a pay schedule?',
    'how do I create a savings goal',
)


def valid_retrieval(body):
    if not isinstance(body, dict) or body.get('status') != 'success':
        return False
    results = body.get('results')
    return bool(isinstance(results, list) and results and all(
        isinstance(item, dict)
        and isinstance(item.get('source_id'), str) and item['source_id'].strip()
        and isinstance(item.get('text'), str) and item['text'].strip()
        and isinstance(item.get('distance'), (float, int)) and 0 <= item['distance'] < 1
        for item in results
    ))


def valid_answer(body, insufficient=False, source_ids=None):
    if not isinstance(body, dict) or 'error' in body:
        return False
    if not isinstance(body.get('answer'), str) or not body['answer'].strip():
        return False
    citations = body.get('citations')
    if not isinstance(citations, list):
        return False
    if insufficient:
        return body.get('confidence_category') == 'insufficient' and citations == []
    return bool(
        isinstance(body.get('confidence_category'), str)
        and body['confidence_category'] in {'high', 'medium', 'low'} and citations
        and all(isinstance(source, str) and source.strip() for source in citations)
        and (source_ids is None or set(citations) <= source_ids)
    )


def validate_rag(url=None):
    base = (url or os.environ.get('RAG_SERVER_URL', 'http://localhost:5101')).rstrip('/')
    out = {'health': None, 'refresh': None, 'retrieval': [], 'generation': None,
           'insufficient': None, 'errors': [], 'passed': False}

    def request_json(method, path, **kwargs):
        response = getattr(requests, method)(base + path, **kwargs)
        response.raise_for_status()
        return response.json()

    try:
        out['health'] = request_json('get', '/health', timeout=10)
        h = out['health']
        if not (isinstance(h, dict) and h.get('service') == 'rag-server'
                and h.get('status') == 'ok' and h.get('corpus_loaded') is True
                and isinstance(h.get('chunk_count'), int) and h['chunk_count'] > 0):
            raise ValueError('Corpus is not loaded or health is invalid')
    except (requests.RequestException, ValueError) as exc:
        out['errors'].append(f'health: {exc}')
        return out

    try:
        out['refresh'] = request_json('post', '/refresh_corpus', timeout=20)
        refresh = out['refresh']
        if not (isinstance(refresh, dict) and refresh.get('status') == 'success'
                and isinstance(refresh.get('chunk_count'), int) and refresh['chunk_count'] > 0):
            raise ValueError('Corpus refresh did not load chunks')
    except (requests.RequestException, ValueError) as exc:
        out['errors'].append(f'refresh_corpus: {exc}')

    income_sources = set()
    for query in RAG_QUERIES:
        try:
            body = request_json('post', '/retrieve_context', json={'query': query, 'k': 3}, timeout=20)
            ok = valid_retrieval(body)
            out['retrieval'].append({'query': query, 'passed': ok,
                                     'results': body.get('results', []) if isinstance(body, dict) else []})
            if not ok:
                out['errors'].append(f'retrieve_context: no valid context for {query}')
            elif query == 'What is a pay schedule?':
                income_sources = {item['source_id'] for item in body['results']}
        except (requests.RequestException, ValueError) as exc:
            out['retrieval'].append({'query': query, 'passed': False, 'error': str(exc)})
            out['errors'].append(f'retrieve_context: {exc}')

    for key, query in [('generation', 'What is a pay schedule?'),
                       ('insufficient', 'Quantum chromodynamics')]:
        try:
            out[key] = request_json('post', '/answer_question', json={'query': query, 'k': 3}, timeout=120)
            if not valid_answer(out[key], insufficient=(key == 'insufficient'),
                                source_ids=income_sources if key == 'generation' else None):
                out['errors'].append(f'{key}: invalid answer, citations or confidence')
        except (requests.RequestException, ValueError) as exc:
            out['errors'].append(f'{key}: {exc}')
    out['passed'] = not out['errors']
    return out


def print_validation(mode, data):
    print('\n' + '=' * 70 + '\n' + mode.upper() + ' VALIDATION\n' + '=' * 70)
    if mode == 'mcp':
        print('[{}] MCP connection'.format('PASS' if data.get('connected') else 'FAIL'))
        print('[{}] Tool discovery: {}/{}'.format(
            'PASS' if set(data.get('tools', [])) == EXPECTED_TOOLS
            and len(data.get('tools', [])) == len(EXPECTED_TOOLS) else 'FAIL',
            len(data.get('tools', [])), len(EXPECTED_TOOLS)))
        for key in ('missing_tools', 'unexpected_tools'):
            if data.get(key):
                print('[FAIL] ' + key + ': ' + ', '.join(data[key]))
        for call in data.get('calls', []):
            print('[{}] {}'.format('PASS' if call.get('passed') else 'FAIL', call['tool']))
            # Print only shape/counts, not personal financial records.
            payload = call.get('response')
            if isinstance(payload, dict):
                print('  JSON keys: ' + ', '.join(payload))
            elif isinstance(payload, list):
                print(f'  JSON array: {len(payload)} item(s)')
            if call.get('error'):
                print('  ' + call['error'])
    else:
        for key in ('health', 'refresh', 'generation', 'insufficient'):
            print(f'{key}: ' + json.dumps(data.get(key), ensure_ascii=False))
        for item in data.get('retrieval', []):
            print('[{}] Retrieval: {} ({} chunks)'.format(
                'PASS' if item.get('passed') else 'FAIL', item['query'], len(item.get('results', []))))
    for error in data.get('errors', []):
        print('[FAIL] ' + error)
    passed = bool(data.get('passed'))
    print('[{}] {} overall'.format('PASS' if passed else 'FAIL', mode.upper()))
    return passed
