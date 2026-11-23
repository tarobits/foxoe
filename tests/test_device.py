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
