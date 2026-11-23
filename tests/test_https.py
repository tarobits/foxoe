"""Real TLS/HTTP listener isolation with a temporary, test-only certificate."""
import asyncio
import socket
import ssl
import subprocess

import httpx
import pytest
import uvicorn

from foxoe.__main__ import SharedLoopServer
from foxoe.server import create_app


def test_https_registration_listener_isolated_and_shutdown_cleans_up(tmp_path):
    cert = tmp_path / 'test-cert.pem'
    key = tmp_path / 'test-key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)

    async def scenario():
        app = create_app(tmp_path / 'data', hardware=False)
        sockets = []
        for _ in range(2):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            sockets.append(sock)
        local_port, tls_port = [sock.getsockname()[1] for sock in sockets]
        local = SharedLoopServer(uvicorn.Config(app, log_level='error', access_log=False))
        remote = SharedLoopServer(uvicorn.Config(app.state.registration, ssl_certfile=str(cert), ssl_keyfile=str(key), log_level='error', access_log=False))
        tasks = [asyncio.create_task(server.serve(sockets=[sock])) for server, sock in zip((local, remote), sockets)]
        try:
            async with asyncio.timeout(10):
                while not (local.started and remote.started):
                    await asyncio.sleep(.02)
            context = ssl.create_default_context(cafile=str(cert))
            async with httpx.AsyncClient(verify=context, trust_env=False) as client:
                base = f'https://127.0.0.1:{tls_port}'
                assert (await client.get(base + '/api/config')).status_code == 404
                assert (await client.post(base + '/v1/apps', json={})).status_code == 401
                result = await client.post(base + '/v1/apps', headers={'Authorization': 'Bearer ' + app.state.store.registration_token},
                    json={'id': 'registered', 'name': 'Registered', 'url': 'https://example.test/app'})
                assert result.status_code == 201
                response = await client.get(f'http://127.0.0.1:{local_port}/api/config')
                assert any(item['id'] == 'registered' for item in response.json()['apps'])
            async with httpx.AsyncClient(trust_env=False) as untrusted:
                with pytest.raises(httpx.ConnectError):
                    await untrusted.get(base + '/v1/apps')
        finally:
            local.should_exit = remote.should_exit = True
            await asyncio.wait_for(asyncio.gather(*tasks), 10)
            for sock in sockets:
                sock.close()
        assert all(task.done() for task in tasks)
        assert app.state.controller.owner is None
    asyncio.run(scenario())
