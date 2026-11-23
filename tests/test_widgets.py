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


def test_item_overlap_is_opt_in_and_never_disables_other_validation():
    value = {'id': 'layout', 'kind': 'layout', 'items': [{'id': 'a'}, {'id': 'b'}]}
    with pytest.raises(ValidationError):
        Widget(**value)
    enabled = Widget(**value, allowOverlap=True)
    assert enabled.allowOverlap is True
    assert Widget(id='legacy').allowOverlap is False
    for change in ({'allowOverlap': 'true'}, {'allowOverlap': 1}, {'allowOverlap': None},
                   {'items': [{'id': 'a', 'row': 1}]}, {'items': [{'id': 'a'}, {'id': 'a'}]},
                   {'items': [{'id': 'a', 'columnSpan': 3}]}):
        with pytest.raises(ValidationError):
            Widget(**{**value, 'allowOverlap': True, **change})
    with pytest.raises(ValidationError, match='overlapping_widgets'):
        Configuration(widgets=[enabled, Widget(id='second', allowOverlap=True)])


def test_disabling_item_overlap_is_atomic_and_can_recover(tmp_path):
    with TestClient(create_app(tmp_path, hardware=False), base_url='http://127.0.0.1:8765') as client:
        headers = {'origin': 'http://127.0.0.1:8765'}
        config = client.get('/api/config').json()
        config['widgets'] = [{'id': 'layout', 'kind': 'layout', 'allowOverlap': True,
                              'items': [{'id': 'a'}, {'id': 'b'}]}]
        assert client.put('/api/config', json=config, headers=headers).status_code == 200
        saved = client.get('/api/config').json()
        assert Store(tmp_path).load().widgets[0].allowOverlap is True
        changed = json.loads(json.dumps(saved))
        changed['widgets'][0]['allowOverlap'] = False
        assert client.put('/api/config', json=changed, headers=headers).status_code == 422
        assert client.get('/api/config').json() == saved
        changed['widgets'][0]['items'][1]['column'] = 1
        assert client.put('/api/config', json=changed, headers=headers).status_code == 200


def comparison(source='system'):
    return {'kind': 'comparison', 'source': source, 'path': 'ready', 'operator': 'eq', 'value': True}


def test_title_visibility_defaults_round_trip_and_invalid_save_recovery(tmp_path):
    assert Widget(id='legacy', title='Existing title').showTitle is True
    assert WidgetItem(id='legacy').showTitle is True
    for value in ['false', 0, 1, None, {}]:
        for model in (Widget, WidgetItem):
            with pytest.raises(ValidationError):
                model(id='invalid', showTitle=value)
    with TestClient(create_app(tmp_path, hardware=False), base_url='http://127.0.0.1:8765') as client:
        headers = {'origin': 'http://127.0.0.1:8765'}
        config = client.get('/api/config').json()
        config['widgets'] = [{'id': 'custom', 'kind': 'layout', 'title': 'Saved title', 'showTitle': False,
                              'items': [{'id': 'child', 'kind': 'text', 'title': 'Item title', 'showTitle': False}]}]
        assert client.put('/api/config', json=config, headers=headers).status_code == 200
        saved = client.get('/api/config').json()
        stored = Store(tmp_path).load().widgets[0]
        assert stored.title == 'Saved title' and stored.showTitle is False
        assert stored.items[0].title == 'Item title' and stored.items[0].showTitle is False
        invalid = json.loads(json.dumps(saved))
        invalid['widgets'][0]['items'][0]['showTitle'] = 'false'
        assert client.put('/api/config', json=invalid, headers=headers).status_code == 422
        assert client.get('/api/config').json() == saved
        saved['widgets'][0]['showTitle'] = True
        assert client.put('/api/config', json=saved, headers=headers).status_code == 200
        assert Store(tmp_path).load().widgets[0].showTitle is True


def combined_condition():
    return {'kind': 'or', 'children': [
        {'kind': 'and', 'children': [comparison(), comparison()]},
        {**comparison(), 'negate': True},
    ]}


