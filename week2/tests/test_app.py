from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from referee.store import Store
from referee.catalog import demo_places
from referee.decision import rank_options,DALLAS_TZ
from datetime import datetime

APP=Path(__file__).resolve().parents[1]/'streamlit_app.py'


@pytest.fixture
def app(tmp_path):
    store=Store(tmp_path)
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        yield app,store


def click(app,label):
    next(b for b in app.button if b.label==label).click().run()
    assert not app.exception
    assert not app.error,[e.value for e in app.error]


def test_landing_help_and_every_help_tab(app):
    at,store=app
    assert any('Different people.' in x.value for x in at.get('html'))
    click(at,'Help')
    assert len(at.tabs)==4
    assert any('Architecture'==t.label for t in at.tabs)


def test_demo_uses_tiles_rsvps_and_common_ground(app):
    from referee.simple import SimplePlans
    at,store=app
    with patch('requests.request',side_effect=AssertionError('Demo must stay offline')),patch('referee.common_ground.ask',side_effect=AssertionError('Sample must not call LLM')):
        click(at,'Try the Dallas demo')
        owner=at.session_state['member_key']
        plans=SimplePlans(store)
        assert plans.plan(owner)['zip']=='75201'
        assert len(plans.responses(owner))==4
        assert any(x.label=='I would enjoy: Coffee and catch-up (demo)' for x in at.checkbox)
        assert not any(x.label=='Discover our options' for x in at.button)
        click(at,'Find our common ground')
        assert any(x.value=='Suggested choice: Coffee and catch-up (demo)' for x in at.text)
        assert any('Sample explanation from demo rules' in x.value for x in at.caption)
        assert plans.plan(owner)['final_choice']==''
        click(at,'Save my response')
        selector=next(x for x in at.selectbox if x.label=='Demo: view as a friend')
        other=list(at.session_state['demo_keys'])[1]
        selector.select(other).run()
        assert not at.exception and not at.error
        assert not any(b.label=='Finalize choice' for b in at.button)
        next(x for x in at.selectbox if x.label=='Demo: view as a friend').select(store.member(owner)['id']).run()
        click(at,'Finalize choice')
        assert plans.plan(owner)['final_choice']=='Coffee and catch-up (demo)'


def test_finalized_plan_and_scrapbook_screen(app):
    at,store=app
    key,invite,keys=store.create_demo()
    options,_=rank_options(store.profiles(key),demo_places(),datetime(2026,10,18,17,tzinfo=DALLAS_TZ),120)
    sid=store.start_poll(key,'Friends together',datetime(2026,10,18,17,tzinfo=DALLAS_TZ),120,options)
    for k in keys.values():store.vote(k,sid,{p.place.id:2 for p in options})
    store.close_poll(key,sid)
    for k in keys.values():store.confirm(k,sid)
    at.session_state['member_key']=key;at.session_state['page']='The vote';at.run()
    assert not at.exception and not at.error
    assert any('reservation has not been made' in x.value for x in at.success)
    store.complete(key,sid)
    store.add_memory(key,sid,'Best afternoon',5,True,[])
    click(at,'Our adventures')
    assert any('Friends together'==x.value for x in at.subheader)


def test_us_location_picker_saves_non_dallas_profile(app):
    at,store=app
    key,invite=store.create_group('West coast friends','Casey')
    at.session_state['member_key']=key;at.session_state['page']='Your group';at.run()
    assert not at.exception and not at.error
    picker=next(x for x in at.selectbox if x.label=='Starting city / area')
    picker.select('Seattle, Washington').run()
    assert not any('Allow my' in x.label or 'I have reviewed' in x.label for x in at.checkbox)
    click(at,'Save my profile')
    profile=store.profiles(key)[0]
    assert profile.reviewed
    assert not profile.ai_consent and not profile.graph_consent
    assert profile.city=='Seattle, Washington'
    assert profile.timezone=='America/Los_Angeles'
    assert abs(profile.lat-47.6062)<.001


def test_rejoin_restores_coordinator_and_replacement_invitation_controls(app):
    at,store=app
    owner,invite=store.create_group('Saved circle','Coordinator')
    at.session_state['page']='Your group';at.run()
    next(x for x in at.text_input if x.label=='Your private return key').set_value(owner)
    click(at,'Return to my group')
    assert at.session_state['member_key']==owner
    click(at,'Generate a new invitation code')
    assert at.session_state['invite']!=invite
    with pytest.raises(ValueError):store.join(invite,'New friend')
    assert not at.get('download_button')
    assert any('password manager' in x.value for x in at.caption)


def test_demo_is_labeled_and_has_no_private_key_or_real_text_send(app):
    at,store=app
    click(at,'Try the Dallas demo')
    assert any('Dallas demo' in x.value for x in at.info)
    assert next(b for b in at.button if b.label=='Prepare text invitation').disabled
    assert not any(x.label=='Return later / leave this browser' for x in at.expander)
    assert not any(x.value==at.session_state['member_key'] for x in at.code)
