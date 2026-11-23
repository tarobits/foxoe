import asyncio
import json
import socket

import httpx
import pytest
from pydantic import ValidationError

from foxoe.controller import Controller
from foxoe.models import Configuration, DataSource, Widget
from foxoe.sources import Sources, sanitize, system_stats


def test_widget_boundaries_and_source_references():
    with pytest.raises(ValidationError):
        Widget(id="outside", x=23, w=2)
    with pytest.raises(ValidationError):
        Widget(id="outside", y=47, h=2)
    with pytest.raises(ValidationError):
        Configuration(widgets=[Widget(id="one"), Widget(id="two")])
    with pytest.raises(ValidationError):
        Configuration(widgets=[Widget(id="missing", source="unknown")])
    with pytest.raises(ValidationError):
        DataSource(id="bad", name="Bad", url="http://example.test", authEnv="PATH")
    with pytest.raises(ValidationError):
        DataSource(id="bad", name="Bad", url="/demo")


def test_sensitive_fields_and_nested_values_are_sanitized():
    secret = "synthetic-test-value"
    result = sanitize({"token": secret, "items": [{"name": "Job", "password": "private", "description": f"value {secret}"}]}, secret)
    assert "token" not in result
    assert result["items"][0] == {"name": "Job", "description": "value [redacted]"}
    assert len(sanitize(list(range(1000)))) == 200
    assert "load1" in system_stats()


def setup_source():
    source = DataSource(id="queue", name="Queue", url="https://example.test/queue")
    controller = Controller(Configuration(sources=[source]), "http://127.0.0.1:8765")
    return source, controller


@pytest.fixture(autouse=True)
def dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", 443))])


def test_failed_fetch_preserves_last_value_then_recovers():
    async def scenario():
        source, controller = setup_source()
        responses = [httpx.Response(200, json={"jobs": ["First"]}), httpx.Response(500), httpx.Response(200, json={"jobs": ["Next"]})]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: responses.pop(0))) as client:
            sources = Sources(controller, client)
            await sources.fetch(source)
            first_time = sources.cache[source.id]["updatedAt"]
            await sources.fetch(source)
            assert sources.cache[source.id] == {"value": {"jobs": ["First"]}, "error": "source_unavailable", "updatedAt": first_time}
            await sources.fetch(source)
            assert sources.cache[source.id]["value"] == {"jobs": ["Next"]}
            assert sources.cache[source.id]["error"] is None
    asyncio.run(scenario())


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "https://evil.test"}), httpx.Response(200, content=b"not json"), httpx.Response(200, content=b"x" * 262145)])
def test_invalid_upstream_fails_safely(response):
    async def scenario():
        source, controller = setup_source()
        calls = []
        def handle(request):
            calls.append(request)
            return response
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            sources = Sources(controller, client)
            await sources.fetch(source)
            assert sources.cache[source.id]["error"] == "source_unavailable"
            assert len(calls) == 1
    asyncio.run(scenario())


def test_cancelled_fetch_releases_capacity_and_changed_config_discards_result():
    async def scenario():
        source, controller = setup_source()
        started = asyncio.Event()
        release = asyncio.Event()
        async def handle(request):
            started.set()
            await release.wait()
            return httpx.Response(200, json={"jobs": []})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            sources = Sources(controller, client)
            task = asyncio.create_task(sources.fetch(source))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sources.semaphore._value == 4
            started.clear()
            task = asyncio.create_task(sources.fetch(source))
            await started.wait()
            controller.configure(controller.config.model_copy(update={"revision": 1, "sources": []}))
            release.set()
            await task
            assert not sources.cache
            await sources.fetch(source)
            assert sources.cache[source.id]["value"] == {"jobs": []}
    asyncio.run(scenario())


def test_missing_credentials_and_metadata_destination_never_send(monkeypatch):
    async def scenario():
        source, controller = setup_source()
        calls = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: calls.append(request))) as client:
            sources = Sources(controller, client)
            source.authEnv = "FOXOE_SECRET_NONEXISTENT_TEST"
            await sources.fetch(source)
            assert not calls
            source.authEnv = ""
            monkeypatch.setattr(socket, "getaddrinfo", lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))])
            await sources.fetch(source)
            assert not calls
    asyncio.run(scenario())


