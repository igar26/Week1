from datetime import datetime
from unittest.mock import patch,Mock
import pytest
import requests
from referee.store import Store
from referee.catalog import demo_places
from referee.models import Profile
from referee.decision import rank_options,DALLAS_TZ
from referee.sms import notify_booking,refresh_statuses,SMSError,message_body

ENV={'SMS_ENABLED':'true','TWILIO_ACCOUNT_SID':'AC'+'a'*32,'TWILIO_AUTH_TOKEN':'fake-test-token','TWILIO_FROM_NUMBER':'+12125550100'}


@pytest.fixture
def booking(tmp_path):
    store=Store(tmp_path)
    owner,invite=store.create_group('Real local group','Alice')
    other=store.join(invite,'Bob')
    for key in [owner,other]:
        m=store.member(key)
        store.save_profile(key,Profile(id=m['id'],name=m['name'],city='Dallas',lat=32.77,lon=-96.79,budget=40,interests=['Food'],reviewed=True))
    places=[p.model_copy(update={'synthetic':False}) for p in demo_places()[:3]]
    start=datetime(2026,10,18,17,tzinfo=DALLAS_TZ)
    options,_=rank_options(store.profiles(owner),places,start,120)
    sid=store.start_poll(owner,'Dinner',start,120,options)
    for key in [owner,other]:store.vote(key,sid,{p.place.id:2 for p in options})
    store.close_poll(owner,sid)
    for key in [owner,other]:store.confirm(key,sid)
    return store,owner,other,sid


def test_requires_confirmed_booking_and_coordinator_and_optin(booking):
    s,owner,other,sid=booking
    with pytest.raises(SMSError),patch('referee.sms.requests.post') as post:
        notify_booking(s,owner,sid)
        post.assert_not_called()
    with pytest.raises(ValueError):s.confirm_booking(owner,sid,'REF-123',False)
    with pytest.raises(ValueError):s.confirm_booking(other,sid,'REF-123',True)
    s.confirm_booking(owner,sid,'REF-123',True)
    with patch.dict('os.environ',ENV),patch('referee.sms.requests.post') as post:
        assert notify_booking(s,owner,sid)==[]
        post.assert_not_called()


def test_once_per_recipient_and_actual_delivery_status(booking):
    s,owner,other,sid=booking
    s.save_sms_contact(owner,'+12125550101',True)
    s.save_sms_contact(other,'+12125550102',False)
    s.confirm_booking(owner,sid,'REF-123',True)
    response=Mock(status_code=201);response.json.return_value={'sid':'SM'+'b'*32,'status':'queued'}
    with patch.dict('os.environ',ENV),patch('referee.sms.requests.post',return_value=response) as post:
        result=notify_booking(s,owner,sid)
        assert result[0]['status']=='queued'
        assert post.call_args.kwargs['data']['To']=='+12125550101'
        assert 'Party of 2' in post.call_args.kwargs['data']['Body']
        notify_booking(s,owner,sid)
        assert post.call_count==1
    response.json.return_value={'status':'delivered'}
    with patch.dict('os.environ',ENV),patch('referee.sms.requests.get',return_value=response),patch('referee.sms.requests.post') as post:
        assert refresh_statuses(s,owner,sid)[0]['status']=='delivered'
        post.assert_not_called()


def test_timeout_is_not_automatically_retried(booking):
    s,owner,other,sid=booking
    s.save_sms_contact(owner,'+12125550101',True);s.confirm_booking(owner,sid,'REF',True)
    with patch.dict('os.environ',ENV),patch('referee.sms.requests.post',side_effect=requests.Timeout) as post:
        assert notify_booking(s,owner,sid)[0]['status']=='unknown'
        notify_booking(s,owner,sid)
        assert post.call_count==1


def test_contact_validation_optout_and_no_phone_in_profiles(booking):
    s,owner,other,sid=booking
    with pytest.raises(ValueError):s.save_sms_contact(owner,'555-1234',True)
    s.save_sms_contact(owner,'+12125550101',True)
    assert '+12125550101' not in str([p.model_dump() for p in s.profiles(owner)])
    s.save_sms_contact(owner,'',False)
    assert not s.sms_contact(owner)['opt_in']
    s.confirm_booking(owner,sid,'REF',True)
    with patch.dict('os.environ',ENV),patch('referee.sms.requests.post') as post:
        notify_booking(s,owner,sid);post.assert_not_called()


def test_disabled_by_default(booking):
    s,owner,other,sid=booking
    s.confirm_booking(owner,sid,'REF',True)
    with patch.dict('os.environ',{'SMS_ENABLED':'false'}),patch('referee.sms.requests.post') as post:
        with pytest.raises(SMSError,match='disabled'):notify_booking(s,owner,sid)
        post.assert_not_called()


def test_sms_controls_render_and_repeated_button_press_is_safe(booking):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    s,owner,other,sid=booking
    s.save_sms_contact(owner,'+12125550101',True)
    s.confirm_booking(owner,sid,'REF-123',True)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=30)
    app.session_state['member_key']=owner;app.session_state['page']='The vote'
    response=Mock(status_code=201);response.json.return_value={'sid':'SM'+'c'*32,'status':'queued'}
    with patch('referee.ui.store',return_value=s),patch.dict('os.environ',ENV),patch('referee.sms.requests.post',return_value=response) as post:
        app.run()
        assert not app.exception and not app.error
        for _ in range(2):
            next(b for b in app.button if b.label=='Send booking text to opted-in members').click().run()
            assert not app.exception and not app.error
        assert post.call_count==1
