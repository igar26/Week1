from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import pytest
from streamlit.testing.v1 import AppTest
from referee.store import Store
from referee.simple import SimplePlans,invitation_url,text_invitation


def setup(tmp_path):
    store=Store(tmp_path);plans=SimplePlans(store)
    owner,code=store.create_group('Friday friends','Alex')
    plans.save_plan(owner,dict(zip='75201',date='2026-10-23',time='17:00',duration=120,budget=30,interests=['Food'],choices=['Pizza','Park','Coffee']))
    return store,plans,owner,code


def test_invited_members_can_respond_independently_and_persist(tmp_path):
    store,plans,owner,code=setup(tmp_path)
    friend=store.join(code,'Jordan')
    plans.respond(owner,'Can join',['Pizza','Park'],['Food'])
    plans.respond(friend,'Maybe',['Coffee'],['Coffee'])
    assert SimplePlans(Store(tmp_path)).responses(owner)[1]['response']['attendance']=='Maybe'
    assert plans.responses(owner)[0]['response']['choices']==['Pizza','Park']
    assert store.group(owner)['owner']==store.member(owner)['id']
    assert store.member(friend)['id']!=store.member(owner)['id']
    outsider,_=store.create_group('Other group','Blake')
    assert plans.plan(outsider) is None
    assert len(plans.responses(outsider))==1
    with pytest.raises(ValueError):plans.finalize(friend,'Pizza')


def test_finalize_waits_for_responses_and_attending_members_fit(tmp_path):
    store,plans,owner,code=setup(tmp_path);friend=store.join(code,'Jordan')
    plans.respond(owner,'Can join',['Pizza'],['Food'])
    with pytest.raises(ValueError,match='everyone'):plans.finalize(owner,'Pizza')
    plans.respond(friend,'Can join',['Park'],['Outdoors'])
    with pytest.raises(ValueError,match='everyone who can join'):plans.finalize(owner,'Pizza')
    plans.respond(friend,'Cannot join',[],[])
    plans.finalize(owner,'Pizza')
    assert plans.plan(friend)['final_choice']=='Pizza'
    with pytest.raises(ValueError,match='finalized'):store.join(code,'Late arrival')
    with pytest.raises(ValueError,match='finalized'):plans.respond(friend,'Can join',['Pizza'],[])


def test_links_exclude_private_keys_and_sms_is_only_a_draft():
    link=invitation_url('invite-code','https://example.org')
    assert parse_qs(urlsplit(link).query)=={'invite':['invite-code']}
    draft=text_invitation('+1 (212) 555-0123','Friday friends',link)
    assert draft.startswith('sms:+12125550123?')
    assert link in parse_qs(urlsplit(draft).query)['body'][0]
    with pytest.raises(ValueError):text_invitation('not a phone','Group',link)
    with pytest.raises(ValueError):invitation_url('code','http://example.org')
    with pytest.raises(ValueError):invitation_url('code','https://user:secret@example.org')


def test_expired_invitation_still_rejected(tmp_path):
    store,_,_,code=setup(tmp_path)
    with store.db() as conn:conn.execute('UPDATE groups SET invite_expires=?',((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),))
    with pytest.raises(ValueError,match='expired'):store.join(code,'Jordan')


def button(app,label):
    next(b for b in app.button if b.label==label).click().run()
    assert not app.exception and not app.error


def test_simple_create_and_response_need_no_network_or_keys(tmp_path):
    store=Store(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.accounts.identity',return_value={'id':'verified-test-subject','name':'Alex'}),patch('referee.ui.store',return_value=store),patch('requests.request',side_effect=AssertionError('No APIs needed')):
        app=AppTest.from_file(str(appfile)).run()
        button(app,'Plan something good')
        for label,value in [('Group name','Friday friends'),('Your name','Alex'),('Meetup ZIP code','75201')]:
            next(x for x in app.text_input if x.label==label).set_value(value)
        next(x for x in app.text_area if x.label.startswith('Places or activities')).set_value('Pizza\nPark\nCoffee')
        button(app,'Create group')
        key=app.session_state['member_key']
        assert SimplePlans(store).plan(key)['zip']=='75201'
        next(x for x in app.radio if x.label=='Can you join?').set_value('Can join')
        next(x for x in app.checkbox if x.label=='I would enjoy: Pizza').check()
        next(x for x in app.checkbox if x.label=='I would enjoy: Park').check()
        button(app,'Save my response')
        assert SimplePlans(store).responses(key)[0]['response']['choices']==['Pizza','Park']
        assert next(x for x in app.button if x.label=='Prepare text invitation').disabled


def test_invite_link_opens_join_form_and_does_not_sign_in_as_coordinator(tmp_path):
    store,plans,owner,code=setup(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(appfile))
        app.query_params['invite']=code
        app.run()
        assert app.session_state['pending_invite']==code
        assert 'invite' not in app.query_params
        next(x for x in app.text_input if x.key=='simple_join_name').set_value('Jordan')
        button(app,'Join group')
        key=app.session_state['member_key']
        assert store.member(key)['name']=='Jordan'
        assert store.member(key)['id']!=store.group(key)['owner']
        assert plans.plan(key)['zip']=='75201'


def test_preparing_sms_does_not_send_network_request(tmp_path,monkeypatch):
    store,plans,owner,code=setup(tmp_path)
    monkeypatch.setenv('PUBLIC_APP_URL','https://example.org')
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store),patch('requests.post',side_effect=AssertionError('No texts sent by the app')):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=owner
        app.session_state['invite']=code
        app.session_state['page']='Your group'
        app.run()
        next(x for x in app.text_input if x.label.startswith('Friend’s mobile')).set_value('+12125550123')
        button(app,'Prepare text invitation')
        assert any(x.label=='Open your messaging app to send' for x in app.get('link_button'))


def test_tile_selection_recovers_after_empty_vote_and_survives_refresh(tmp_path):
    store,plans,owner,code=setup(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=owner
        app.session_state['invite']=code
        app.session_state['page']='Your group'
        app.run()
        next(x for x in app.radio if x.label=='Can you join?').set_value('Can join')
        button(app,'Save my response')
        assert any('outing tile' in x.value for x in app.warning)
        assert plans.responses(owner)[0]['response'] is None
        next(x for x in app.checkbox if x.label=='I would enjoy: Coffee').check()
        button(app,'Save my response')
        assert plans.responses(owner)[0]['response']['choices']==['Coffee']
        assert any('Selected: Coffee' in x.value for x in app.success)
        button(app,'Refresh responses')
        assert next(x for x in app.checkbox if x.label=='I would enjoy: Coffee').value
        assert not next(x for x in app.checkbox if x.label=='I would enjoy: Pizza').value
        friend=store.join(code,'Jordan')
        app.session_state['member_key']=friend
        app.run()
        assert not next(x for x in app.checkbox if x.label=='I would enjoy: Coffee').value
