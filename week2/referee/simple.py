"""Simple group plans: ZIP area, choices, personal RSVP and explicit text sharing."""
import json
import os
import re
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urlsplit
import streamlit as st
from .models import INTERESTS


def budget_limit(plan, rows):
    """Use the lowest definite attendee limit, capped by the proposed event budget.

    Older responses inherit the event budget until the member saves a personal one.
    Tentative members do not become confirmed attendees implicitly.
    """
    return min([plan['budget']]+[r['response'].get('budget',plan['budget']) for r in rows
                if r['response'] and r['response']['attendance']=='Can join'])


class SimplePlans:
    def __init__(self, store):
        self.store=store

    def plan(self,key):
        member=self.store.member(key)
        with self.store.db() as c:
            row=c.execute('SELECT details FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone()
        return json.loads(row[0]) if row else None

    def save_plan(self,key,details):
        member=self.store.owner(key)
        if not re.fullmatch(r'\d{5}',details.get('zip','')) or details['zip']=='00000':raise ValueError('Enter a five-digit US ZIP code.')
        date.fromisoformat(details['date']);time.fromisoformat(details['time'])
        if details['duration'] not in {60,90,120,180} or not 15<=details['budget']<=1000 or not set(details['interests'])<=set(INTERESTS):raise ValueError('Check the duration and preferences. The activity budget must be between $15 and $1,000 per person.')
        choices=list(dict.fromkeys(x.strip() for x in details.get('choices',[]) if x.strip()))
        if not 2<=len(choices)<=8 or any(len(x)>100 for x in choices):raise ValueError('Add 2–8 choices, each up to 100 characters.')
        details={k:details[k] for k in ('zip','date','time','duration','budget','interests')}
        details.update(choices=choices,final_choice='')
        with self.store.db() as c:
            if c.execute('SELECT 1 FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone():raise ValueError('This group already has an outing. Create a new group for another outing.')
            c.execute('INSERT INTO simple_plans VALUES(?,?)',(member['group_id'],json.dumps(details)))

    def respond(self,key,attendance,choices,interests,wishes="",analysis_consent=False,budget=None):
        member=self.store.member(key);plan=self.plan(key)
        if not plan:raise ValueError('This group has no outing yet.')
        if plan['final_choice']:raise ValueError('The coordinator has finalized the choice.')
        if attendance not in {'Can join','Maybe','Cannot join'} or not set(choices)<=set(plan['choices']) or not set(interests)<=set(INTERESTS):raise ValueError('Choose one of the displayed responses.')
        if attendance=='Can join' and not choices:raise ValueError('Select at least one outing tile before saving “Can join”.')
        if not isinstance(wishes,str) or len(wishes)>800 or not isinstance(analysis_consent,bool):raise ValueError('Keep wishes under 800 characters and choose an analysis preference.')
        budget=plan['budget'] if budget is None else budget
        if type(budget) not in (int,float) or not 15<=budget<=1000:raise ValueError('Enter a personal budget between $15 and $1,000.')
        response={'budget':budget,'wishes':wishes.strip(),'analysis_consent':analysis_consent,'attendance':attendance,'choices':choices if attendance!='Cannot join' else [],'interests':interests}
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=json.loads(c.execute('SELECT details FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone()[0])
            if current['final_choice']:raise ValueError('The coordinator has finalized the choice.')
            c.execute('INSERT OR REPLACE INTO simple_responses VALUES(?,?)',(member['id'],json.dumps(response)))

    def set_analysis_consent(self,key,allowed):
        member=self.store.member(key)
        if type(allowed) is not bool:raise ValueError('Choose whether to allow group analysis.')
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT response FROM simple_responses WHERE member_id=?',(member['id'],)).fetchone()
            if not row:raise ValueError('Save your outing response first.')
            response=json.loads(row[0]);response['analysis_consent']=allowed
            c.execute('UPDATE simple_responses SET response=? WHERE member_id=?',(json.dumps(response),member['id']))

    def responses(self,key):
        group=self.store.group(key)
        with self.store.db() as c:
            rows=c.execute("SELECT m.id,m.name,r.response FROM members m LEFT JOIN simple_responses r ON r.member_id=m.id WHERE m.group_id=? AND m.left_at='' ORDER BY m.rowid",(group['id'],)).fetchall()
        return [dict(id=r['id'],name=r['name'],response=json.loads(r['response']) if r['response'] else None) for r in rows]

    def finalize(self,key,choice):
        member=self.store.owner(key)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            plan=json.loads(c.execute('SELECT details FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone()[0])
            if plan['final_choice']:raise ValueError('This choice is already final.')
            if choice not in plan['choices']:raise ValueError('Choose a listed option.')
            rows=c.execute("SELECT r.response FROM members m LEFT JOIN simple_responses r ON r.member_id=m.id WHERE m.group_id=? AND m.left_at=''",(member['group_id'],)).fetchall()
            if any(not r[0] for r in rows):raise ValueError('Wait for everyone to respond before finalizing.')
            answers=[json.loads(r[0]) for r in rows]
            attending=[r for r in answers if r['attendance']=='Can join']
            if not attending or any(choice not in r['choices'] for r in attending):raise ValueError('Choose an option accepted by everyone who can join, or ask them to update their choices.')
            plan['final_choice']=choice
            c.execute('UPDATE simple_plans SET details=? WHERE group_id=?',(json.dumps(plan),member['group_id']))


def invitation_url(code,base=None):
    base=(base if base is not None else os.getenv('PUBLIC_APP_URL','http://127.0.0.1:8502')).rstrip('/')
    p=urlsplit(base)
    if p.scheme not in {'https','http'} or not p.hostname or p.username or p.password or p.query or p.fragment:raise ValueError('The host must configure a valid app URL without credentials or query parameters.')
    if p.scheme!='https' and p.hostname not in {'localhost','127.0.0.1','::1'}:raise ValueError('Shared app links require HTTPS.')
    return base+'/?'+urlencode({'invite':code})


def text_invitation(phone,group,link):
    phone=re.sub(r'[\s()-]','',phone)
    if not re.fullmatch(r'\+[1-9]\d{7,14}',phone):raise ValueError('Enter a mobile number with country code, for example +12125550123.')
    return 'sms:'+phone+'?'+urlencode({'body':f'Join our After Hours group: {group}. Pick what you like and tell us if you can join: {link}'})


def consume_invitation():
    code=st.query_params.get('invite')
    if code:
        if re.fullmatch(r'[A-Za-z0-9_-]{16}',code):
            st.session_state.pending_invite=code
            st.session_state.page='Your group'
        del st.query_params['invite']


@st.cache_data(ttl=900,max_entries=100)
def nearby_places(zipcode,category='All categories'):
    from .nearby import find_places,PLACE_CATEGORIES
    if category not in PLACE_CATEGORIES:raise ValueError('Choose a displayed place category.')
    categories=PLACE_CATEGORIES[category]
    result=find_places(zipcode.strip(),**({'categories':categories} if categories else {}))
    return {**result,'provider':'Geoapify','category':category}


def toggle_nearby_place(zipcode,place,widget_key):
    basket=st.session_state.get('nearby_basket',{'zip':zipcode,'places':{}})
    if basket['zip']!=zipcode:basket={'zip':zipcode,'places':{}}
    if st.session_state[widget_key]:basket['places'][place['id']]=place
    else:basket['places'].pop(place['id'],None)
    st.session_state.nearby_basket=basket


def clear_nearby_choices(zipcode):
    st.session_state.nearby_basket={'zip':zipcode,'places':{}}
    for key in list(st.session_state):
        if key.startswith('nearby_pick_'+zipcode+'_'):st.session_state[key]=False


def nearby_picker(zipcode):
    from .providers import ProviderError,safe_url
    from .nearby import PLACE_CATEGORIES
    import time as clock
    basket=st.session_state.get('nearby_basket')
    if not basket or basket['zip']!=zipcode:
        st.session_state.nearby_basket={'zip':zipcode,'places':{}}
    category=st.selectbox('What nearby places would you like to see?',list(PLACE_CATEGORIES),key='nearby_category')
    if st.button('Find nearby places',icon=':material/explore:'):
        if not re.fullmatch(r'\d{5}',zipcode):
            st.warning('Enter a five-digit US ZIP code before searching.')
        elif clock.monotonic()-st.session_state.get('nearby_last_request',-100)<3:
            st.info('Please wait 3 seconds between searches.')
        else:
            st.session_state.nearby_last_request=clock.monotonic()
            try:
                with st.spinner('Looking for '+category.lower()+' near your ZIP…'):
                    result=nearby_places(zipcode,category)
                    st.session_state.nearby_result={**result,'category':category}
                    st.session_state.nearby_provider='geoapify-v2'
            except (ValueError,ProviderError) as exc:
                st.session_state.pop('nearby_result',None)
                st.warning(str(exc))
                st.caption('Your selected choices are kept. You can also add your own places below.')
    if st.session_state.get('nearby_provider')!='geoapify-v2':st.session_state.pop('nearby_result',None)
    result=st.session_state.get('nearby_result')
    if result and result['zip']==zipcode and result.get('category')==category:
        st.caption(result['area']+' · '+category+' · within 10 straight-line miles of the ZIP center · Powered by [Geoapify](https://www.geoapify.com/) · [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)')
        if not result['places']:st.info('No places were returned for this category. Try another category or add a place below.')
        columns=st.columns(3)
        for i,row in enumerate(result['places']):
            place=row['place']
            with columns[i%3].container(border=True):
                st.text(place['name'])
                st.caption(place['category']+' · '+str(row['miles'])+' miles')
                st.text(place.get('address') or 'Street address not listed')
                st.caption('Reported hours: '+(place.get('hours') or 'Not listed'))
                if safe_url(place.get('source_url')):st.link_button('View place details',place['source_url'])
                widget_key='nearby_pick_'+zipcode+'_'+place['id']
                st.checkbox('Add to outing choices',value=place['id'] in st.session_state.nearby_basket['places'],key=widget_key,
                            on_change=toggle_nearby_place,args=(zipcode,place,widget_key))
        st.caption('Check hours, prices and suitability with the venue. No synthetic places are substituted.')
    elif result and result['zip']==zipcode:
        st.caption('Click Find nearby places to load the selected category. Your earlier selections are kept.')
    selected=list(st.session_state.nearby_basket['places'].values())
    if selected:
        st.text('Selected places: '+', '.join(place['name'] for place in selected))
        st.caption(f'{len(selected)} selected across categories · Choose 2–8 places or combine with your own choices below.')
        st.button('Clear selected places',on_click=clear_nearby_choices,args=(zipcode,))
    return list(dict.fromkeys(place['name'][:100] for place in selected))


def response_tiles(plan,rows,group_id,member_id,saved,editable,demo=False):
    st.subheader('Outing choices')
    picks=[]
    tiles=st.columns(3)
    for index,choice in enumerate(plan['choices']):
        with tiles[index%3].container(border=True):
            st.text(choice)
            if editable:
                if st.checkbox('I would enjoy: '+choice,value=choice in saved,key=f'rsvp_{group_id}_{member_id}_{index}'):
                    picks.append(choice)
            elif choice in saved:st.caption('Your saved choice')
            count=sum(bool(r['response'] and r['response']['attendance']=='Can join' and choice in r['response']['choices']) for r in rows)
            st.caption(f'{count} interested and able to join')
            if demo:st.caption('Fictional activity idea; no real venue or address.')
            else:st.link_button('Find on map','https://www.google.com/maps/search/?'+urlencode({'api':1,'query':choice+' near '+plan['zip']}))
    return picks


def group_page(store_factory,advanced_page):
    store=store_factory();plans=SimplePlans(store)
    key=st.session_state.get('member_key')
    if key and st.session_state.get('pending_invite'):
        st.info('You already have a group open. Open the new invitation in a different browser profile to keep access to both groups. Signed-in event creators can reopen their saved meetups through their account. Guest access still depends on the existing browser session.')
        if st.button('Back to my current group'):
            st.session_state.pop('pending_invite',None);st.rerun()
        return
    if key and not plans.plan(key):
        advanced_page();return
    st.title('Your people. Your plan.')
    if not key:
        invite=st.session_state.get('pending_invite','')
        if invite:
            st.info('You’re invited! Enter your name, then choose what sounds fun.')
        from .accounts import creator_access,Accounts,identity
        creator=creator_access(store) if not invite else None
        if not invite and creator:
            zipcode=st.text_input('Meetup ZIP code',max_chars=5,placeholder='75201',key='simple_zip')
            st.caption('Start with activity ideas and preferences. After everyone responds, find common ground and search for a venue below the group’s choices.')
            with st.form('simple_create'):
                st.subheader('Start a group outing')
                group=st.text_input('Group name',max_chars=80)
                name=st.text_input('Your name',max_chars=60)
                a,b=st.columns(2)
                day=a.date_input('Outing date',value=datetime.now(ZoneInfo('America/Chicago')).date())
                hour=b.time_input('Meetup time (local to the venue)',value=time(18))
                duration=st.selectbox('How long?',[60,90,120,180],format_func=lambda m:f'{m//60} hr {m%60} min')
                budget=st.number_input('Proposed activity budget per person ($)',min_value=15.0,max_value=1000.0,value=30.0,step=5.0,format='%.2f',help='Type your own amount, including cents. The minimum budget is $15 per person.')
                interests=st.multiselect('What sounds fun?',INTERESTS,default=['Food','Outdoors'])
                choices=st.text_area('Places or activities to choose from — one per line',placeholder='Pizza at a nearby restaurant\nPicnic in the park\nCoffee and a walk')
                if st.form_submit_button('Create group',type='primary'):
                    options=list(dict.fromkeys(x.strip() for x in choices.splitlines() if x.strip()))
                    if not 2<=len(options)<=8 or any(len(x)>100 for x in options):raise ValueError('Add 2–8 short outing choices.')
                    if not group.strip() or not name.strip():raise ValueError('Enter your name and a group name.')
                    if not re.fullmatch(r'\d{5}',zipcode) or zipcode=='00000':raise ValueError('Enter a five-digit US ZIP code.')
                    verified_creator=identity()
                    if not verified_creator:raise ValueError('Sign in before creating a meetup.')
                    key,code=store.create_group(group,name)
                    Accounts(store).link(verified_creator,key)
                    plans.save_plan(key,dict(zip=zipcode,date=day.isoformat(),time=hour.strftime('%H:%M'),duration=duration,budget=budget,interests=interests,choices=options))
                    st.session_state.update(member_key=key,invite=code)
                    st.rerun()
        with st.expander('Join with a code' if not invite else 'Join your friends',expanded=bool(invite)):
            with st.form('simple_join'):
                code=st.text_input('Invitation code',value=invite,type='password')
                name=st.text_input('Your name',key='simple_join_name',max_chars=60)
                if st.form_submit_button('Join group',type='primary'):
                    # Name alone never restores another member’s identity.
                    st.session_state.member_key=store.join(code,name)
                    st.session_state.pop('pending_invite',None);st.rerun()
        with st.expander('Existing prototype access'):
            st.caption('Event creators can sign in with Google above to open saved meetups. This recovery form is for guests and older prototype users who already saved an access key. Keep your current browser session open otherwise.')
            with st.form('simple_rejoin'):
                secret=st.text_input('Your private return key',type='password')
                if st.form_submit_button('Return to my group'):
                    store.member(secret.strip());st.session_state.member_key=secret.strip();st.rerun()
        return
    group=store.group(key);member=store.member(key);plan=plans.plan(key)
    if group['demo']:
        st.info('Dallas demo · Fictional outing choices and sample responses. No live search, messages or bookings are made.')
        keys=st.session_state.get('demo_keys',{})
        if keys:
            names={r['id']:r['name'] for r in store.roster(key)}
            keys={pid:value for pid,value in keys.items() if pid in names}
            st.session_state.demo_keys=keys
            selected=st.selectbox('Demo: view as a friend',list(keys),index=list(keys).index(member['id']),format_func=lambda pid:names[pid]+(' · coordinator' if pid==group['owner'] else ''))
            if selected!=member['id']:
                st.session_state.member_key=keys[selected]
                st.rerun()
        st.caption('Try editing a friend’s RSVP, return to the coordinator, find the shared fit, then finalize. Start a fresh demo from Home to reset it.')
    st.subheader(group['name'])
    st.caption(('Coordinator: you' if group['owner']==member['id'] else 'You’re joining as '+member['name'])+' · Your shared meetup')
    st.write(f"ZIP {plan['zip']} · {plan['date']} at {plan['time']} (venue local time) · {plan['duration']} minutes · proposed budget ${plan['budget']}/person")
    st.caption('The ZIP is the shared meetup area. Travel distance, venue hours, dietary needs and reservations still need the coordinator’s check.')
    with st.expander('Share this event',expanded=True):
        code=st.session_state.get('invite')
        if group['owner']==member['id']:
            if not code or st.button('Replace invitation link'):
                code=store.rotate_invitation(key);st.session_state.invite=code
            link=invitation_url(code)
            st.caption('Copy the event link using the copy icon, then share it with your friends. They join with their name and choose what works for them.')
            st.code(link,language=None)
            st.caption('Invitation expires in 7 days. Share only with the friends you want to join.')
            local=urlsplit(link).hostname in {'localhost','127.0.0.1','::1'}
            if group['demo']:st.caption('Text invitations are disabled for fictional demo groups.')
            if local:st.info('Local demo: this link works only on this computer. Phone invitations need a securely hosted app URL; hosting is not enabled in this prototype.')
            with st.form('prepare_invite'):
                phone=st.text_input('Friend’s mobile number (with country code)',placeholder='+12125550123')
                if st.form_submit_button('Prepare text invitation',disabled=local or bool(group['demo'])):
                    draft=text_invitation(phone,group['name'],link)
                    st.link_button('Open your messaging app to send',draft)
                    st.caption('You review and press Send in your messaging app. Nothing has been sent automatically. Carrier charges may apply. Use only for friends expecting your invitation.')
        else:st.caption('Ask your coordinator to send invitations.')
    rows=plans.responses(key);mine=next(r['response'] for r in rows if r['id']==member['id']) or {}
    from .meetup import Meetups
    try:venue_round=Meetups(plans).current(key)
    except ValueError:venue_round=None
    stage='3 / Enjoy the meetup, then share photos in Our adventures' if venue_round and venue_round['status']=='finalized' else ('2 / Choose and agree on a venue below' if plan['final_choice'] else '1 / Everyone saves their availability and choices')
    st.info(stage)
    st.caption(f"Shared spending ceiling: ${budget_limit(plan,rows):g}/person, based on the proposed budget and definite attendees’ saved limits. Older responses use the proposed budget until updated.")
    if not plan['final_choice']:
        with st.form('simple_response_'+group['id']+'_'+member['id']):
            st.subheader('What works for you?')
            attendance=st.radio('Can you join?',['Can join','Maybe','Cannot join'],index=['Can join','Maybe','Cannot join'].index(mine.get('attendance','Maybe')))
            st.caption('Tick one or more outing tiles below, then save your response.')
            picks=response_tiles(plan,rows,group['id'],member['id'],mine.get('choices',[]),editable=True,demo=bool(group['demo']))
            interests=st.multiselect('Your preferences',INTERESTS,default=mine.get('interests',plan['interests']))
            if mine and mine.get('budget',plan['budget'])<15:st.info('Your previously saved budget is below the new $15 minimum. Enter at least $15 and save your response to update it.')
            personal_budget=st.number_input('My activity budget per person ($)',min_value=15.0,max_value=1000.0,value=max(15.0,float(mine.get('budget',plan['budget']))),step=5.0,format='%.2f',help='Click the amount and type your own budget, including cents. The minimum budget is $15 per person.')
            st.caption('Type any amount from $15 to $1,000; you are not restricted to the +/− steps. Include food, activity fees and any other spending you need to allow for. The group uses the lowest confirmed attendee limit; tentative responses remain tentative.')
            wishes=st.text_area('What would make this outing work well for you? (optional)',value=mine.get('wishes',''),max_chars=800,placeholder='Somewhere quiet, a short walk, or a good spot to celebrate.')
            consent=st.checkbox('Let the group assistant analyse my choices and wishes',value=mine.get('analysis_consent',False))
            st.caption('Optional. Consenting responses may be processed by the host’s AI service and shown in the group recommendation. Avoid private contact details in wishes. You can still vote without this.')
            if st.form_submit_button('Save my response',type='primary'):
                try:
                    plans.respond(key,attendance,picks,interests,wishes,consent,budget=personal_budget)
                except ValueError as exc:
                    st.warning(str(exc))
                else:
                    st.session_state.response_saved_for=member['id']
                    st.rerun()
    else:
        st.success('Activity agreed: '+plan['final_choice'])
        st.caption(f"Your saved spending limit: ${mine.get('budget',plan['budget']):g}. Preferences are locked for this outing; ask the coordinator to resolve changed needs before confirming a venue.")
        response_tiles(plan,rows,group['id'],member['id'],mine.get('choices',[]),editable=False,demo=bool(group['demo']))
        if not group['demo']:
            with st.expander('Group assistant privacy'):
                with st.form('post_agreement_consent_'+member['id']):
                    allowed=st.checkbox('Let the group assistant analyse my choices and wishes',value=mine.get('analysis_consent',False))
                    st.caption('You can change this permission after activity agreement. Your saved outing and venue votes stay intact.')
                    if st.form_submit_button('Save analysis preference'):
                        plans.set_analysis_consent(key,allowed);st.rerun()

    if st.session_state.pop('response_saved_for',None)==member['id']:
        st.success('Your response is saved. Selected: '+(', '.join(mine.get('choices',[])) or 'No outing choices')+'.')
    st.subheader('The group so far')
    for row in rows:
        answer=row['response']
        st.text(row['name']+' · '+(answer['attendance']+f" · spending limit ${answer.get('budget',plan['budget']):g}" if answer else 'Waiting for a response'))
    from .common_ground import panel as common_ground_panel
    common_ground_panel(plans,key)
    if group['owner']==member['id'] and not plan['final_choice']:
        with st.form('simple_finalize'):
            selected=st.selectbox('Choose the shared plan',plan['choices'])
            st.caption('Wait for every response. The choice must work for everyone who says they can join. “Maybe” is not a confirmed attendee.')
            if st.form_submit_button('Finalize choice'):plans.finalize(key,selected);st.rerun()
    from .meetup import panel as meetup_panel
    meetup_panel(plans,key)
    if st.button('Refresh responses'):st.rerun()
    from .membership import group_settings
    group_settings(store,key)
