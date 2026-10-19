import io
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest
from referee.store import Store
from referee.simple import SimplePlans
from referee.demo import create_outing_demo
from referee.meetup import Meetups


def outing(tmp_path):
    store=Store(tmp_path);owner,code,keys=create_outing_demo(store);plans=SimplePlans(store)
    plans.finalize(owner,plans.plan(owner)['choices'][0])
    meetup=Meetups(plans);meetup.search(owner,'Coffee');meetup.open(owner)
    for key in keys.values():
        response=next(r['response'] for r in plans.responses(key) if r['id']==store.member(key)['id'])
        if response['attendance']!='Cannot join':meetup.vote(key,{p['place']['id']:2 for p in meetup.current(key)['places']})
    meetup.finalize(owner,meetup.current(owner)['places'][0]['place']['id'])
    return store,meetup,owner,keys


def image_bytes():
    content=io.BytesIO();Image.new('RGB',(20,20),'blue').save(content,format='PNG');return content.getvalue()


def test_simple_completed_outing_supports_private_photos_and_completion_is_idempotent(tmp_path):
    store,meetup,owner,keys=outing(tmp_path)
    friend=list(keys.values())[1]
    with pytest.raises(ValueError,match='organizer'):meetup.complete(friend)
    sid=meetup.complete(owner)
    assert meetup.complete(owner)==sid
    assert len(store.completed_sessions(owner))==1
    memory=store.add_memory(friend,sid,'A good evening',5,True,[image_bytes()])
    saved=Store(tmp_path).memories(owner)[0]
    assert saved['id']==memory and saved['photos']
    assert store.photo_bytes(owner,saved['photos'][0]['id']).startswith(b'\xff\xd8')
    other,_=store.create_group('Other group','Other person')
    with pytest.raises(ValueError):store.photo_bytes(other,saved['photos'][0]['id'])
    with pytest.raises(ValueError):store.delete_memory(owner,memory)
    store.delete_memory(friend,memory)
    assert not store.memories(owner)


def test_current_flow_reveals_upload_and_renders_saved_photo(tmp_path):
    store,meetup,owner,keys=outing(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=owner;app.session_state['page']='Our adventures';app.run()
        assert not app.exception and not app.error
        assert next(x for x in app.get('file_uploader')).disabled
        next(x for x in app.checkbox if x.label=='This outing has taken place and is ready for our photos').check().run()
        next(b for b in app.button if b.label=='Mark adventure completed').click().run()
        assert not app.exception and not app.error
        assert not next(x for x in app.get('file_uploader')).disabled
        sid=store.completed_sessions(owner)[0]['id']
        store.add_memory(owner,sid,'Happy memories',5,True,[image_bytes()])
        app.run()
        assert any('data:image/jpeg;base64,' in x.value for x in app.get('html'))
        assert any(x.value=='Happy memories' for x in app.markdown)


def test_past_adventure_can_be_added_without_a_places_connection(tmp_path):
    store=Store(tmp_path);owner,code=store.create_group('Friends','Alex');friend=store.join(code,'Jordan')
    today=datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
    with pytest.raises(ValueError,match='organizer'):store.add_past_adventure(friend,'Our day',today)
    sid=store.add_past_adventure(owner,'Our day',today)
    store.add_memory(friend,sid,'Lovely afternoon',4,True,[image_bytes()])
    assert store.memories(owner)[0]['title']=='Our day'


def test_past_adventure_ui_enables_upload_without_network(tmp_path):
    store=Store(tmp_path);owner,invite=store.create_group('Friends','Alex')
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store),patch('requests.request',side_effect=AssertionError('No provider needed')):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=owner;app.session_state['page']='Our adventures';app.run()
        next(x for x in app.text_input if x.label=='Adventure name').set_value('Our picnic')
        next(x for x in app.checkbox if x.label=='This is a past group outing').check()
        next(b for b in app.button if b.label=='Create adventure for photos').click().run()
        assert not app.exception and not app.error
        assert not next(x for x in app.get('file_uploader')).disabled
        assert any(x.value=='Add photos and memories' for x in app.subheader)
