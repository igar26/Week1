from datetime import date,datetime,time
from zoneinfo import ZoneInfo
from unittest.mock import patch
import pytest
from referee.geography import search_us,starters,local_start,session_moment
from referee.catalog import demo_profiles,demo_places
from referee.decision import rank_options,hours_status
from referee.providers import google,weather
from referee.sms import message_body


def test_search_us_filters_country_and_preserves_state_and_timezone():
    rows={'results':[
        {'name':'Portland','admin1':'Oregon','admin2':'Multnomah County','latitude':45.52,'longitude':-122.67,'timezone':'America/Los_Angeles','country_code':'US'},
        {'name':'Portland','admin1':'Victoria','latitude':-38.34,'longitude':141.6,'timezone':'Australia/Melbourne','country_code':'AU'}]}
    with patch('referee.geography.fetch',return_value=rows) as fetch:
        result=search_us('Portland, OR')
    assert len(result)==1
    assert result[0]['timezone']=='America/Los_Angeles'
    assert result[0]['state']=='Oregon'
    assert fetch.call_args.kwargs['params']['countryCode']=='US'
    assert fetch.call_args.kwargs['params']['name']=='Portland, OR'


def test_offline_starters_include_alaska_hawaii_and_multiple_zones():
    rows=starters()
    assert any(r['state']=='Alaska' for r in rows)
    assert any(r['state']=='Hawaii' for r in rows)
    assert len({r['timezone'] for r in rows})>=6
    with pytest.raises(ValueError):search_us('x')


def test_non_central_venue_hours_and_person_availability():
    people=demo_profiles()
    for p in people:
        p.timezone='America/Los_Angeles';p.available_from='16:00';p.available_until='18:00'
    place=demo_places()[0].model_copy(update={'timezone':'America/Chicago','hours':'Mo-Su 19:00-22:00'})
    start=local_start(date(2026,10,18),time(17),'America/Los_Angeles')
    assert rank_options(people,[place],start,60)[0]
    people[0].timezone='America/New_York'
    assert not rank_options(people,[place],start,60)[0]
    assert hours_status('Mo-Su 17:00-19:00',start,60)=='open'


@pytest.mark.parametrize('day,clock',[ (date(2026,3,8),time(2,30)),(date(2026,11,1),time(1,30)) ])
def test_dst_ambiguous_and_nonexistent_times_rejected(day,clock):
    with pytest.raises(ValueError):local_start(day,clock,'America/New_York')


def test_frozen_session_and_booking_sms_preserve_venue_zone():
    start=local_start(date(2026,10,18),time(17),'Pacific/Honolulu')
    session={'start':start.isoformat(),'timezone':'Pacific/Honolulu','winner':'p1','options':[{'place':{'id':'p1','name':'Island cafe'}}],'people':[{},{}]}
    assert session_moment(session).hour==17
    assert '05:00 PM HST' in message_body(session)
    # Old saved sessions keep their former Central interpretation.
    assert str(session_moment({'start':'2026-10-18T17:00:00-05:00'}).tzinfo)=='America/Chicago'


def test_google_search_does_not_override_selected_geography_with_dallas():
    with patch.dict('os.environ',{'GOOGLE_PLACES_API_KEY':'fake'}),patch('referee.providers.fetch',return_value={'places':[]}) as fetch:
        google(47.6,-122.3)
    payload=fetch.call_args.kwargs['json']
    assert 'Dallas' not in payload['textQuery']
    assert payload['locationBias']['circle']['center']['latitude']==47.6
