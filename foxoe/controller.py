"""One browser owns the deck; document and layout generations reject stale input."""
import asyncio
from typing import Any

from .models import Configuration, Layout, matches_app

TEXT = {
    "en": {"home": "Home", "back": "Back", "reload": "Reload"},
    "de": {"home": "Start", "back": "Zurück", "reload": "Neu laden"},
}


class Controller:
    def __init__(self, config: Configuration, origin: str):
        self.config = config
        self.origin = origin
        self.owner: str | None = None
        self.queue: asyncio.Queue | None = None
        self.document: str | None = None
        self.app_id: str | None = None
        self.home = False
        self.stack: list[Layout] = []
        self.generation = 0
        self.held: set[int] = set()
        self.device = "disconnected"
        self.device_enabled = True

    def set_device_enabled(self, enabled: bool):
        if enabled != self.device_enabled:
            self.device_enabled = enabled
            self.generation += 1
            self.held.clear()

    def connect(self, owner: str) -> asyncio.Queue:
        if self.owner is not None:
            raise ValueError("bridge_busy")
        self.owner = owner
        self.queue = asyncio.Queue(maxsize=64)
        self.invalidate()
        return self.queue

    def disconnect(self, owner: str):
        if self.owner == owner:
            self.owner = None
            self.queue = None
            self.invalidate()

    def invalidate(self):
        self.document = None
        self.app_id = None
        self.home = False
        self.stack = []
        self.generation += 1

    def context(self, owner: str, document: str, url: str):
        self.check_owner(owner)
        self.invalidate()
        if not isinstance(document, str) or not 1 <= len(document) <= 128:
            raise ValueError("invalid_document")
        if not isinstance(url, str) or len(url) > 4096:
            raise ValueError("invalid_url")
        self.document = document
        self.home = url in (self.origin, self.origin + "/")
        self.app_id = next((app.id for app in self.config.apps if matches_app(url, app.url, self.origin)), None)

    def check_owner(self, owner: str):
        if owner != self.owner:
            raise ValueError("not_owner")

    def layout(self, owner: str, document: str, operation: str, value: Any):
        self.check_owner(owner)
        if document != self.document or not self.app_id:
            raise ValueError("inactive_document")
        app = next(app for app in self.config.apps if app.id == self.app_id)
        if operation == "update":
            if not self.stack or not isinstance(value, dict) or not isinstance(value.get("changes"), dict):
                raise ValueError("invalid_update")
            current = self.stack[-1].model_dump()
            index = next((index for index, button in enumerate(current["buttons"]) if button and button["id"] == value.get("id")), None)
            if index is None or "id" in value["changes"]:
                raise ValueError("invalid_update")
            current["buttons"][index].update(value["changes"])
            updated = Layout.model_validate(current)
            if any(button and button.image and button.image not in app.images for button in updated.buttons):
                raise ValueError("unknown_image")
            self.stack[-1] = updated
            self.generation += 1
            return
        if operation in ("screen", "pushScreen"):
            screen = next((screen for screen in app.screens if screen.id == value), None)
            if screen is None:
                raise ValueError("unknown_screen")
            value = screen.model_dump()
            operation = "show" if operation == "screen" else "push"
        if operation == "pop":
            if self.stack:
                self.stack.pop()
        else:
            layout = Layout.model_validate(value)
            if any(button and button.image and button.image not in app.images for button in layout.buttons):
                raise ValueError("unknown_image")
            if operation == "push":
                if len(self.stack) >= 8:
                    raise ValueError("layout_stack_full")
                self.stack.append(layout)
            elif operation == "show":
                self.stack = [layout]
            else:
                raise ValueError("invalid_operation")
        self.generation += 1

    def configure(self, config: Configuration):
        self.config = config
        self.invalidate()
        self.emit({"type": "configuration", "config": config.model_dump()})

    def emit(self, event: dict):
        if self.queue is None:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Dropping a press silently can produce a misleading UI. Fail closed;
            # the bridge receiver notices the lost owner and disconnects.
            owner = self.owner
            if owner:
                self.disconnect(owner)

    def buttons(self) -> list[dict | None]:
        text = TEXT[self.config.locale]
        result: list[dict | None] = [None] * 15
        if self.home and self.owner:
            for index, app in enumerate(self.config.apps):
                result[index] = {"id": app.id, "label": app.name, "icon": app.icon, "textSize": app.textSize,
                                 "iconColor": app.iconColor, "textColor": app.textColor, "backgroundColor": app.backgroundColor,
                                 "image": app.images.get(app.image), "kind": "launch", "disabled": False}
        elif self.app_id and self.stack:
            app = next(app for app in self.config.apps if app.id == self.app_id)
            for index, button in enumerate(self.stack[-1].buttons):
                if button:
                    result[index] = {**button.model_dump(), "image": app.images.get(button.image), "kind": "action"}
        elif self.document and self.owner:
            result[0] = {"id": "back", "label": text["back"], "icon": "back", "kind": "browser", "disabled": False}
            result[1] = {"id": "reload", "label": text["reload"], "icon": "reload", "kind": "browser", "disabled": False}
        result[14] = {"id": "home", "label": text["home"], "icon": "home", "kind": "browser", "disabled": not bool(self.owner)}
        return result

    def press(self, index: int, down: bool, generation: int):
        if not self.device_enabled:
            return
        if not down:
            self.held.discard(index)
            return
        if index in self.held:
            return
        self.held.add(index)
        if not 0 <= index < 15 or generation != self.generation or not self.owner:
            return
        button = self.buttons()[index]
        if not button or button["disabled"]:
            return
        event = {"type": button["kind"], "id": button["id"], "document": self.document, "generation": self.generation}
        if button["kind"] == "action":
            event["layout"] = self.stack[-1].id
        self.emit(event)

    def state(self):
        return {"connected": bool(self.owner), "device": self.device, "activeApp": self.app_id,
                "deviceEnabled": self.device_enabled,
                "home": self.home, "generation": self.generation, "configRevision": self.config.revision, "buttons": self.buttons()}
