"""Optional USB worker. USB discovery, drawing and writes never block the API loop."""
import asyncio
import threading
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageColor

from .controller import Controller
from .models import ICON_NAMES

@lru_cache(maxsize=64)
def builtin_icon(name):
    # Never let API-supplied names become arbitrary filesystem paths.
    name = name if name in ICON_NAMES else 'window'
    try:
        with Image.open(Path(__file__).parent / 'assets' / 'icons' / f'{name}.png') as asset:
            return asset.convert('RGBA').resize((36, 36), Image.Resampling.LANCZOS)
    except OSError:
        return None


@lru_cache(maxsize=128)
def key_image(label: str, disabled: bool, home: bool, png: bytes | None = None, *, icon: str | None = 'window', text_size: int = 14,
              icon_color: str | None = None, text_color: str | None = None, background_color: str | None = None):
    if type(text_size) is not int or not 8 <= text_size <= 32:
        raise ValueError('invalid_text_size')
    if home:
        icon_color = text_color = background_color = None
    image = Image.new("RGB", (72, 72), "#4f46e5" if home else background_color or "#1f2937")
    if png:
        with Image.open(io.BytesIO(png)) as asset:
            overlay = asset.convert("RGBA")
            image.paste(overlay, (0, 0), overlay)
        return ImageEnhance.Brightness(image).enhance(0.45) if disabled else image
    symbol = builtin_icon('home' if home else icon) if home or icon else None
    text_top = 4
    if symbol is not None:
        symbol_size = min(36, 62 - text_size - 2)
        symbol = symbol.resize((symbol_size, symbol_size), Image.Resampling.LANCZOS)
        if icon_color:
            tinted = Image.new('RGBA', symbol.size, icon_color)
            tinted.putalpha(symbol.getchannel('A'))
            symbol = tinted
        if disabled:
            symbol = ImageEnhance.Brightness(symbol).enhance(0.45)
        image.paste(symbol, ((72 - symbol_size) // 2, 4), symbol)
        text_top = symbol_size + 7
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", text_size)
    except OSError:
        font = ImageFont.load_default(size=text_size)
    # Wrap by measured width, including unbroken names, without fetching assets.
    lines: list[str] = []
    line = ""
    for char in label[:60]:
        if char == '\n':
            lines.append(line)
            line = ''
        elif line and draw.textlength(line + char, font=font) > 62:
            lines.append(line)
            line = char
        else:
            line += char
    lines.append(line)
    line_height = text_size + 2
    limit = max(1, (68 - text_top) // line_height)
    if len(lines) > limit:
        lines = lines[:limit]
        while lines[-1] and draw.textlength(lines[-1] + '…', font=font) > 62:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    # Compose in a bounded region: large glyphs and unusual Unicode cannot
    # overlap the icon or escape the key. Keep the selected size, not auto-shrink.
    text_layer = Image.new('RGBA', (64, 68 - text_top))
    text_draw = ImageDraw.Draw(text_layer)
    ink = text_color or '#ffffff'
    if disabled:
        ink = tuple(int(channel * .45) for channel in ImageColor.getrgb(text_color)) if text_color else '#9ca3af'
    for index, text in enumerate(lines):
        y = text_layer.height / 2 + (index - (len(lines) - 1) / 2) * line_height
        text_draw.text((32, y), text,
                  font=font, fill=ink, anchor="mm")
    image.paste(text_layer, (4, text_top), text_layer)
    return image


class DeviceWorker:
    def __init__(self, controller: Controller, loop: asyncio.AbstractEventLoop, image_loader=lambda digest: None):
        self.controller = controller
        self.loop = loop
        self.image_loader = image_loader
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.snapshot = ([], -1, 65)
        self.rendered_generation = -1
        self.thread = threading.Thread(target=self.run, name="foxoe-usb", daemon=True)

    def update(self):
        with self.lock:
            self.snapshot = (self.controller.buttons(), self.controller.generation, self.controller.config.brightness)

    def status(self, value: str):
        self.loop.call_soon_threadsafe(self.controller.held.clear)
        self.loop.call_soon_threadsafe(setattr, self.controller, "device", value)

    def key_changed(self, deck, key, down):
        self.loop.call_soon_threadsafe(self.controller.press, key, down, self.rendered_generation)

    def run(self):
        try:
            from StreamDeck.DeviceManager import DeviceManager
            from StreamDeck.ImageHelpers import PILHelper
        except ImportError:
            self.status("driver_missing")
            return
        deck = None
        previous = None
        try:
            while not self.stop.is_set():
                try:
                    if deck is None:
                        candidates = DeviceManager().enumerate()
                        deck = next((item for item in candidates if item.is_visual() and item.key_count() == 15), None)
                        if deck is None:
                            self.status("disconnected")
                            self.stop.wait(2)
                            continue
                        deck.open()
                        deck.reset()
                        deck.set_key_callback(self.key_changed)
                        previous = None
                        self.status("connected")
                    if not deck.connected():
                        raise OSError("USB disconnected")
                    with self.lock:
                        snapshot = self.snapshot
                    if snapshot != previous:
                        buttons, generation, brightness = snapshot
                        self.rendered_generation = -1
                        deck.set_brightness(brightness)
                        for index, button in enumerate(buttons):
                            old = previous[0][index] if previous and len(previous[0]) > index else None
                            if previous and button == old:
                                continue
                            png = self.image_loader(button["image"]) if button and button.get("image") else None
                            image = key_image(button["label"] if button else "", bool(button and button["disabled"]), index == 14, png,
                                              icon=button["icon"] if button else None,
                                              text_size=button.get('textSize', 14) if button else 14,
                                              icon_color=button.get('iconColor') if button else None,
                                              text_color=button.get('textColor') if button else None,
                                              background_color=button.get('backgroundColor') if button else None)
                            deck.set_key_image(index, PILHelper.to_native_key_format(deck, image))
                        self.rendered_generation = generation
                        previous = snapshot
                    self.stop.wait(0.15)
                except Exception:
                    # Permission errors, unplugging and failed writes all release
                    # the handle before the next discovery attempt.
                    self.status("unavailable")
                    self.rendered_generation = -1
                    if deck is not None:
                        try:
                            deck.close()
                        except Exception:
                            pass
                    deck = None
                    self.stop.wait(2)
        finally:
            if deck is not None:
                try:
                    deck.reset()
                finally:
                    deck.close()

    async def close(self):
        self.stop.set()
        await asyncio.to_thread(self.thread.join, 5)
