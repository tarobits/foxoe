"""Validate configuration and app-supplied controls before changing live state."""
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Icon = Literal["window", "printer", "home", "keypad", "play", "backspace", "check", "close", "back", "reload", "foxoe"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Application(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=1, max_length=2048)
    icon: Icon = "window"
    image: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    images: dict[str, str] = Field(default_factory=dict, max_length=32)
    screens: list["Layout"] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def valid_assets(self):
        import re
        if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", key) or not re.fullmatch(r"[a-f0-9]{64}", value) for key, value in self.images.items()):
            raise ValueError("invalid_asset")
        if self.image and self.image not in self.images:
            raise ValueError("unknown_image")
        if len({screen.id for screen in self.screens}) != len(self.screens):
            raise ValueError("duplicate_screen")
        if any(button and button.image and button.image not in self.images for screen in self.screens for button in screen.buttons):
            raise ValueError("unknown_image")
        return self

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if value == "/demo":
            return value
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "\\" in value or any(ord(c) < 33 for c in value)):
            raise ValueError("invalid_app_url")
        try:
            parsed.port
        except ValueError as error:
            raise ValueError("invalid_app_url") from error
        return value


class Configuration(StrictModel):
    revision: int = Field(default=0, ge=0)
    title: str = Field(default="FoxOE", min_length=1, max_length=60)
    locale: Literal["en", "de"] = "en"
    brightness: int = Field(default=65, ge=0, le=100, strict=True)
    apps: list[Application] = Field(default_factory=lambda: [Application(id="foxoe-demo", name="FoxOE Demo", url="/demo", icon="foxoe")], max_length=14)
    sources: list["DataSource"] = Field(default_factory=list, max_length=12)
    widgets: list["Widget"] = Field(default_factory=lambda: [
        Widget(id="clock", kind="clock", x=0, y=0, w=5, h=2),
        Widget(id="load", kind="value", source="system", path="load1", x=5, y=0, w=3, h=2),
        Widget(id="memory", kind="value", source="system", path="memoryPercent", unit="%", x=8, y=0, w=4, h=2),
    ], max_length=24)

    @model_validator(mode="after")
    def unique_apps(self):
        if len({app.id for app in self.apps}) != len(self.apps):
            raise ValueError("duplicate_app_id")
        if len({source.id for source in self.sources}) != len(self.sources) or any(source.id == "system" for source in self.sources):
            raise ValueError("duplicate_source_id")
        if len({widget.id for widget in self.widgets}) != len(self.widgets):
            raise ValueError("duplicate_widget_id")
        sources = {source.id for source in self.sources} | {"system"}
        for index, widget in enumerate(self.widgets):
            if widget.kind in ("value", "list") and widget.source not in sources:
                raise ValueError("unknown_source")
            for other in self.widgets[index + 1:]:
                if widget.x < other.x + other.w and widget.x + widget.w > other.x and widget.y < other.y + other.h and widget.y + widget.h > other.y:
                    raise ValueError("overlapping_widgets")
        return self


class Button(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=32)
    icon: Icon = "window"
    disabled: bool = False
    image: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,40}$")


class Layout(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$")
    buttons: list[Button | None] = Field(max_length=14)

    @model_validator(mode="after")
    def unique_buttons(self):
        ids = [button.id for button in self.buttons if button]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_action_id")
        return self


class DataSource(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=1, max_length=2048)
    interval: int = Field(default=15, ge=5, le=3600, strict=True)
    authEnv: str = Field(default="", pattern=r"^(FOXOE_SECRET_[A-Z0-9_]+)?$")

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        value = Application.safe_url(value)
        if value.startswith("/"):
            raise ValueError("absolute_url_required")
        return value


class Widget(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    kind: Literal["clock", "text", "value", "list"] = "value"
    title: str = Field(default="", max_length=60)
    text: str = Field(default="", max_length=1000)
    source: str = Field(default="system", max_length=40)
    path: str = Field(default="", max_length=200)
    itemPath: str = Field(default="", max_length=200)
    unit: str = Field(default="", max_length=12)
    x: int = Field(default=0, ge=0, le=11, strict=True)
    y: int = Field(default=0, ge=0, le=23, strict=True)
    w: int = Field(default=4, ge=2, le=12, strict=True)
    h: int = Field(default=2, ge=1, le=12, strict=True)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.w > 12 or self.y + self.h > 24:
            raise ValueError("widget_out_of_bounds")
        return self


Application.model_rebuild()
Configuration.model_rebuild()


def matches_app(url: str, configured: str, origin: str) -> bool:
    """Path-segment matching avoids granting /printer-evil access to /printer."""
    try:
        actual = urlsplit(url)
        expected = urlsplit(origin + configured if configured.startswith("/") else configured)
        if actual.username is not None or actual.password is not None or "\\" in url:
            return False
        def authority(parsed):
            return (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        base = expected.path.rstrip("/")
        return authority(actual) == authority(expected) and (actual.path == base or actual.path.startswith(base + "/") or not base)
    except (ValueError, AttributeError):
        return False
