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
        Widget(id="outside", x=11, w=2)
    with pytest.raises(ValidationError):
        Widget(id="outside", y=23, h=2)
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
