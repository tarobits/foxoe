import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from foxoe.models import Widget, WidgetItem
from foxoe.server import create_app

CASES = json.loads(Path(__file__).with_name('formula-cases.json').read_text())


@pytest.mark.parametrize('formula', CASES['valid'])
def test_formula_grammar_accepts_supported_arithmetic(formula):
    assert Widget(id='sample', formula=formula).formula == formula


@pytest.mark.parametrize('formula', CASES['invalid'] + ['('*18+'1'+')'*18, '1+'*70+'1', '1'*513])
def test_formula_grammar_rejects_executable_unbounded_and_invalid_input(formula):
    with pytest.raises(ValidationError):
        Widget(id='sample', formula=formula)


@pytest.mark.parametrize('change', [{'fontWeight': 1000}, {'fontWeight': 'bold'}, {'italic': 'false'}, {'verticalAlign':'left'}, {'decimals':-1}, {'decimals':11}, {'decimals':True}, {'decimals':1.5}])
def test_invalid_formatting_rejected(change):
    with pytest.raises(ValidationError):
        WidgetItem(id='sample', **change)


def test_formatting_round_trip_and_failed_formula_does_not_change_configuration(tmp_path):
    with TestClient(create_app(tmp_path, hardware=False), base_url='http://127.0.0.1:8765') as client:
        headers={'origin':'http://127.0.0.1:8765'}
        config=client.get('/api/config').json()
        config['widgets'][1].update(formula='field("load1") / 2',decimals=3,fontWeight=700,italic=True,verticalAlign='bottom')
        assert client.put('/api/config',json=config,headers=headers).status_code == 200
        saved=client.get('/api/config').json()
        assert saved['widgets'][1]['formula']=='field("load1") / 2'
        invalid=json.loads(json.dumps(saved)); invalid['widgets'][1]['formula']='value.constructor'
        assert client.put('/api/config',json=invalid,headers=headers).status_code==422
        assert client.get('/api/config').json()==saved
        saved['widgets'][1]['formula']='value + 1'
        assert client.put('/api/config',json=saved,headers=headers).status_code==200
