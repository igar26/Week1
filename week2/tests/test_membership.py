import io
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest
from referee.store import Store
from referee.simple import SimplePlans
from referee.demo import create_outing_demo
from referee.meetup import Meetups


def photo():
    data=io.BytesIO();Image.new('RGB',(12,12),'orange').save(data,format='PNG');return data.getvalue()


def group(tmp_path):
    store=Store(tmp_path);owner,code=store.create_group('Friends','Alex');friend=store.join(code,'Jordan')
    plans=SimplePlans(store)
    plans.save_plan(owner,dict(zip='75078',date='2026-10-25',time='18:00',duration=120,budget=30,interests=['Coffee'],choices=['Coffee','Park']))
    for key in [owner,friend]:plans.respond(key,'Can join',['Coffee'],['Coffee'])
    sid=store.add_past_adventure(owner,'Our afternoon',datetime.now(ZoneInfo('America/Chicago')).date().isoformat())
    return store,plans,owner,friend,code,sid


def test_leaving_revokes_access_and_optionally_deletes_only_own_memories(tmp_path):
    store,plans,owner,friend,code,sid=group(tmp_path)
    own_memory=store.add_memory(owner,sid,'Owner memory',5,True,[photo()])
    friend_memory=store.add_memory(friend,sid,'Friend memory',5,True,[photo()])
    friend_photo=next(m for m in store.memories(owner) if m['id']==friend_memory)['photos'][0]['id']
    store.leave_group(friend,delete_memories=True)
    assert len(store.roster(owner))==1
    assert [m['id'] for m in store.memories(owner)]==[own_memory]
    assert len(list(store.photos_dir.glob('*.jpg')))==1
    with pytest.raises(ValueError):store.member(friend)
    with pytest.raises(ValueError):store.photo_bytes(friend,friend_photo)
    with pytest.raises(ValueError):store.add_memory(friend,sid,'No access',5,True,[])
    assert len(plans.responses(owner))==1


def test_coordinator_must_transfer_and_kept_memories_stay_shared(tmp_path):
    store,plans,owner,friend,code,sid=group(tmp_path)
    store.add_memory(owner,sid,'Kept for everyone',5,True,[photo()])
    with pytest.raises(ValueError,match='coordinator'):store.leave_group(owner)
    assert store.owner(owner)
    outsider,_=store.create_group('Other group','Other owner')
    with pytest.raises(ValueError):store.leave_group(owner,successor=store.member(outsider)['id'])
    store.leave_group(owner,successor=store.member(friend)['id'])
    assert store.owner(friend)
    assert store.memories(friend)[0]['caption']=='Kept for everyone'
    with pytest.raises(ValueError):store.member(owner)


def test_last_member_leave_closes_old_invitation(tmp_path):
    store=Store(tmp_path);owner,code=store.create_group('Solo','Alex')
    store.leave_group(owner)
    with pytest.raises(ValueError):store.join(code,'Jordan')
    with pytest.raises(ValueError):store.member(owner)


def test_departure_reopens_unfinished_activity_without_blocked_votes(tmp_path):
    store,plans,owner,friend,code,sid=group(tmp_path)
    plans.finalize(owner,'Coffee')
    store.leave_group(friend)
    assert plans.plan(owner)['final_choice']==''
    plans.finalize(owner,'Coffee')
    assert plans.plan(owner)['final_choice']=='Coffee'


def test_agreed_venue_survives_member_departure(tmp_path):
    store=Store(tmp_path);owner,code,keys=create_outing_demo(store);plans=SimplePlans(store)
    plans.finalize(owner,plans.plan(owner)['choices'][0]);meetups=Meetups(plans)
    meetups.search(owner,'Coffee');meetups.open(owner)
    for key in keys.values():
        row=next(r for r in plans.responses(key) if r['id']==store.member(key)['id'])
        if row['response']['attendance']!='Cannot join':meetups.vote(key,{p['place']['id']:2 for p in meetups.current(key)['places']})
    meetups.finalize(owner,meetups.current(owner)['places'][0]['place']['id'])
    successor=list(keys.values())[1]
    store.leave_group(owner,successor=store.member(successor)['id'])
    assert meetups.current(successor)['status']=='finalized'
    assert plans.plan(successor)['final_choice']
    assert store.owner(successor)


def test_member_leave_control_clears_browser_access(tmp_path):
    store,plans,owner,friend,code,sid=group(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=friend;app.session_state['page']='Your group';app.run()
        assert next(b for b in app.button if b.label=='Leave group').disabled
        next(x for x in app.checkbox if x.label=='I understand and want to leave this group').check().run()
        next(b for b in app.button if b.label=='Leave group').click().run()
        assert not app.exception and not app.error
        assert app.session_state['page']=='Home'
        with pytest.raises(ValueError):store.member(friend)


def test_another_members_gallery_sees_new_photo_and_departed_session_loses_access(tmp_path):
    store,plans,owner,friend,code,sid=group(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=friend;app.session_state['page']='Our adventures';app.run()
        assert not any('data:image/jpeg;base64,' in x.value for x in app.get('html'))
        store.add_memory(owner,sid,'New shared photo',5,True,[photo()])
        app.run()
        assert any('data:image/jpeg;base64,' in x.value for x in app.get('html'))
        assert any('Gallery updates about every 5 seconds' in x.value for x in app.caption)
        store.leave_group(friend)
        app.run()
        assert not app.exception and not app.error
        assert app.session_state['page']=='Home'
        assert not any('data:image/jpeg;base64,' in x.value for x in app.get('html'))


def test_departure_clears_unfinished_venue_round_and_its_ballots(tmp_path):
    store=Store(tmp_path);owner,code,keys=create_outing_demo(store);plans=SimplePlans(store)
    plans.finalize(owner,plans.plan(owner)['choices'][0]);meetups=Meetups(plans)
    meetups.search(owner,'Coffee');meetups.open(owner)
    meetups.vote(owner,{p['place']['id']:2 for p in meetups.current(owner)['places']})
    store.leave_group(list(keys.values())[1])
    assert meetups.current(owner) is None
    assert meetups.ballots(owner)=={}
    assert plans.plan(owner)['final_choice']==''
