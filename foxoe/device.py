"""Optional USB worker. USB discovery, drawing and writes never block the API loop."""
import asyncio
import threading
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from .controller import Controller

ICON_NAMES = frozenset({'window', 'printer', 'home', 'keypad', 'play', 'backspace', 'check', 'close', 'back', 'reload', 'foxoe'})


@lru_cache(maxsize=16)
def builtin_icon(name):
    # Never let API-supplied names become arbitrary filesystem paths.
    name = name if name in ICON_NAMES else 'window'
    try:
        with Image.open(Path(__file__).parent / 'assets' / 'icons' / f'{name}.png') as asset:
            return asset.convert('RGBA').resize((36, 36), Image.Resampling.LANCZOS)
    except OSError:
        return None


@lru_cache(maxsize=128)
def key_image(label: str, disabled: bool, home: bool, png: bytes | None = None, *, icon: str | None = 'window'):
    image = Image.new("RGB", (72, 72), "#4f46e5" if home else "#1f2937")
    if png:
        with Image.open(io.BytesIO(png)) as asset:
            overlay = asset.convert("RGBA")
            image.paste(overlay, (0, 0), overlay)
        return ImageEnhance.Brightness(image).enhance(0.45) if disabled else image
    symbol = builtin_icon('home' if home else icon) if home or icon else None
    if symbol is not None:
        if disabled:
            symbol = ImageEnhance.Brightness(symbol).enhance(0.45)
        image.paste(symbol, (18, 5), symbol)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default(size=14)
    # Wrap by measured width, including unbroken names, without fetching assets.
    lines: list[str] = []
    line = ""
    for char in label[:60]:
        if draw.textlength(line + char, font=font) > 62:
            lines.append(line)
            line = char
        else:
            line += char
    lines.append(line)
    lines = lines[:2 if symbol is not None else 3]
    for index, text in enumerate(lines):
        y = 50 + index * 14 if symbol is not None else 36 + (index - (len(lines) - 1) / 2) * 17
        draw.text((36, y), text,
                  font=font, fill="#9ca3af" if disabled else "#ffffff", anchor="mm")
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
                                              icon=button["icon"] if button else None)
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
