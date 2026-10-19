import io
import json
from datetime import datetime
import pytest
from PIL import Image
from referee.store import Store
from referee.catalog import demo_places
from referee.decision import rank_options,DALLAS_TZ


@pytest.fixture
def demo(tmp_path):
    store=Store(tmp_path)
    key,invite,keys=store.create_demo()
    options,_=rank_options(store.profiles(key),demo_places(),datetime(2026,10,18,17,tzinfo=DALLAS_TZ),120)
    sid=store.start_poll(key,'A Sunday together',datetime(2026,10,18,17,tzinfo=DALLAS_TZ),120,options)
    return store,key,invite,keys,sid,options


def test_group_keys_and_cross_group_isolation(demo):
    store,key,invite,keys,sid,options=demo
    other,_=store.create_group('Other group','Other person')
    with pytest.raises(ValueError):store.get_session(other,sid)
    with pytest.raises(ValueError):store.member('bad-key')
    with store.db() as c:
        hashes=[r[0] for r in c.execute('SELECT key_hash FROM members')]
    assert key not in hashes
    assert all(len(x)==64 for x in hashes)
    with pytest.raises(ValueError):store.join(invite,'Unexpected guest')


def test_poll_waits_for_everyone_and_one_editable_ballot(demo):
    store,key,invite,keys,sid,options=demo
    ballot={p.place.id:2 for p in options}
    store.vote(key,sid,ballot);store.vote(key,sid,ballot)
    assert len(store.ballots(key,sid))==3
    with pytest.raises(ValueError):store.close_poll(key,sid)
    for k in keys.values():store.vote(k,sid,ballot)
    assert len(store.ballots(key,sid))==12
    store.close_poll(key,sid)
    assert store.session(key)['status']=='confirming'
    with pytest.raises(ValueError):store.complete(key,sid)
    for i,k in enumerate(keys.values()):
        store.confirm(k,sid)
        assert store.session(key)['status']==('finalized' if i==3 else 'confirming')
    with pytest.raises(ValueError):store.vote(key,sid,ballot)


def test_veto_and_no_consensus(demo):
    store,key,invite,keys,sid,options=demo
    for k in keys.values():store.vote(k,sid,{p.place.id:0 for p in options})
    with pytest.raises(ValueError,match='No consensus'):store.close_poll(key,sid)
    for k in keys.values():store.vote(k,sid,{p.place.id:(0 if i==0 else 2) for i,p in enumerate(options)})
    assert store.close_poll(key,sid)==options[1].place.id


def complete_demo(demo):
    store,key,invite,keys,sid,options=demo
    for k in keys.values():store.vote(k,sid,{p.place.id:2 for p in options})
    store.close_poll(key,sid)
    for k in keys.values():store.confirm(k,sid)
    store.complete(key,sid)


def test_scrapbook_ownership_photo_validation_and_deletion(demo):
    store,key,invite,keys,sid,options=demo
    with pytest.raises(ValueError):store.add_memory(key,sid,'Too early',5,True,[])
    complete_demo(demo)
    photo=io.BytesIO();image=Image.new('RGB',(30,20),'orange');exif=Image.Exif();exif[270]='private metadata'
    image.save(photo,format='JPEG',exif=exif)
    mid=store.add_memory(key,sid,'Good company',5,True,[photo.getvalue()])
    saved=store.memories(key)[0];pid=saved['photos'][0]['id']
    clean=Image.open(io.BytesIO(store.photo_bytes(key,pid)))
    assert not clean.getexif()
    other,_=store.create_group('Other','Other')
    with pytest.raises(ValueError):store.photo_bytes(other,pid)
    another=list(keys.values())[1]
    with pytest.raises(ValueError):store.delete_memory(another,mid)
    with pytest.raises(ValueError):store.add_memory(key,sid,'Bad photo',5,True,[b'not a photo'])
    assert len(store.memories(key))==1
    store.delete_memory(key,mid)
    assert store.memories(key)==[]
    assert list(store.photos_dir.iterdir())==[]


def test_only_owner_can_reset_and_frozen_profiles_cannot_change(demo):
    store,key,invite,keys,sid,options=demo
    other=list(keys.values())[1]
    with pytest.raises(ValueError):store.reset_round(other)
    with pytest.raises(ValueError):store.save_profile(key,store.profiles(key)[0])
    store.reset_round(key)
    assert store.session(key) is None
    store.save_profile(key,store.profiles(key)[0])


def test_group_and_access_survive_store_restart(tmp_path):
    first=Store(tmp_path)
    owner,invite=first.create_group('Persistent friends','Coordinator')
    second=Store(tmp_path)
    assert second.group(owner)['name']=='Persistent friends'
    member=second.join(invite,'New friend')
    third=Store(tmp_path)
    assert len(third.roster(member))==2
    assert third.group(member)['id']==third.group(owner)['id']


def test_only_coordinator_can_replace_invite_without_losing_members(tmp_path):
    store=Store(tmp_path)
    owner,old=store.create_group('Circle','Coordinator')
    member=store.join(old,'Friend')
    with pytest.raises(ValueError):store.rotate_invitation(member)
    new=store.rotate_invitation(owner)
    with pytest.raises(ValueError):store.join(old,'Someone else')
    resumed=Store(tmp_path)
    another=resumed.join(new,'Another friend')
    assert len(resumed.roster(another))==3
    assert resumed.member(member)['name']=='Friend'
    assert resumed.owner(owner)['name']=='Coordinator'
