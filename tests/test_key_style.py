import pytest
from pydantic import ValidationError

from foxoe.models import Application, Button, Configuration
from foxoe.controller import Controller


def test_null_icon_and_text_size_survive_launcher_and_live_updates():
    app = Application(id='app', name='Text', url='https://example.test', icon=None, textSize=24)
    controller = Controller(Configuration(apps=[app]), 'http://127.0.0.1:8765')
    controller.connect('browser')
    controller.context('browser', 'home', 'http://127.0.0.1:8765/')
    assert controller.buttons()[0]['icon'] is None
    assert controller.buttons()[0]['textSize'] == 24
    controller.context('browser', 'doc', app.url)
    controller.layout('browser', 'doc', 'show', {'id': 'main', 'buttons': [{'id': 'a', 'label': '42', 'icon': None, 'textSize': 32}]})
    before = controller.state()
    for changes in [{'textSize': 0}, {'textSize': 33}, {'textSize': True}, {'textSize': '20'}, {'icon': '../../secret'}, {'icon': ''}]:
        with pytest.raises(ValidationError):
            controller.layout('browser', 'doc', 'update', {'id': 'a', 'changes': changes})
        assert controller.state() == before
    controller.layout('browser', 'doc', 'update', {'id': 'a', 'changes': {'icon': 'user', 'textSize': 8}})
    assert controller.buttons()[0]['icon'] == 'user'
    assert controller.buttons()[0]['textSize'] == 8
    assert controller.buttons()[14]['icon'] == 'home'


@pytest.mark.parametrize('size', [None, True, False, 7, 33, -100, 1e10, 14.5, '14', {}, []])
def test_invalid_text_sizes_rejected(size):
    with pytest.raises(ValidationError):
        Button(id='a', label='A', textSize=size)
    with pytest.raises(ValidationError):
        Application(id='app', name='App', url='https://example.test', textSize=size)


def test_omitted_style_preserves_defaults():
    button = Button(id='a', label='A')
    assert button.icon == 'window'
    assert button.textSize == 14