def test_combined_conditions_round_trip_and_legacy_rules_still_load(tmp_path):
    legacy = WidgetRule(path='ready', value=True)
    combined = WidgetRule(condition=combined_condition(), target='visible', visible=False)
    store = Store(tmp_path)
    config = store.load()
    config.widgets = [Widget(id='grouped', kind='layout', rules=[legacy], items=[
        WidgetItem(id='child', kind='text', rules=[combined])])]
    store.save(config)
    saved = Store(tmp_path).load().widgets[0]
    assert saved.rules[0].condition is None
    assert saved.rules[0].path == 'ready'
    assert saved.items[0].rules[0] == combined
    assert list(combined.sources()) == ['system'] * 3


@pytest.mark.parametrize('condition', [
    {}, {'kind': 'eval'}, {'kind': 'and', 'children': []},
    {'kind': 'or', 'children': [None]}, {'kind': 'and', 'children': [comparison()] * 17},
    {**comparison(), 'negate': 'true'}, {**comparison(), 'operator': 'eval'},
    {**comparison(), 'value': float('inf')}, {**comparison(), 'children': []},
    {'kind': 'or', 'children': [comparison()], 'source': 'system'},
    {'kind': 'or', 'children': [{'kind': 'and', 'children': [comparison()]}] * 16},
])
def test_combined_condition_rejects_malformed_input(condition):
    with pytest.raises(ValidationError):
        WidgetRule(condition=condition)


def test_condition_depth_and_total_node_limits():
    tree = comparison()
    for _ in range(4):
        tree = {'kind': 'and', 'children': [tree]}
    WidgetRule(condition=tree)
    with pytest.raises(ValidationError, match='condition_too_complex'):
        WidgetRule(condition={'kind': 'and', 'children': [tree]})
    cyclic = {'kind': 'and', 'children': []}
    cyclic['children'].append(cyclic)
    with pytest.raises(ValidationError, match='condition_too_complex'):
        WidgetRule(condition=cyclic)
    # Root + 15 two-node groups + one leaf = exactly 32 nodes.
    maximum = {'kind': 'or', 'children': [{'kind': 'and', 'children': [comparison()]} for _ in range(15)] + [comparison()]}
    WidgetRule(condition=maximum)
    maximum['children'][-1] = {'kind': 'and', 'children': [comparison()]}
    with pytest.raises(ValidationError, match='condition_too_complex'):
        WidgetRule(condition=maximum)


def test_nested_source_validation_failed_save_and_recovery(tmp_path):
    with TestClient(create_app(tmp_path, hardware=False), base_url='http://127.0.0.1:8765') as client:
        headers = {'origin': 'http://127.0.0.1:8765'}
        before = client.get('/api/config').json()
        changed = json.loads(json.dumps(before))
        tree = combined_condition()
        tree['children'][0]['children'][1]['source'] = 'unregistered'
        changed['widgets'][0]['rules'] = [{'condition': tree}]
        assert client.put('/api/config', json=changed, headers=headers).status_code == 422
        assert client.get('/api/config').json() == before
        # The same nested references are checked on individual items.
        with pytest.raises(ValidationError, match='unknown_rule_source'):
            Configuration(widgets=[Widget(id='custom', kind='layout', items=[
                WidgetItem(id='child', kind='text', rules=[WidgetRule(condition=tree)])])])
        tree['children'][0]['children'][1]['source'] = 'system'
        assert client.put('/api/config', json=changed, headers=headers).status_code == 200
        saved = client.get('/api/config').json()
        assert saved['widgets'][0]['rules'][0]['condition']['kind'] == 'or'
        changed = json.loads(json.dumps(saved))
        changed['widgets'][0]['rules'][0]['condition'] = {'kind': 'and', 'children': []}
        assert client.put('/api/config', json=changed, headers=headers).status_code == 422
        assert client.get('/api/config').json() == saved
        saved['widgets'][0]['rules'] = []
        assert client.put('/api/config', json=saved, headers=headers).status_code == 200
