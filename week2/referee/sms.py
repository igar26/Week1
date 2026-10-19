"""Explicit booking notification action. No background sends or automatic retries."""
import os
import re
from datetime import datetime
import requests
from .geography import session_moment


class SMSError(RuntimeError):pass


def settings():
    if os.getenv('SMS_ENABLED','false').lower()!='true':raise SMSError('SMS is disabled. Configure Twilio and set SMS_ENABLED=true in week2/.env to enable real sends.')
    sid=os.getenv('TWILIO_ACCOUNT_SID','');token=os.getenv('TWILIO_AUTH_TOKEN','');sender=os.getenv('TWILIO_FROM_NUMBER','')
    if not re.fullmatch(r'AC[0-9a-fA-F]{32}',sid) or not token or not re.fullmatch(r'\+[1-9]\d{7,14}',sender):
        raise SMSError('Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and your approved TWILIO_FROM_NUMBER in week2/.env.')
    return sid,token,sender


def message_body(session):
    place=next(p['place'] for p in session['options'] if p['place']['id']==session['winner'])
    moment=session_moment(session)
    return (f"After Hours: Your group is booked at {place['name']} on {moment.strftime('%b %d, %Y at %I:%M %p %Z')}. "
            f"Party of {len(session['people'])}. The group confirmed and the organizer approved the booking. "
            "Reply STOP to unsubscribe.")


def notify_booking(store,key,session_id):
    store.owner(key);session=store.get_session(key,session_id)
    if session['status']!='finalized' or not session['booked_at'] or not session['coordinator_approved_at']:
        raise SMSError('The group must finalize the plan and the organizer must confirm and approve the booking first.')
    place=next(p['place'] for p in session['options'] if p['place']['id']==session['winner'])
    if place['synthetic'] or store.group(key)['demo']:raise SMSError('Real SMS is disabled for demo venues and groups.')
    account,token,sender=settings()
    body=message_body(session)
    for person in store.sms_recipients(key,session_id):
        phone=store.claim_sms(key,session_id,person['member_id'])
        if not phone:continue
        status,sid,error='unknown','',''
        try:
            response=requests.post(f'https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json',
                auth=(account,token),data={'To':phone,'From':sender,'Body':body},timeout=20)
            if 400<=response.status_code<500:
                status,error='rejected','Twilio rejected this request. Check the sender, recipient consent, account access and registration in the Twilio console.'
            else:
                response.raise_for_status();payload=response.json()
                if not re.fullmatch(r'SM[0-9a-fA-F]{32}',payload.get('sid','')):raise ValueError
                sid=payload['sid'];status=payload.get('status','queued')
                if status not in {'accepted','scheduled','queued','sending','sent','delivered','undelivered','failed','canceled'}:status='unknown'
        except (requests.RequestException,ValueError):
            error='Delivery outcome is uncertain. Check Twilio before any manual resend; the app will not automatically retry.'
        store.finish_sms(key,session_id,person['member_id'],status,sid,error)
    return store.sms_statuses(key,session_id)


def refresh_statuses(store,key,session_id):
    store.owner(key);rows=store.sms_statuses(key,session_id)
    account,token,_=settings()
    for row in rows:
        if not re.fullmatch(r'SM[0-9a-fA-F]{32}',row['sid']):continue
        try:
            response=requests.get(f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages/{row['sid']}.json",auth=(account,token),timeout=20)
            response.raise_for_status();payload=response.json();status=payload.get('status')
            if status in {'accepted','scheduled','queued','sending','sent','delivered','undelivered','failed','canceled'}:
                store.finish_sms(key,session_id,row['member_id'],status,row['sid'],'Provider reports delivery failure.' if status in {'failed','undelivered'} else '')
        except (requests.RequestException,ValueError):raise SMSError('Could not refresh delivery status. Existing messages have not been resent.') from None
    return store.sms_statuses(key,session_id)
