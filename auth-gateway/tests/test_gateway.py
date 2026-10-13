import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.app import Settings, create_app
from gateway.store import login_hash

SECRET = 'test-secret'


class FakeBackends(httpx.AsyncBaseTransport):
    """Два BPM: у обоих есть логин ivanov, пароли разные."""

    passwords = {
        'https://mega.test': {'ivanov': 'mega-pass'},
        'https://park.test': {'ivanov': 'park-pass', 'petrov': 'p1'},
    }

    async def handle_async_request(self, request):
        import json

        base = f'{request.url.scheme}://{request.url.host}'
        body = json.loads(request.content)
        if self.passwords.get(base, {}).get(body['username']) == body['password']:
            return httpx.Response(200, json={'access': f'a-{base}', 'refresh': 'r'})
        return httpx.Response(401, json={'detail': 'No active account'})


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv('GATEWAY_DB_PATH', str(tmp_path / 'g.sqlite3'))
    monkeypatch.setenv('LOGIN_HASH_SECRET', SECRET)
    monkeypatch.setenv('LOGIN_MAX_ATTEMPTS', '5')
    app = create_app(Settings(), transport=FakeBackends())
    client = TestClient(app)
    keys = {
        'mega': app.state.store.add_backend('Мега', 'https://mega.test'),
        'park': app.state.store.add_backend('Парк', 'https://park.test'),
    }
    push = lambda key, logins: client.put(
        '/api/backend/logins', headers={'Authorization': f'Bearer {key}'},
        json={'logins': [login_hash(SECRET, login) for login in logins]},
    )
    assert push(keys['mega'], ['Ivanov']).json()['logins'] == 1
    assert push(keys['park'], ['ivanov', 'petrov']).status_code == 200
    return client, keys, push


def test_login_routes_to_right_backend(gateway):
    client, _keys, _push = gateway
    response = client.post('/api/login', json={'username': 'petrov', 'password': 'p1'})
    assert response.status_code == 200
    assert response.json()['base_url'] == 'https://park.test'


def test_same_login_resolved_by_password(gateway):
    client, _keys, _push = gateway
    assert client.post('/api/login', json={'username': ' ivanov ', 'password': 'mega-pass'}).json()['base_url'] == 'https://mega.test'
    assert client.post('/api/login', json={'username': 'ivanov', 'password': 'park-pass'}).json()['base_url'] == 'https://park.test'


def test_unknown_and_wrong_password_look_the_same(gateway):
    client, _keys, _push = gateway
    unknown = client.post('/api/login', json={'username': 'nobody', 'password': 'x'})
    wrong = client.post('/api/login', json={'username': 'petrov', 'password': 'x'})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_push_requires_key_and_replaces(gateway):
    client, keys, push = gateway
    assert client.put('/api/backend/logins', json={'logins': []}).status_code == 401
    push(keys['park'], ['ivanov'])
    assert client.post('/api/login', json={'username': 'petrov', 'password': 'p1'}).status_code == 401


def test_rate_limit(gateway):
    client, _keys, _push = gateway
    codes = [client.post('/api/login', json={'username': 'petrov', 'password': 'bad'}).status_code for _ in range(6)]
    assert codes[-1] == 429
