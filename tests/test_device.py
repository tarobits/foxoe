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
    config = Configuration()
    config.apps[0].icon = None
    config.apps[0].textSize = 32
    controller = Controller(config, 'http://127.0.0.1:8765')
    controller.connect('browser')
    controller.context('browser', 'doc', 'http://127.0.0.1:8765/')
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
            if index == 0:
                assert image.tobytes() == key_image(config.apps[0].name, False, False, icon=None, text_size=32).tobytes()
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


def test_off_sets_zero_brightness_ignores_keys_and_on_restores_latest_layout(monkeypatch):
    manager_module=importlib.import_module('StreamDeck.DeviceManager')
    helper=importlib.import_module('StreamDeck.ImageHelpers.PILHelper')
    controller=Controller(Configuration(),'http://127.0.0.1:8765')
    queue=controller.connect('browser'); controller.context('browser','doc','http://127.0.0.1:8765/')
    controller.set_device_enabled(False)
    worker=DeviceWorker(controller,ImmediateLoop()); worker.update()
    class Deck:
        closed=False
        brightness=[]
        writes=[]
        def is_visual(self): return True
        def key_count(self): return 15
        def open(self): pass
        def reset(self): pass
        def connected(self): return True
        def set_key_callback(self, callback): self.callback=callback
        def set_brightness(self, value): self.brightness.append(value)
        def set_key_image(self,index,image): self.writes.append(index)
        def close(self): self.closed=True
    deck=Deck()
    class Stop(NoWaitStop):
        def wait(self,timeout):
            self.ticks+=1
            if self.ticks==1:
                assert deck.brightness==[0] and not deck.writes
                deck.callback(deck,0,True); assert queue.empty()
                controller.config.brightness=23; worker.update()
            elif self.ticks==2:
                assert deck.brightness==[0,0] and not deck.writes
                controller.set_device_enabled(True); worker.update()
            else:
                assert deck.brightness[-1]==23 and deck.writes==list(range(15))
                deck.callback(deck,0,False); deck.callback(deck,0,True)
                assert queue.get_nowait()['type']=='launch'
                self.set()
    worker.stop=Stop()
    monkeypatch.setattr(manager_module.DeviceManager,'_get_transport',staticmethod(lambda name:None))
    monkeypatch.setattr(manager_module.DeviceManager,'enumerate',lambda self:[deck])
    monkeypatch.setattr(helper,'to_native_key_format',lambda deck,image:image)
    worker.run()
    assert deck.closed and worker.stop.ticks==3


def test_failed_brightness_write_reconnects_without_waking_device(monkeypatch):
    manager=importlib.import_module('StreamDeck.DeviceManager')
    controller=Controller(Configuration(),'http://127.0.0.1:8765')
    controller.set_device_enabled(False)
    worker=DeviceWorker(controller,ImmediateLoop()); worker.stop=NoWaitStop(); worker.update()
    calls=[]
    class Deck:
        closed=False
        def __init__(self,fail): self.fail=fail
        def is_visual(self): return True
        def key_count(self): return 15
        def open(self): pass
        def reset(self): pass
        def connected(self): return True
        def set_key_callback(self,callback): pass
        def set_brightness(self,value):
            calls.append(value)
            if self.fail: raise OSError('synthetic USB failure')
            worker.stop.set()
        def close(self): self.closed=True
    first,second=Deck(True),Deck(False)
    devices=iter([first,second])
    monkeypatch.setattr(manager.DeviceManager,'_get_transport',staticmethod(lambda name:None))
    monkeypatch.setattr(manager.DeviceManager,'enumerate',lambda self:[next(devices)])
    worker.run()
    assert calls==[0,0] and first.closed and second.closed
    assert controller.device_enabled is False and worker.rendered_generation==-1


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


def test_text_only_sizes_wrap_within_key_and_keep_home_reserved():
    from PIL import ImageChops
    small = key_image('42', False, False, icon=None, text_size=8)
    large = key_image('42', False, False, icon=None, text_size=32)
    def bounds(image):
        return ImageChops.difference(image, Image.new('RGB', image.size, '#1f2937')).getbbox()
    a, b = bounds(small), bounds(large)
    assert b[2] - b[0] > a[2] - a[0]
    assert b[3] - b[1] > a[3] - a[1]
    for icon in (None, 'user', 'arrow-down-tray'):
        for size in (8, 14, 24, 32):
            image = key_image('WWWW Long label\nÄÖÜ 123', False, False, icon=icon, text_size=size)
            box = bounds(image)
            assert 4 <= box[0] < box[2] <= 68
            assert 4 <= box[1] < box[3] <= 68
    assert key_image('Home', False, True, icon=None).tobytes() == key_image('Home', False, True, icon='home').tobytes()
    assert key_image('42', True, False, icon=None, text_size=32).tobytes() != large.tobytes()


def test_key_colors_tint_without_mutating_cached_icons_or_uploaded_artwork():
    original = key_image('A', False, False, icon='user').tobytes()
    colored = key_image('A', False, False, icon='user', icon_color='#ff0000', text_color='#00ff00', background_color='#0000ff')
    assert colored.getpixel((0, 0)) == (0, 0, 255)
    assert any(r > 200 and g < 20 for count, (r, g, b) in colored.crop((18, 4, 54, 40)).getcolors(72 * 72))
    assert any(g > 200 and r < 20 for count, (r, g, b) in colored.crop((4, 43, 68, 68)).getcolors(72 * 72))
    assert key_image('A', False, False, icon='user').tobytes() == original
    assert key_image('Home', False, True, icon_color='#ff0000', background_color='#000000').tobytes() == key_image('Home', False, True).tobytes()
    png = io.BytesIO()
    artwork = Image.new('RGBA', (72, 72), (0, 0, 0, 0))
    artwork.putpixel((36, 36), (10, 20, 30, 255))
    artwork.save(png, 'PNG')
    custom = key_image('A', False, False, png.getvalue(), icon_color='#ff0000', background_color='#00ff00')
    assert custom.getpixel((36, 36)) == (10, 20, 30)
    assert custom.getpixel((0, 0)) == (0, 255, 0)


def test_long_app_name_shrinks_before_truncating_and_short_label_keeps_size(monkeypatch):
    from PIL import ImageDraw
    drawn = []
    original = ImageDraw.ImageDraw.text
    def record(self, xy, text, *args, **kwargs):
        drawn.append((text, kwargs['font'].size))
        return original(self, xy, text, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', record)
    key_image.cache_clear()
    key_image('Label Station', False, False, icon='printer', text_size=32)
    assert ''.join(text for text, _ in drawn).replace(' ', '') == 'LabelStation'
    assert all(8 <= size < 32 for _, size in drawn)
    drawn.clear()
    key_image('42', False, False, icon=None, text_size=32)
    assert drawn == [('42', 32)]
    for label in ('W' * 60, '\n'.join(['Ä'] * 30), 'A very long application name that must remain complete'):
        drawn.clear()
        rendered = key_image(label, False, False, icon='printer', text_size=32)
        assert ''.join(text for text, _ in drawn).replace(' ', '') == label.replace(' ', '').replace('\n', '')
        assert rendered.size == (72, 72)
        assert all('…' not in text for text, _ in drawn)
