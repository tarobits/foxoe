import importlib
import io

from PIL import Image

from foxoe.controller import Controller
from foxoe.device import DeviceWorker, key_image
from foxoe.models import Configuration


class ImmediateLoop:
    def call_soon_threadsafe(self, function, *args):
        function(*args)


class NoWaitStop:
    stopped = False
    ticks = 0
    def set(self): self.stopped = True
    def is_set(self): return self.stopped
    def wait(self, timeout):
        self.ticks += 1
        if self.ticks > 10: self.set()
        return self.stopped


def test_driver_api_and_recovery_after_failed_write(monkeypatch):
    manager_module = importlib.import_module('StreamDeck.DeviceManager')
    helper = importlib.import_module('StreamDeck.ImageHelpers.PILHelper')
    # Use the library's real connection method, so API drift is caught.
    device_class = importlib.import_module('StreamDeck.Devices.StreamDeck').StreamDeck
    assert hasattr(device_class, 'connected')
    controller = Controller(Configuration(), 'http://127.0.0.1:8765')
    worker = DeviceWorker(controller, ImmediateLoop())
    worker.stop = NoWaitStop()
    worker.update()
    class Deck:
        def __init__(self, fails): self.fails = fails; self.closed = False; self.writes = 0
        def is_visual(self): return True
        def key_count(self): return 15
        def open(self): pass
        def reset(self): pass
        def connected(self): return True
        def set_key_callback(self, callback): self.callback = callback
        def set_brightness(self, brightness): assert brightness == 65
        def set_key_image(self, index, image):
            self.writes += 1
            if self.fails: raise OSError('test USB failure')
            if index == 14: worker.stop.set()
        def close(self): self.closed = True
    first, second = Deck(True), Deck(False)
    calls = 0
    def enumerate_devices(self):
        nonlocal calls
        calls += 1
        if calls > 3:
            worker.stop.set()
        return [first if calls == 1 else second]
    monkeypatch.setattr(manager_module.DeviceManager, '_get_transport', staticmethod(lambda name: None))
    monkeypatch.setattr(manager_module.DeviceManager, 'enumerate', enumerate_devices)
    monkeypatch.setattr(helper, 'to_native_key_format', lambda deck, image: image)
    worker.run()
    assert first.closed and second.closed
    assert second.writes == 15


def test_registered_image_is_rendered_at_key_size_and_dimmed():
    output = io.BytesIO()
    Image.new('RGBA', (72, 72), (200, 100, 50, 255)).save(output, 'PNG')
    normal = key_image('Print', False, False, output.getvalue())
    disabled = key_image('Print', True, False, output.getvalue())
    assert normal.size == disabled.size == (72, 72)
    assert disabled.getpixel((30, 30))[0] < normal.getpixel((30, 30))[0]


def test_builtin_icons_are_drawn_and_home_has_a_house_symbol():
    from PIL import ImageChops
    printer = key_image('Action', False, False, icon='printer')
    window = key_image('Action', False, False, icon='window')
    assert ImageChops.difference(printer, window).getbbox() is not None
    home = key_image('Home', False, True, icon='home')
    blank = key_image('', False, False, icon=None)
    assert len(home.crop((12, 4, 60, 44)).getcolors(72 * 72)) > 2
    assert len(blank.getcolors(72 * 72)) == 1
    assert key_image('', False, False, icon='../../secret').tobytes() == key_image('', False, False, icon='window').tobytes()


def test_custom_icons_override_builtin_icons_and_disabled_icons_are_dimmed():
    output = io.BytesIO()
    Image.new('RGBA', (72, 72), (200, 100, 50, 255)).save(output, 'PNG')
    custom = key_image('Print', False, False, output.getvalue(), icon='printer')
    assert custom.getpixel((36, 20)) == (200, 100, 50)
    normal = key_image('', False, False, icon='home')
    disabled = key_image('', True, False, icon='home')
    from PIL import ImageStat
    assert sum(ImageStat.Stat(disabled).sum) < sum(ImageStat.Stat(normal).sum)


def test_generated_icons_cover_browser_sizes_and_all_supported_key_icons():
    import json
    from pathlib import Path
    from foxoe.device import ICON_NAMES, builtin_icon
    root = Path(__file__).parents[1]
    manifest = json.loads((root / 'extension/manifest.json').read_text())
    for size, filename in manifest['icons'].items():
        with Image.open(root / 'extension' / filename) as icon:
            assert icon.size == (int(size), int(size))
            assert icon.mode == 'RGBA'
            assert icon.getpixel((0, 0))[3] == 0
            assert icon.getbbox() is not None
    for name in ICON_NAMES:
        assert builtin_icon(name) is not None, f'Missing generated asset: {name}; run npm run build:icons'
    fox = (root / 'public/foxoe.svg').read_text()
    assert '<text' not in fox and '<rect' not in fox
