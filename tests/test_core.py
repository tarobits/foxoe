import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from foxoe.controller import Controller
from foxoe.models import Application, Configuration, Layout, matches_app
from foxoe.store import Conflict, Store

ORIGIN = "http://127.0.0.1:8765"


def configured():
    return Configuration(apps=[Application(id="printer", name="Printer", url="https://printer.example/app")])


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "https://user:password@example.com", "https://example.com:bad", "https://example.com/\\evil", "https://example.com/\nsecret"])
def test_invalid_urls(url):
    with pytest.raises(ValidationError):
        Application(id="printer", name="Printer", url=url)


@pytest.mark.parametrize("url, expected", [
    ("https://printer.example/app", True),
    ("https://printer.example/app/job?id=1", True),
    ("https://printer.example/app-evil", False),
    ("https://printer.example.evil/app", False),
    ("http://printer.example/app", False),
    ("https://printer.example:443/app", True),
    ("https://printer.example:444/app", False),
    ("https://bad@printer.example/app", False),
])
def test_url_scope(url, expected):
    assert matches_app(url, "https://printer.example/app", ORIGIN) is expected


def test_config_and_layout_boundaries():
    with pytest.raises(ValidationError):
        Configuration(apps=configured().apps * 2)
    with pytest.raises(ValidationError):
        Configuration(brightness=True)
    with pytest.raises(ValidationError):
        Configuration(brightness=101)
    with pytest.raises(ValidationError):
        Layout(id="too-large", buttons=[None] * 15)
    with pytest.raises(ValidationError):
        Layout(id="duplicates", buttons=[{"id": "x", "label": "X"}] * 2)


def test_conflicting_saves_are_atomic_and_recoverable(tmp_path):
    store = Store(tmp_path)
    initial = store.load()
    def save(title):
        try:
            return store.save(initial.model_copy(update={"title": title})).title
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["One", "Two"]))
    assert results.count("conflict") == 1
    current = store.load()
    assert current.title in ("One", "Two") and current.revision == 1
    assert store.save(current.model_copy(update={"title": "Recovery"})).revision == 2
    assert Store(tmp_path).token == store.token
    assert (tmp_path / "bridge-token").stat().st_mode & 0o077 == 0


def test_document_switch_rejects_late_layout_and_stale_press():
    async def scenario():
        controller = Controller(configured(), ORIGIN)
        queue = controller.connect("browser")
        controller.context("browser", "old-document", "https://printer.example/app")
        controller.layout("browser", "old-document", "show", {"id": "main", "buttons": [{"id": "print", "label": "Print"}]})
        old_generation = controller.generation
        controller.context("browser", "new-document", "https://printer.example/app")
        with pytest.raises(ValueError):
            controller.layout("browser", "old-document", "show", {"id": "old", "buttons": []})
        controller.press(0, True, old_generation)
        assert queue.empty()
        controller.press(0, False, old_generation)
        controller.layout("browser", "new-document", "show", {"id": "new", "buttons": [{"id": "print", "label": "Print"}]})
        controller.press(0, True, controller.generation)
        assert (await queue.get())["document"] == "new-document"
    asyncio.run(scenario())


def test_keypad_stack_disabled_repeat_home_and_disconnect():
    async def scenario():
        controller = Controller(configured(), ORIGIN)
        queue = controller.connect("browser")
        controller.context("browser", "doc", "https://printer.example/app")
        controller.layout("browser", "doc", "show", {"id": "base", "buttons": [{"id": "print", "label": "Print", "disabled": True}]})
        controller.press(0, True, controller.generation)
        controller.press(0, False, controller.generation)
        assert queue.empty()
        controller.layout("browser", "doc", "push", {"id": "keypad", "buttons": [{"id": "digit.1", "label": "1"}]})
        controller.press(0, True, controller.generation)
        controller.press(0, True, controller.generation)
        assert queue.qsize() == 1
        assert (await queue.get())["layout"] == "keypad"
        controller.layout("browser", "doc", "pop", None)
        assert controller.buttons()[0]["disabled"]
        assert controller.buttons()[14]["id"] == "home"
        with pytest.raises(ValueError):
            controller.connect("intruder")
        controller.disconnect("intruder")
        assert controller.owner == "browser"
        controller.disconnect("browser")
        assert controller.buttons()[14]["disabled"]
        controller.connect("next-browser")
        controller.context("next-browser", "new", ORIGIN + "/")
        assert controller.buttons()[0]["kind"] == "launch"
    asyncio.run(scenario())


def test_malformed_layout_does_not_destroy_previous_and_stack_is_bounded():
    controller = Controller(configured(), ORIGIN)
    controller.connect("browser")
    controller.context("browser", "doc", "https://printer.example/app")
    for index in range(8):
        controller.layout("browser", "doc", "push", {"id": str(index), "buttons": []})
    with pytest.raises(ValueError):
        controller.layout("browser", "doc", "push", {"id": "overflow", "buttons": []})
    with pytest.raises(ValueError):
        controller.layout("browser", "doc", "show", {"id": "bad", "buttons": [None] * 15})
    assert controller.stack[-1].id == "7"
    controller.layout("browser", "doc", "pop", None)
    controller.layout("browser", "doc", "push", {"id": "recovered", "buttons": []})
    assert controller.stack[-1].id == "recovered"


def test_slow_consumer_fails_closed_and_can_reconnect():
    controller = Controller(configured(), ORIGIN)
    controller.connect("browser")
    for _ in range(65):
        controller.emit({"type": "test"})
    assert controller.owner is None
    assert controller.connect("recovered").empty()
