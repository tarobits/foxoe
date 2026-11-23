import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from foxoe.models import Configuration, Widget, WidgetItem, WidgetRule
from foxoe.store import Store, Conflict
from foxoe.server import create_app


def legacy_database(path, invalid=False):
    path.mkdir(exist_ok=True)
    # Existing installations already have credentials; isolate the migration
    # concurrency test from first-install credential creation.
    for name in ('bridge-token', 'registration-token'):
        (path / name).write_text('synthetic-legacy-credential-for-tests-only')
    value = {'revision': 7, 'title': 'Saved dashboard', 'apps': [], 'sources': [], 'widgets': [
        {'id': 'clock', 'kind': 'clock', 'x': 0, 'y': 0, 'w': 5, 'h': 2},
        {'id': 'value', 'kind': 'value', 'x': 5, 'y': 0, 'w': 7, 'h': 2},
    ]}
    if invalid:
        value['widgets'][0]['x'] = 'invalid'
    with sqlite3.connect(path / 'foxoe.sqlite') as db:
        db.execute('CREATE TABLE settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO settings VALUES (1, ?)', (json.dumps(value),))
    return value


def test_grid_migration_preserves_layout_once_even_with_concurrent_starts(tmp_path):
    original = legacy_database(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = list(pool.map(Store, [tmp_path, tmp_path]))
    for store in stores:
        saved = store.load()
        assert saved.gridVersion == 2 and saved.revision == 8
        assert saved.title == original['title']
        for old, new in zip(original['widgets'], saved.widgets):
            for field in ('x', 'y', 'w', 'h'):
                assert getattr(new, field) == old[field] * 2
        with pytest.raises(Conflict):
            store.save(saved.model_copy(update={'revision': 7}))
    assert Store(tmp_path).load().revision == 8


def test_invalid_migration_leaves_original_data_and_allows_recovery(tmp_path):
    original = legacy_database(tmp_path, invalid=True)
    with pytest.raises(ValueError):
        Store(tmp_path)
    with sqlite3.connect(tmp_path / 'foxoe.sqlite') as db:
        assert json.loads(db.execute('SELECT value FROM settings').fetchone()[0]) == original
        original['widgets'][0]['x'] = 0
        db.execute('UPDATE settings SET value=?', (json.dumps(original),))
    assert Store(tmp_path).load().widgets[1].x == 10


def test_widget_layout_styles_and_rule_values_round_trip(tmp_path):
    item = WidgetItem(id='status', kind='icon', icon='user', textColor='#ff0000', fontSize=24,
                      rules=[WidgetRule(path='load1', operator='gt', value=2, target='iconColor', color='#00ff00')])
    widget = Widget(id='custom', kind='layout', columns=[2, 1], rows=[1, 3], items=[item], backgroundColor='#112233')
    store = Store(tmp_path)
    config = store.load().model_copy(update={'widgets': [widget]})
    store.save(config)
    assert store.load().widgets[0] == widget
    for value in [None, False, 0, 1.5, '0']:
        assert WidgetRule(value=value).value == value


@pytest.mark.parametrize('changes', [
    {'columns': []}, {'columns': [0]}, {'rows': [True]}, {'columns': [1] * 7},
    {'fontSize': 97}, {'fontSize': True}, {'backgroundColor': 'url(https://evil.test)'},
    {'padding': -1}, {'gap': 33}, {'x': 23, 'w': 2}, {'y': 47, 'h': 2},
    {'items': [{'id': 'a', 'column': 2}]}, {'items': [{'id': 'a', 'rowSpan': 2}]},
    {'items': [{'id': 'a'}, {'id': 'b'}]}, {'items': [{'id': 'a'}, {'id': 'a', 'column': 1}]},
    {'rules': [{'operator': 'eval'}]}, {'rules': [{'target': '__proto__'}]},
    {'rules': [{'value': {'code': 'alert(1)'}}]}, {'rules': [{'value': float('nan')}]},
    {'rules': [{}] * 17},
])
def test_widget_rejects_unsafe_or_invalid_layouts(changes):
    with pytest.raises(ValidationError):
        Widget(id='bad', **changes)


def test_config_rejects_missing_element_and_rule_sources():
    for widget in [Widget(id='a', kind='layout', items=[WidgetItem(id='child', source='missing')]),
                   Widget(id='a', rules=[WidgetRule(source='missing')]),
                   Widget(id='a', kind='layout', items=[WidgetItem(id='child', kind='text', rules=[WidgetRule(source='missing')])])]:
        with pytest.raises(ValidationError):
            Configuration(widgets=[widget])


def test_failed_widget_save_is_atomic_and_next_valid_save_works(tmp_path):
    app = create_app(tmp_path, hardware=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        before = client.get('/api/config').json()
        invalid = json.loads(json.dumps(before))
        invalid['widgets'][0]['rules'] = [{'source': 'unregistered'}]
        assert client.put('/api/config', json=invalid, headers={'origin': 'http://127.0.0.1:8765'}).status_code == 422
        assert client.get('/api/config').json() == before
        before['widgets'][0]['backgroundColor'] = '#123456'
        assert client.put('/api/config', json=before, headers={'origin': 'http://127.0.0.1:8765'}).status_code == 200
