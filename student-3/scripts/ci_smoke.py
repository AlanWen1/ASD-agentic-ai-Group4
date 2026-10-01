"""Real HTTP integration for an isolated CI stack with AI/MCP/RAG disabled.

Creates disposable users/records and cleans them up. Never prints credentials.
Uses Compose ports by default; URL variables allow a native verification stack.
"""
import os
import secrets
import time

import requests

AUTH_URL = os.getenv('SMOKE_AUTH_URL', 'http://localhost:6000').rstrip('/')
DB_URL = os.getenv('SMOKE_DATABASE_URL', 'http://localhost:6003').rstrip('/')
BACKEND_URL = os.getenv('SMOKE_BACKEND_URL', 'http://localhost:5003').rstrip('/')
FRONTEND_URL = os.getenv('SMOKE_FRONTEND_URL', 'http://localhost:3003').rstrip('/')


def call(method, url, expected=200, **kwargs):
    response = requests.request(method, url, timeout=10, **kwargs)
    assert response.status_code == expected, f'{method} {url.split("?")[0]}: expected {expected}, got {response.status_code}'
    return response.json() if response.content else None


def wait_healthy(url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = requests.get(url + '/health', timeout=3)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        time.sleep(1)
    raise AssertionError('Service did not become healthy: ' + url)


def main():
    for url in (AUTH_URL, DB_URL, FRONTEND_URL):
        wait_healthy(url)
    health = wait_healthy(BACKEND_URL)
    assert health['modes'] == {'ai': False, 'mcp': False, 'rag': False}, 'This script requires an isolated stack with all three modes disabled'
    page = requests.get(FRONTEND_URL, timeout=10)
    assert page.status_code == 200
    assert all(marker in page.text for marker in ('mcpIncomeButton', 'mcpScheduleButton', 'ragForm'))
    print('[PASS] Services healthy; UI includes MCP/RAG controls; all AI modes disabled')

    users, credentials = [], []
    source_id = schedule_id = None
    try:
        for _ in range(2):
            username = 'r1_smoke_' + secrets.token_hex(8)
            password = secrets.token_urlsafe(24)
            user = call('POST', AUTH_URL + '/users', expected=201,
                        json={'username': username, 'email': username + '@example.test', 'password': password})
            users.append(user['id'])
            login = call('POST', AUTH_URL + '/auth/login', json={'identifier': username, 'password': password})
            credentials.append({'Authorization': 'Bearer ' + login['token']})
        owner, other = credentials
        call('GET', FRONTEND_URL + '/api/income-sources', expected=401)
        source = call('POST', FRONTEND_URL + '/api/income-sources', expected=201, headers=owner,
                      json={'source_name': 'Release 1 CI income', 'income_type': 'Freelance',
                            'standard_amount': 1250.50, 'payment_frequency': 'monthly', 'active': True})
        source_id = source['id']
        assert source['user_id'] == users[0]
        call('GET', FRONTEND_URL + f'/api/income-sources/{source_id}', expected=404, headers=other)
        listed = call('GET', FRONTEND_URL + '/api/income-sources', headers=other)
        assert all(item['id'] != source_id for item in listed['items'])
        updated = call('PUT', FRONTEND_URL + f'/api/income-sources/{source_id}', headers=owner,
                       json={'source_name': 'Updated CI income'})
        assert updated['source_name'] == 'Updated CI income'
        schedule = call('POST', FRONTEND_URL + '/api/pay-schedules', expected=201, headers=owner,
                        json={'income_source_id': source_id, 'expected_pay_date': '2099-01-15',
                              'expected_amount': 1250.50, 'status': 'scheduled'})
        schedule_id = schedule['id']
        call('GET', FRONTEND_URL + f'/api/pay-schedules/{schedule_id}', expected=404, headers=other)
        call('DELETE', FRONTEND_URL + f'/api/income-sources/{source_id}', expected=409, headers=owner)
        before = call('GET', FRONTEND_URL + '/api/dashboard?month=2099-01', headers=owner)['summary']
        assert before['expected_total'] == 1250.50 and before['outstanding_total'] == 1250.50
        call('PUT', FRONTEND_URL + f'/api/pay-schedules/{schedule_id}', headers=owner,
             json={'status': 'received', 'received_date': '2099-01-15', 'actual_amount': 1200})
        after = call('GET', FRONTEND_URL + '/api/dashboard?month=2099-01', headers=owner)['summary']
        assert after['received_total'] == 1200 and after['variance'] == -50.50 and after['outstanding_total'] == 0
        print('[PASS] Authenticated frontend → backend → database CRUD, isolation and money totals')
        for method, route, mode in [('GET', '/api/ai/status', 'AI'), ('POST', '/api/ai/analyse', 'AI'),
                                    ('POST', '/api/ai/chat', 'AI'), ('POST', '/api/mcp/query', 'MCP'),
                                    ('POST', '/api/rag/ask', 'RAG')]:
            body = call(method, FRONTEND_URL + route, expected=503, headers=owner,
                        json={'message': 'pay', 'tool': 'get_income_sources'})
            assert body['code'] == mode + '_DISABLED'
        print('[PASS] Disabled AI/MCP/RAG endpoints through the frontend proxy')
    finally:
        if credentials:
            if schedule_id is not None:
                call('DELETE', FRONTEND_URL + f'/api/pay-schedules/{schedule_id}', expected=204, headers=credentials[0])
            if source_id is not None:
                call('DELETE', FRONTEND_URL + f'/api/income-sources/{source_id}', expected=204, headers=credentials[0])
        for user_id in users:
            call('DELETE', AUTH_URL + f'/users/{user_id}')
    print('[PASS] Disposable test records removed')


if __name__ == '__main__':
    main()
