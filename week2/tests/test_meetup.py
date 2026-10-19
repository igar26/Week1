from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from referee.store import Store
from referee.simple import SimplePlans
from referee.demo import create_outing_demo
from referee.meetup import Meetups,recommend,VenueAdvice
from referee.codex import AgentError


def ready(tmp_path):
    store=Store(tmp_path);owner,code,keys=create_outing_demo(store)
    plans=SimplePlans(store);activity=plans.plan(owner)['choices'][0]
    plans.finalize(owner,activity)
    meetups=Meetups(plans);meetups.search(owner,'Coffee')
    return store,plans,meetups,owner,keys


def everyone_votes(meetups,plans,keys,chosen=None):
    venues=meetups.current(next(iter(keys.values())))['places']
    for key in keys.values():
        row=next(r for r in plans.responses(key) if r['id']==plans.store.member(key)['id'])
        if row['response']['attendance']!='Cannot join':
            meetups.vote(key,{p['place']['id']:(2 if chosen is None or p['place']['id']==chosen else 1) for p in venues})


def test_second_stage_persists_and_requires_group_venue_agreement(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    venue=meetups.current(owner)['places'][0]['place']['id']
    meetups.open(owner)
    with pytest.raises(ValueError,match='Wait'):meetups.finalize(owner,venue)
    everyone_votes(meetups,plans,keys,venue)
    with pytest.raises(ValueError,match='organizer'):meetups.finalize(list(keys.values())[1],venue)
    meetups.finalize(owner,venue)
    assert Meetups(SimplePlans(Store(tmp_path))).current(owner)['winner']==venue
    with pytest.raises(ValueError):meetups.vote(owner,{p['place']['id']:2 for p in meetups.current(owner)['places']})


def test_veto_and_budget_are_enforced(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    venue=meetups.current(owner)['places'][0]['place']['id']
    meetups.check_details(owner,venue,100,4.5,'https://example.org/menu')
    meetups.open(owner);everyone_votes(meetups,plans,keys)
    assert venue not in {p['place']['id'] for p in meetups.eligible(owner)}
    with pytest.raises(ValueError,match='budget'):meetups.finalize(owner,venue)
    second=meetups.current(owner)['places'][1]['place']['id']
    meetups.vote(list(keys.values())[1],{p['place']['id']:0 for p in meetups.current(owner)['places']})
    assert meetups.eligible(owner)==[]
    with pytest.raises(ValueError,match='Works for me'):meetups.finalize(owner,second)


def test_unknown_details_and_frozen_vote_data(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    venue=meetups.current(owner)['places'][0]['place']['id']
    with pytest.raises(ValueError,match='Source|source'):meetups.check_details(owner,venue,12,4.2,'')
    meetups.check_details(owner,venue,None,None,'')
    assert meetups.current(owner)['places'][0]['place']['rating'] is None
    meetups.open(owner)
    with pytest.raises(ValueError,match='frozen'):meetups.check_details(owner,venue,12,4.2,'https://example.org')
    with pytest.raises(ValueError,match='already open'):meetups.search(owner,'Coffee')
    with pytest.raises(ValueError,match='might join'):meetups.vote(list(keys.values())[-1],{})
    outsider,_=store.create_group('Other group','Other owner')
    assert meetups.current(outsider) is None
    assert meetups.ballots(outsider)=={}


def test_demo_recommendation_is_offline_and_not_finalization(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    meetups.open(owner)
    with patch('referee.meetup.ask',side_effect=AssertionError('No model call')):
        answer=recommend(meetups,owner)
    assert answer['demo']
    assert meetups.current(owner)['status']=='voting'


def test_real_analysis_needs_consent_and_rejects_unsupported_venue(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    # Test real-model gates using a fixture round without any network discovery.
    with store.db() as c:c.execute('UPDATE groups SET demo=0 WHERE id=?',(store.group(owner)['id'],))
    meetups.open(owner)
    with patch('referee.meetup.ask') as ask:
        with pytest.raises(ValueError,match='allow group analysis'):recommend(meetups,owner)
        ask.assert_not_called()
    for key in keys.values():plans.set_analysis_consent(key,True)
    with patch('referee.meetup.ask',return_value=VenueAdvice(venue_id='invented',summary='Wrong',reasons=[],questions=[])):
        with pytest.raises(AgentError,match='unsupported'):recommend(meetups,owner)


def test_current_demo_same_page_venue_tiles_and_voting(tmp_path):
    store=Store(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store),patch('requests.request',side_effect=AssertionError('Demo offline')):
        app=AppTest.from_file(str(appfile)).run()
        def click(label):
            next(b for b in app.button if b.label==label).click().run()
            assert not app.exception and not app.error
        click('Try the Dallas demo');click('Finalize choice');click('Find meetup venues')
        assert any(x.value=='Moonlight Social (fictional)' for x in app.text)
        click('Let everyone vote on these venues')
        for radio in app.radio:
            if radio.label.startswith('Your choice for'):radio.set_value('Works for me')
        click('Save my venue choices')
        owner=app.session_state['member_key'];plans=SimplePlans(store);meetups=Meetups(plans)
        everyone_votes(meetups,plans,app.session_state['demo_keys'])
        click('Refresh responses');click('Suggest the best venue')
        click('Confirm agreed meetup venue')
        assert meetups.current(owner)['status']=='finalized'
        assert any('Meetup venue agreed:' in x.value for x in app.success)


def test_real_search_uses_agreed_activity_zip_and_category(tmp_path):
    from referee.models import Place
    store,plans,meetups,owner,keys=ready(tmp_path)
    meetups.restart(owner)
    with store.db() as c:c.execute('UPDATE groups SET demo=0 WHERE id=?',(store.group(owner)['id'],))
    place=Place(id='real-listing',name='A listed cafe',category='Restaurant',lat=32.79,lon=-96.8,source='Geoapify',address='Example address')
    with patch('referee.nearby.find_places',return_value={'places':[{'place':place.model_dump(),'miles':1.1}]}) as find:
        meetups.search(owner,'Coffee')
    find.assert_called_once_with('75201',categories=['catering.cafe'])
    candidate=meetups.current(owner)['places'][0]
    assert candidate['place']['rating'] is None and candidate['place']['cost'] is None
    meetups.check_details(owner,place.id,15,4.3,'https://example.org/menu')
    assert meetups.current(owner)['places'][0]['checked_source']=='https://example.org/menu'


def test_venue_restart_clears_ballots_but_preserves_activity(tmp_path):
    store,plans,meetups,owner,keys=ready(tmp_path)
    meetups.open(owner);everyone_votes(meetups,plans,keys)
    old_id=meetups.current(owner)['id']
    activity=plans.plan(owner)['final_choice']
    with pytest.raises(ValueError,match='organizer'):meetups.restart(list(keys.values())[1])
    meetups.restart(owner)
    assert meetups.current(owner) is None and meetups.ballots(owner)=={}
    assert plans.plan(owner)['final_choice']==activity
    meetups.search(owner,'Coffee')
    assert meetups.current(owner)['id']!=old_id


def test_consent_change_preserves_votes_but_invalidates_ai_results(tmp_path):
    from referee.meetup import venue_signature
    store,plans,meetups,owner,keys=ready(tmp_path)
    meetups.open(owner);everyone_votes(meetups,plans,keys)
    before=recommend(meetups,owner)
    votes=meetups.ballots(owner)
    plans.set_analysis_consent(owner,True)
    assert meetups.ballots(owner)==votes
    assert before['signature']!=venue_signature({'round':meetups.current(owner),'responses':plans.responses(owner)},votes)


def test_individual_budget_blocks_venue_even_with_unanimous_yes(tmp_path):
    store=Store(tmp_path);owner,code,keys=create_outing_demo(store)
    plans=SimplePlans(store)
    other=list(keys.values())[1]
    mine=next(r['response'] for r in plans.responses(other) if r['id']==store.member(other)['id'])
    plans.respond(other,mine['attendance'],mine['choices'],mine['interests'],budget=15)
    plans.finalize(owner,plans.plan(owner)['choices'][0])
    meetups=Meetups(plans);meetups.search(owner,'Coffee');meetups.open(owner)
    everyone_votes(meetups,plans,keys)
    expensive=meetups.current(owner)['places'][1]['place']['id']  # $22, below event $30 but above member $15
    affordable=meetups.current(owner)['places'][2]['place']['id']  # $8
    assert expensive not in {p['place']['id'] for p in meetups.eligible(owner)}
    with pytest.raises(ValueError,match='budget'):meetups.finalize(owner,expensive)
    meetups.finalize(owner,affordable)
    assert meetups.current(owner)['winner']==affordable