def test_preview_fetches_fresh_draft_without_mutating_live_cache(monkeypatch):
    monkeypatch.setenv('FOXOE_SECRET_PREVIEW_TEST', 'synthetic-preview-secret')
    async def scenario():
        source, controller = setup_source()
        original = controller.config.model_dump_json()
        draft = source.model_copy(update={'url': 'https://example.test/draft', 'authEnv': 'FOXOE_SECRET_PREVIEW_TEST'})
        responses = [httpx.Response(200, json={'count': 0, 'note': 'synthetic-preview-secret', 'token': 'hidden'}),
                     httpx.Response(500), httpx.Response(200, json=False), httpx.Response(200, content='null')]
        calls = []
        def handle(request):
            assert str(request.url) == draft.url
            assert request.headers['authorization'] == 'Bearer synthetic-preview-secret'
            calls.append(request)
            return responses.pop(0)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            sources = Sources(controller, client)
            sources.cache[source.id] = {'value': {'saved': True}, 'error': None, 'updatedAt': 1}
            sources.next_fetch[source.id] = ('unchanged', 999)
            snapshot = await sources.preview(draft)
            assert snapshot['value'] == {'count': 0, 'note': '[redacted]'}
            assert snapshot['updatedAt'] > 1
            assert await sources.preview(draft) == {'value': None, 'error': 'source_unavailable', 'updatedAt': None}
            assert (await sources.preview(draft))['value'] is False
            null = await sources.preview(draft)
            assert null['value'] is None and null['error'] is None and null['updatedAt']
            assert len(calls) == 4
            assert sources.cache[source.id]['value'] == {'saved': True}
            assert sources.next_fetch[source.id] == ('unchanged', 999)
            assert controller.config.model_dump_json() == original
    asyncio.run(scenario())


@pytest.mark.parametrize('body', ['NaN', 'Infinity', '{"value":-Infinity}', '{"value":1e999}', '<html>Error</html>', 'x' * 262145])
def test_preview_rejects_bad_json_and_recovers(body):
    async def scenario():
        source, controller = setup_source()
        responses = [httpx.Response(200, content=body), httpx.Response(200, json={'ok': True})]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: responses.pop(0))) as client:
            sources = Sources(controller, client)
            assert (await sources.preview(source))['error'] == 'source_unavailable'
            assert (await sources.preview(source))['value'] == {'ok': True}
            assert not sources.cache and not sources.next_fetch
    asyncio.run(scenario())


def test_preview_shares_fetch_capacity_and_cancellation_releases_slots():
    async def scenario():
        source, controller = setup_source()
        started = 0
        release = asyncio.Event()
        async def handle(_):
            nonlocal started
            started += 1
            await release.wait()
            return httpx.Response(200, json={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            sources = Sources(controller, client)
            tasks = [asyncio.create_task(sources.preview(source)) for _ in range(5)]
            try:
                async with asyncio.timeout(2):
                    while started < 4:
                        await asyncio.sleep(.01)
                assert started == 4
                tasks[0].cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tasks[0]
                async with asyncio.timeout(2):
                    while started < 5:
                        await asyncio.sleep(.01)
                release.set()
                await asyncio.gather(*tasks[1:])
                assert sources.semaphore._value == 4
                assert (await sources.preview(source))['error'] is None
                assert not sources.cache
            finally:
                release.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(scenario())


def test_preview_deadline_releases_capacity_and_next_fetch_succeeds(monkeypatch):
    original_timeout = asyncio.timeout
    monkeypatch.setattr('foxoe.sources.asyncio.timeout', lambda _: original_timeout(.02))
    async def scenario():
        source, controller = setup_source()
        blocked = True
        async def handle(_):
            if blocked:
                await asyncio.Event().wait()
            return httpx.Response(200, json={'ok': True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            sources = Sources(controller, client)
            assert (await sources.preview(source))['error'] == 'source_unavailable'
            assert sources.semaphore._value == 4
            blocked = False
            assert (await sources.preview(source))['value'] == {'ok': True}
    asyncio.run(scenario())
