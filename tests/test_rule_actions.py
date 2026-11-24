import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from foxoe.models import Widget, WidgetItem, WidgetRule
from foxoe.server import create_app
from foxoe.store import Store


@pytest.mark.parametrize('actions', [[], [{}], [{'target':'eval'}], [{'target':'visible','visible':'false'}],
    [{'target':'text','text':None}], [{'target':'text','text':1}], [{'target':'text','text':'x'*1001}],
    [{'target':'title','text':'x'*61}], [{'target':'textColor','color':'url(evil)'}],
    [{'target':'text','text':'hello','color':'#ffffff'}], [{'target':'visible'}],
    [{'target':'icon'}], [{'target':'icon','icon':''}], [{'target':'icon','icon':'__proto__'}],
    [{'target':'icon','icon':'https://evil.test/icon.svg'}], [{'target':'icon','icon':False}],
    [{'target':'icon','icon':'user','text':'unexpected'}],
    [{'target':'visible','visible':True}]*17])
def test_invalid_rule_actions_are_rejected(actions):
    with pytest.raises(ValidationError):
        WidgetRule(actions=actions)


def test_text_actions_require_text_or_value_content():
    rule = WidgetRule(actions=[{'target':'text','text':''}])
    for model in (Widget, WidgetItem):
        for kind in ('text','value'):
            model(id='sample',kind=kind,rules=[rule])
        for kind in ('icon','clock','list'):
            with pytest.raises(ValidationError,match='text_action_requires'):
                model(id='sample',kind=kind,rules=[rule])
    assert WidgetRule().actions is None
    assert len(WidgetRule(actions=[{'target':'visible','visible':True}]*16).actions)==16


def test_multiple_actions_round_trip_and_failed_save_recovers(tmp_path):
    with TestClient(create_app(tmp_path,hardware=False),base_url='http://127.0.0.1:8765') as client:
        headers={'origin':'http://127.0.0.1:8765'}
        config=client.get('/api/config').json()
        actions=[{'target':'text','text':'Ready'},{'target':'title','text':'Status'},
                 {'target':'textColor','color':'#00ff00'},{'target':'visible','visible':True}]
        config['widgets'][1]['rules']=[{'source':'system','path':'load1','operator':'gte','value':0,'actions':actions}]
        assert client.put('/api/config',json=config,headers=headers).status_code==200
        saved=client.get('/api/config').json()
        assert [a.model_dump() for a in Store(tmp_path).load().widgets[1].rules[0].actions]==actions
        invalid=json.loads(json.dumps(saved)); invalid['widgets'][1]['rules'][0]['actions'][1]['target']='__proto__'
        assert client.put('/api/config',json=invalid,headers=headers).status_code==422
        assert client.get('/api/config').json()==saved
        saved['widgets'][1]['rules'][0]['actions'][0]['text']=''
        assert client.put('/api/config',json=saved,headers=headers).status_code==200


def test_icon_actions_require_icon_content():
    for icon in ('user','foxoe',None):
        rule=WidgetRule(actions=[{'target':'icon','icon':icon}])
        for model in (Widget,WidgetItem):
            model(id='sample',kind='icon',rules=[rule])
            for kind in ('text','value','clock','list'):
                with pytest.raises(ValidationError,match='icon_action_requires_icon'):
                    model(id='sample',kind=kind,rules=[rule])
        with pytest.raises(ValidationError,match='icon_action_requires_icon'):
            Widget(id='sample',kind='layout',rules=[rule])


def test_icon_actions_round_trip_on_nested_items_and_recover_after_invalid_save(tmp_path):
    with TestClient(create_app(tmp_path,hardware=False),base_url='http://127.0.0.1:8765') as client:
        headers={'origin':'http://127.0.0.1:8765'}
        config=client.get('/api/config').json()
        actions=[{'target':'icon','icon':'user'},{'target':'iconColor','color':'#00ff00'}]
        config['widgets']=[Widget(id='layout',kind='layout',items=[WidgetItem(id='symbol',kind='icon',rules=[WidgetRule(actions=actions)])]).model_dump()]
        response=client.put('/api/config',json=config,headers=headers)
        assert response.status_code==200
        saved=client.get('/api/config').json()
        assert [a.model_dump() for a in Store(tmp_path).load().widgets[0].items[0].rules[0].actions]==actions
        invalid=json.loads(json.dumps(saved)); invalid['widgets'][0]['items'][0]['kind']='text'
        assert client.put('/api/config',json=invalid,headers=headers).status_code==422
        assert client.get('/api/config').json()==saved
        saved['widgets'][0]['items'][0]['rules'][0]['actions'][0]['icon']=None
        assert client.put('/api/config',json=saved,headers=headers).status_code==200
        assert Store(tmp_path).load().widgets[0].items[0].rules[0].actions[0].icon is None
