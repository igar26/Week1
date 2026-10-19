from urllib.parse import urlsplit, parse_qs
from referee.itinerary import meeting_details, maps_links, duration_label
from referee.models import Place


def session(**updates):
    value={'start':'2026-10-17T23:30:00-05:00','timezone':'America/Chicago',
           'duration':120,'options':[],'winner':None,'status':'voting','booked_at':None}
    return value | updates


def test_duration_and_midnight():
    details=meeting_details(session())
    assert details['duration']=='2 hours'
    assert details['end'].day==18
    assert duration_label(90)=='1 hour 30 minutes'
    assert details['place'] is None


def test_elapsed_time_across_daylight_saving():
    details=meeting_details(session(start='2026-11-01T00:30:00-05:00',duration=180))
    assert details['end'].hour==2
    assert details['end'].tzname()=='CST'


def test_booking_status_is_explicit():
    assert 'reservation pending' in meeting_details(session(status='finalized'))['status']
    assert 'Booked' in meeting_details(session(status='finalized',booked_at='2026-10-01'))['status']


def test_maps_are_destination_only_and_demo_has_no_fake_route():
    place=Place(id='venue',name='A & B',category='Restaurant',lat=32.78,lon=-96.8,
                address='123 Main St, Dallas, TX',source='Organizer')
    links=maps_links(place)
    params=parse_qs(urlsplit(links['Get directions']).query)
    assert params=={'api':['1'],'destination':['A & B, 123 Main St, Dallas, TX']}
    assert maps_links(place.model_copy(update={'synthetic':True}))=={}
    assert '32.78,-96.8' in parse_qs(urlsplit(maps_links(place.model_copy(update={'address':''}))['Get directions']).query)['destination']
