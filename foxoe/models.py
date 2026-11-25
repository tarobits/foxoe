"""Validate configuration and app-supplied controls before changing live state."""
from typing import Annotated, Literal
import json
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .formula import validate_formula

ICON_NAMES = frozenset(json.loads(Path(__file__).with_name('icon_catalog.json').read_text())) | {'foxoe'}
Icon = Literal[tuple(sorted(ICON_NAMES))]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Color = Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$', min_length=7, max_length=7, strict=True)]


class KeyColors(StrictModel):
    iconColor: Color | None = None
    textColor: Color | None = None
    backgroundColor: Color | None = None


class DeckPower(StrictModel):
    enabled: bool = Field(strict=True)


class KeyPreview(KeyColors):
    label: str = Field(default='', max_length=60)
    icon: Icon | None = None
    textSize: int = Field(default=14, ge=8, le=32, strict=True)
    image: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    disabled: bool = Field(default=False, strict=True)
    home: bool = Field(default=False, strict=True)


class Application(KeyColors):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=1, max_length=2048)
    icon: Icon | None = "window"
    textSize: int = Field(default=14, ge=8, le=32, strict=True)
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
    gridVersion: Literal[2] = 2
    revision: int = Field(default=0, ge=0)
    title: str = Field(default="FoxOE", min_length=1, max_length=60)
    locale: Literal["en", "de"] = "en"
    brightness: int = Field(default=65, ge=0, le=100, strict=True)
    apps: list[Application] = Field(default_factory=lambda: [Application(id="foxoe-demo", name="FoxOE Demo", url="/demo", icon="foxoe")], max_length=14)
    sources: list["DataSource"] = Field(default_factory=list, max_length=12)
    widgets: list["Widget"] = Field(default_factory=lambda: [
        Widget(id="clock", kind="clock", x=0, y=0, w=10, h=4),
        Widget(id="load", kind="value", source="system", path="load1", x=10, y=0, w=6, h=4),
        Widget(id="memory", kind="value", source="system", path="memoryPercent", unit="%", x=16, y=0, w=8, h=4),
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
            for element in [widget, *widget.items]:
                if element.kind in ("value", "list") and element.source not in sources:
                    raise ValueError("unknown_source")
                if any(source not in sources for rule in element.rules for source in rule.sources()):
                    raise ValueError("unknown_rule_source")
            for other in self.widgets[index + 1:]:
                if widget.x < other.x + other.w and widget.x + widget.w > other.x and widget.y < other.y + other.h and widget.y + widget.h > other.y:
                    raise ValueError("overlapping_widgets")
        return self


class Button(KeyColors):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=32)
    icon: Icon | None = "window"
    textSize: int = Field(default=14, ge=8, le=32, strict=True)
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


class ComparisonFields(StrictModel):
    source: str = Field(default='system', max_length=40)
    path: str = Field(default='', max_length=200)
    operator: Literal['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'exists', 'missing', 'truthy', 'falsy'] = 'eq'
    value: Annotated[str, Field(max_length=1000, strict=True)] | Annotated[bool, Field(strict=True)] | Annotated[float, Field(strict=True, allow_inf_nan=False)] | None = ''


class ComparisonCondition(ComparisonFields):
    kind: Literal['comparison'] = 'comparison'
    negate: bool = Field(default=False, strict=True)


class ConditionGroup(StrictModel):
    kind: Literal['and', 'or']
    negate: bool = Field(default=False, strict=True)
    children: list['Condition'] = Field(min_length=1, max_length=16)


Condition = Annotated[ComparisonCondition | ConditionGroup, Field(discriminator='kind')]


class ColorAction(StrictModel):
    target: Literal['textColor', 'backgroundColor', 'iconColor']
    color: Color | None


class VisibilityAction(StrictModel):
    target: Literal['visible']
    visible: bool = Field(strict=True)


class TextAction(StrictModel):
    target: Literal['text']
    text: str = Field(max_length=1000, strict=True)


class TitleAction(StrictModel):
    target: Literal['title']
    text: str = Field(max_length=60, strict=True)


class IconAction(StrictModel):
    target: Literal['icon']
    icon: Icon | None


RuleAction = Annotated[ColorAction | VisibilityAction | TextAction | TitleAction | IconAction, Field(discriminator='target')]


class WidgetRule(ComparisonFields):
    condition: Condition | None = None
    actions: list[RuleAction] | None = Field(default=None, min_length=1, max_length=16)
    target: Literal['textColor', 'backgroundColor', 'iconColor', 'visible'] = 'textColor'
    color: Color | None = None
    visible: bool = True

    @field_validator('condition', mode='before')
    @classmethod
    def bounded_condition(cls, value):
        # Bound the raw tree before recursive parsing, including hostile/cyclic input.
        pending = [(value, 0)] if value is not None else []
        count = 0
        while pending:
            node, depth = pending.pop()
            count += 1
            if count > 32 or depth > 4:
                raise ValueError('condition_too_complex')
            children = node.get('children', []) if isinstance(node, dict) else getattr(node, 'children', [])
            if isinstance(children, list):
                if len(children) > 16:
                    raise ValueError('condition_too_complex')
                pending.extend((child, depth + 1) for child in children)
        return value

    def sources(self):
        pending = [self.condition] if self.condition is not None else [self]
        while pending:
            node = pending.pop()
            if isinstance(node, ConditionGroup):
                pending.extend(node.children)
            else:
                yield node.source


class WidgetAppearance(StrictModel):
    textColor: Color | None = None
    backgroundColor: Color | None = None
    iconColor: Color | None = None
    fontSize: int | None = Field(default=None, ge=8, le=96, strict=True)
    fontWeight: Literal[300, 400, 500, 600, 700, 800, 900] | None = None
    italic: bool = Field(default=False, strict=True)
    verticalAlign: Literal['top', 'middle', 'bottom'] | None = None
    align: Literal['left', 'center', 'right'] = 'left'
    rules: list[WidgetRule] = Field(default_factory=list, max_length=16)


class WidgetContent(WidgetAppearance):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    kind: Literal["clock", "text", "value", "list", "icon"] = "value"
    title: str = Field(default="", max_length=60)
    showTitle: bool = Field(default=True, strict=True)
    text: str = Field(default="", max_length=1000)
    source: str = Field(default="system", max_length=40)
    path: str = Field(default="", max_length=200)
    itemPath: str = Field(default="", max_length=200)
    unit: str = Field(default="", max_length=12)
    icon: Icon | None = 'window'

    formula: str = Field(default='', max_length=512, strict=True)
    decimals: int | None = Field(default=None, ge=0, le=10, strict=True)

    @field_validator('formula')
    @classmethod
    def valid_formula(cls, value):
        return validate_formula(value)

    @model_validator(mode='after')
    def valid_content_actions(self):
        if self.kind not in ('text', 'value') and any(action.target == 'text' for rule in self.rules for action in rule.actions or []):
            raise ValueError('text_action_requires_text_or_value')
        if self.kind != 'icon' and any(action.target == 'icon' for rule in self.rules for action in rule.actions or []):
            raise ValueError('icon_action_requires_icon')
        return self


class WidgetItem(WidgetContent):
    row: int = Field(default=0, ge=0, le=5, strict=True)
    column: int = Field(default=0, ge=0, le=5, strict=True)
    rowSpan: int = Field(default=1, ge=1, le=6, strict=True)
    columnSpan: int = Field(default=1, ge=1, le=6, strict=True)


class Widget(WidgetContent):
    kind: Literal['clock', 'text', 'value', 'list', 'icon', 'layout'] = 'value'
    x: int = Field(default=0, ge=0, le=23, strict=True)
    y: int = Field(default=0, ge=0, le=47, strict=True)
    w: int = Field(default=8, ge=2, le=24, strict=True)
    h: int = Field(default=4, ge=1, le=24, strict=True)
    padding: int = Field(default=24, ge=0, le=48, strict=True)
    gap: int = Field(default=8, ge=0, le=32, strict=True)
    allowOverlap: bool = Field(default=False, strict=True)
    columns: list[Annotated[int, Field(ge=1, le=12, strict=True)]] = Field(default_factory=lambda: [1, 1], min_length=1, max_length=6)
    rows: list[Annotated[int, Field(ge=1, le=12, strict=True)]] = Field(default_factory=lambda: [1], min_length=1, max_length=6)
    items: list[WidgetItem] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.w > 24 or self.y + self.h > 48:
            raise ValueError("widget_out_of_bounds")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError('duplicate_item_id')
        for index, item in enumerate(self.items):
            if item.row + item.rowSpan > len(self.rows) or item.column + item.columnSpan > len(self.columns):
                raise ValueError('item_out_of_bounds')
            for other in self.items[index + 1:] if not self.allowOverlap else []:
                if item.column < other.column + other.columnSpan and item.column + item.columnSpan > other.column and item.row < other.row + other.rowSpan and item.row + item.rowSpan > other.row:
                    raise ValueError('overlapping_items')
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
