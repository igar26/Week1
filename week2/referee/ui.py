"""Streamlit screens. API/model calls occur only on explicit button presses."""
import base64
import json
import os
import uuid
import time as clocktime
from datetime import datetime, date, time, timedelta
from pathlib import Path
import streamlit as st
from .catalog import demo_places
from .models import Profile, Place, Proposal, INTERESTS, DIETS
from .store import Store
from .decision import rank_options, DALLAS_TZ, miles
from .geography import starters,search_us,US_ZONES,local_start,session_moment
from zoneinfo import ZoneInfo
from .workflow import process_profiles, coordinate
from .providers import discover, weather, safe_url
from .graph import Graph
from .sms import message_body, notify_booking, refresh_statuses
from .itinerary import meeting_details, maps_links
from .security import inline_photo

ROOT=Path(__file__).resolve().parents[1]


def go(page):st.session_state.page=page


@st.cache_resource
def store():
    """Private group storage, including active membership and departure records."""
    return Store()


@st.cache_data(max_entries=1)
def hero_image():return base64.b64encode((ROOT/'assets/dallas-after-hours.png').read_bytes()).decode()


def styles():
    st.html('''<style>
    [data-testid="stAppViewContainer"] {background:radial-gradient(ellipse at 95% 0%,#273e46 0%,transparent 48%),radial-gradient(ellipse at 0% 90%,#412b2a 0%,transparent 45%),#101b24;}
    .block-container {max-width:1320px;padding-top:2rem;}
    .brand {font-size:1.15rem;font-weight:750;letter-spacing:.13em; color:#f7eee1; margin:0;}
    .eyebrow {font-size:.72rem;letter-spacing:.22em;color:#ffbd91;font-weight:700; text-transform:uppercase;}
    .hero {position:relative;overflow:hidden;border-radius:26px;min-height:490px;padding:55px 44px;isolation:isolate;border:1px solid #6a615c;}
    .hero img {position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:-2;}
    .hero::after {content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(90deg,rgba(13,27,34,.98) 0%,rgba(13,27,34,.82) 37%,rgba(13,27,34,.07) 78%);}
    .hero h1 {font-family:Georgia,serif;font-size:clamp(2.5rem,5vw,4.6rem);font-weight:500;line-height:1.04;max-width:640px;margin:23px 0;color:#fff3e0;}
    .hero em {color:#ffad85;font-style:italic;}
    .hero p {font-size:1.08rem;line-height:1.7;max-width:410px;color:#d8e0df;}
    .stamp {display:inline-block;border:1px solid #9c806d;padding:7px 13px;border-radius:30px;color:#f4d9c4;font-size:.75rem;letter-spacing:.08em;}
    .mini-card {padding:22px;border:1px solid #55616a;border-radius:18px;min-height:150px;background:linear-gradient(140deg,#263d45,#242a35);}
    .mini-card h3 {font-family:Georgia,serif;font-weight:500;margin:8px 0;color:#fff2dd;font-size:1.45rem;}
    .mini-card p {color:#c2cdce;font-size:.9rem;margin:0;}
    @media(max-width:700px){.hero{padding:30px 22px;min-height:440px}.hero::after{background:rgba(13,27,34,.75)}}
    </style>''')


def header():
    from .accounts import sign_out_control
    sign_out_control()
    left,right=st.columns([6,1],vertical_alignment='center')
    with left:
        st.html('<p class="brand">◒ &nbsp; AFTER HOURS</p>')
        st.caption('Less group chat. More good company.')
    with right:st.button('Help',icon=':material/help_outline:',on_click=go,args=('Help',),width='stretch',key='help')
    with st.container(horizontal=True):
        for page,icon in [('Home','home'),('Your group','group'),('Our adventures','photo_library')]:
            st.button(page,icon=f':material/{icon}:',on_click=go,args=(page,),type='primary' if st.session_state.page==page else 'tertiary',key='nav_'+page)
    if st.session_state.get('member_key'):
        s=store()
        try:
            m=s.member(st.session_state.member_key);g=s.group(st.session_state.member_key)
        except ValueError:
            for name in list(st.session_state):del st.session_state[name]
            st.session_state.update(page='Home',notice='Your group access has ended.')
            st.rerun()
        st.caption(f"{g['name']}  /  Viewing as {m['name']}"+('  /  Synthetic demo group' if g['demo'] else ''))


def require_group():
    key=st.session_state.get('member_key')
    if not key:
        st.info('Create a group or join your friends first. The sample group lets you explore immediately.')
        if st.button('Meet the sample group',type='primary',key='sample_required'):load_demo()
        return None
    return key


def load_demo():
    from .demo import create_outing_demo
    key,invite,keys=create_outing_demo(store())
    for field in ['group_recommendation','pending_invite','response_saved_for']:st.session_state.pop(field,None)
    st.session_state.update(member_key=key,invite=invite,demo_keys=keys,page='Your group')
    st.rerun()


def home():
    if st.session_state.get('notice'):st.success(st.session_state.pop('notice'))
    encoded=hero_image()
    st.html(f'''<section class="hero"><img src="data:image/png;base64,{encoded}" alt="Illustrative image of friends sharing a rooftop dinner with the Dallas skyline at dusk">
    <span class="stamp">ANYWHERE IN THE US &nbsp; / &nbsp; MADE FOR YOUR PEOPLE</span>
    <h1>Different people.<br>One <em>great plan.</em></h1>
    <p>Your foodie friend. Your outdoors friend. Your “anything is fine” friend.<br>Finally, a plan that gets everyone out the door.</p>
    <span class="eyebrow">Less “whatever works.” More “see you there!”</span></section>''')
    with st.container(horizontal=True):
        st.button('Plan something good',type='primary',icon=':material/arrow_forward:',on_click=go,args=('Your group',),key='plan_home')
        if st.button('Try the Dallas demo',icon=':material/play_arrow:',key='try_demo'):load_demo()
    st.caption('Hero image is AI-generated inspiration, not a real venue or a photo of your group.')
    st.subheader('A little less “so… what’s the plan?”')
    for column,(number,title,text) in zip(st.columns(3),[
        ('01 / YOUR PEOPLE','Everyone gets a say','Create a group, share an invite and pick what sounds fun.'),
        ('02 / YOUR CITY','Find your common ground','Choose a ZIP and ideas; each friend adds their preferences and spending limit.'),
        ('03 / YOUR MEMORIES','Make it a good story','Vote together, book with the venue, and keep the photos worth revisiting.')]):
        with column:st.html(f'<article class="mini-card"><span class="eyebrow">{number}</span><h3>{title}</h3><p>{text}</p></article>')
    st.space('small')
    a,b=st.columns([1.1,1])
    with a:
        st.subheader('The group chat deserves a night off.')
        st.write('Choose an activity, agree on a venue that fits your spending limits, then keep the photos together. The assistant suggests; your group decides.')
    with b:
        with st.container(border=True):
            st.markdown('**Food & patios** · **Art & culture** · **Outdoors & slow afternoons**')
            st.caption('Choose a ZIP code · Invite your people · Pick what works for everyone')
            st.markdown('**Start small. Make a memory. Do it again.**')


@st.cache_data(ttl=86400,max_entries=100)
def city_search(query):
    return search_us(query)


def starting_area(member_id,existing):
    st.markdown('**Your starting area — anywhere in the United States**')
    with st.form('find_city_'+member_id):
        query=st.text_input('Search a US city or ZIP code',placeholder='Portland, OR · Brooklyn, NY · 96813')
        if st.form_submit_button('Find US locations'):
            result=city_search(query)
            st.session_state['geo_results_'+member_id]=result
            if result:st.session_state['location_'+member_id]=result[0]['label']
            else:st.warning('No US locations matched. Try a city name followed by its state.')
    choices={r['label']:r for r in starters()}
    if existing:
        row={'label':existing.city,'city':existing.city,'state':'','lat':existing.lat,'lon':existing.lon,'timezone':existing.timezone}
        choices[row['label']]=row
    for row in st.session_state.get('geo_results_'+member_id,[]):choices[row['label']]=row
    labels=[None]+list(choices)
    selected=st.selectbox('Starting city / area',labels,index=labels.index(existing.city) if existing else 0,
        format_func=lambda value:value or 'Choose a US location',key='location_'+member_id)
    if selected:
        row=choices[selected]
        st.caption(f"Timezone: {row['timezone']} · Approximate city-center coordinates · Open-Meteo / GeoNames search, with offline starter cities")
        return row
    return None


def usage_guide():
    st.markdown("""**Start the meetup**
Sign in with Google to create your app account before starting a real event. The Dallas demo needs no account.

1. Choose **Plan something good**, enter the meetup ZIP code and activity ideas, then create the group with a date, time and proposed budget. The creator is coordinator.
2. In **Share this event**, copy the invitation for friends. Text preparation opens your messaging app for review; it does not send automatically. Remote phones need a securely hosted version, which is not available yet.
3. Everyone saves **Can join**, **Maybe** or **Cannot join**, multiple activity choices, their own spending limit ($15 minimum), preferences and any important needs.
4. After every response is saved, the coordinator can ask **Find our common ground** for an explanation, then agree on an activity accepted by every definite attendee. AI is optional and needs participants’ permission; voting works without it.
5. Stay on **Your group**: find venue tiles, check missing details and open venue voting. Everyone who can or might join votes on each venue. The assistant can suggest a fit; only the coordinator confirms it, after every definite attendee chooses **Works for me**. Known cost must fit the lowest definite attendee budget and the event budget.
6. Check opening hours, the full cost and personal requirements before arranging the meetup. Unknown details are displayed as unknown. Confirming the venue in the app does not book a table or send booking texts.
7. Once the outing has happened, the coordinator marks it completed in **Our adventures**. Any member can upload photos and captions; they become visible to the whole group. The open gallery refreshes about every five seconds.

**Your group, your choices**
Responses stay editable until activity agreement. “Maybe” is tentative. If no activity works for everyone attending, update the choices together. Before venue confirmation, the coordinator can replace the venue round and collect new votes. A confirmed venue remains part of the group’s history.

**Coming back and leaving**
Groups, responses, venue votes and memories are saved on this app server. Keep your current browser session open: event creators can return through their Google account once the host configures sign-in. Guest members still need their existing browser session or a saved prototype access key. An existing access-key recovery form supports older prototype users. Invitation links invite a new member; they do not recover someone’s identity.

Use **Group settings → Leave this group** to leave. A coordinator must hand over to another member when others remain. You may delete your own shared memories during departure; otherwise they remain with the group. Access is revoked when you leave.

**Try it first**
The Dallas demo uses fictional friends, venue details and offline sample recommendations. It makes no real searches, messages or reservations. No member needs an API key. Nearby search and real AI need the host’s connections.
""")

def meeting_card(session):
    with st.container(border=True):
        st.subheader('Our next adventure ✨')
        if not session:
            st.caption('Discover → Vote → Everyone confirms → Meet up → Make memories')
            st.info('Your coordinator will propose a date, duration and venue after reviewing everyone’s preferences.')
            return
        details=meeting_details(session)
        st.badge(details['status'],color='green' if session['status'] in {'finalized','completed'} else 'orange')
        st.text(session['title'])
        start,end=details['start'],details['end']
        date_col,time_col,length_col=st.columns(3)
        date_col.metric('The big day',start.strftime('%b %d, %Y'))
        time_col.metric('Meet → happy goodbyes',start.strftime('%I:%M %p')+' → '+end.strftime('%I:%M %p'))
        length_col.metric('Time for good company',details['duration'])
        st.caption(start.strftime('%A · %Z')+' · '+str(start.tzinfo)+' · '+str(len(session['people']))+' adventurers')
        if start.date()!=end.date():st.caption('Finishes '+end.strftime('%A, %b %d, %Y · %Z'))
        elif start.tzname()!=end.tzname():st.caption('Ends in '+end.strftime('%Z')+' after the daylight-saving clock change.')
        place=details['place']
        if not place:
            st.write('📍 Destination: still auditioning. Head to The vote to help choose it.')
        else:
            st.text('📍 '+place.name)
            st.text(place.address or ('Fictional demo venue — no real street address.' if place.synthetic else 'Street address not recorded. Ask the coordinator to verify it; the map uses venue coordinates.'))
            st.caption('Gather → '+place.name+' → '+details['duration']+' of good company → New memories')
            for label,url in maps_links(place).items():st.link_button(label,url)
            if not place.synthetic:st.caption('Maps opens only on click. Only the venue destination is included; choose your own starting point in Google Maps. Confirm the pin before travelling.')
        st.caption('Mission: arrive hungry for fun. Departure time is a plan, not a pumpkin spell.')


def group_page():
    from .simple import group_page as simple_group_page
    simple_group_page(store, advanced_group_page)


def advanced_group_page():
    st.title('Good plans start with your people.')
    st.caption('Older detailed group: this saved group uses the original profile workflow. Create a new group from a separate browser profile to try the current ZIP, choices and venue-voting flow.')
    with st.expander('How to create, share, and return to a group'):
        usage_guide()
    st.caption('Groups save automatically on this app server. Returning members use their private rejoin key; no need to create the group again.')
    s=store()
    if not st.session_state.get('member_key'):
        a,b=st.columns(2)
        with a:
            with st.container(border=True):
                st.subheader('Start a meetup')
                st.caption('New events use the current group flow and require creator sign-in.')
                st.button('Start with your account',on_click=go,args=('Your group',),key='legacy_start_account')
        with b:
            with st.container(border=True):
                st.subheader('Your people are already here?')
                with st.form('join_group'):
                    invite=st.text_input('Group invitation code',type='password')
                    name=st.text_input('Your name',key='join_name',max_chars=60)
                    if st.form_submit_button('Join group'):
                        st.session_state.member_key=s.join(invite,name);st.rerun()
                with st.form('rejoin'):
                    secret=st.text_input('Your private rejoin key',type='password')
                    if st.form_submit_button('Rejoin my group'):
                        s.member(secret.strip());st.session_state.member_key=secret.strip();st.rerun()
        if st.button('Explore with four fictional Dallas friends',key='group_demo'):load_demo()
        return
    key=st.session_state.member_key;m=s.member(key);g=s.group(key)
    with st.expander('Your invitation and private rejoin key'):
        if st.session_state.get('invite'):
            st.caption('Share the group invitation with friends. Keep your personal rejoin key to yourself.')
            st.code(st.session_state.invite,language=None)
        st.caption('Save this private key to rejoin as yourself. Do not put it in Git or public screenshots.')
        st.code(key,language=None)
        st.caption('Use the copy button on the private key above and save it in your password manager. Private keys are not offered through shared download URLs.')
        if st.button('Replace my private rejoin key',key='rotate_member_key'):
            replacement=s.rotate_member_key(key)
            st.session_state.member_key=replacement
            if st.session_state.get('demo_keys'):
                st.session_state.demo_keys[m['id']]=replacement
            st.rerun()
        if m['id']==g['owner']:
            st.caption('Lost the invitation code? Generate a replacement below. This invalidates the old invitation, not existing members’ private keys.')
            if st.button('Generate a new invitation code',key='rotate_invite'):
                st.session_state.invite=s.rotate_invitation(key);st.rerun()
        st.caption('Invitations expire after 7 days. Generate a fresh code if needed; replacing your personal key immediately revokes the old key.')

    with st.expander('Booking text preferences'):
        contact=s.sms_contact(key)
        st.caption('Optional: your number stays outside AI profiles and Neo4j. You can update it or opt out even while a plan is frozen.')
        with st.form('sms_contact_'+m['id']):
            phone=st.text_input('Your mobile number, including country code',value=contact['phone'],placeholder='+12125550123')
            opt_in=st.checkbox('I own this number and agree to receive one booking text per finalized outing from After Hours. Message and data rates may apply. Reply STOP to unsubscribe, or turn this off here.',value=bool(contact['opt_in']))
            if st.form_submit_button('Save my text preferences'):
                s.save_sms_contact(key,phone,opt_in);st.success('Text preferences saved.');st.rerun()
    if g['demo'] and st.session_state.get('demo_keys'):
        keys=st.session_state.demo_keys
        names={r['id']:r['name'] for r in s.roster(key)}
        choice=st.selectbox('Demo only: act as a sample participant',list(keys),format_func=lambda pid:names[pid],index=list(keys).index(m['id']))
        if choice!=m['id']:
            st.session_state.member_key=keys[choice];st.rerun()
        st.caption('Role switching is only available for this synthetic demo. Real members use their own private rejoin keys.')
    active=s.session(key)
    meeting_card(active)
    frozen=bool(active and active['status'] in {'voting','confirming','finalized'})
    existing=Profile.model_validate_json(m['profile']) if m['profile']!='{}' else None
    st.subheader(f"A little about {m['name']}")
    if frozen:st.info('This planning round is frozen so votes keep their meaning. The organizer can start a new round below.')
    area=starting_area(m['id'],existing)
    with st.form('profile_'+m['id']):
        a,b=st.columns(2)
        with a:
            budget=st.number_input('Maximum total spend per person (USD)',min_value=0,max_value=1000,value=int(existing.budget) if existing else 40)
            interests=st.multiselect('Your kind of good time',INTERESTS,default=existing.interests if existing else ['Food','Outdoors'])
        with b:
            diets=st.multiselect('Required dietary options (restaurants)',DIETS,default=existing.diets if existing else [])
            accessible=st.checkbox('Step-free / wheelchair access required',value=existing.accessible if existing else False)
            af=st.time_input('Available from (your starting-area local time)',time.fromisoformat(existing.available_from) if existing else time(9))
            au=st.time_input('Available until (your starting-area local time)',time.fromisoformat(existing.available_until) if existing else time(23))
        notes=st.text_area('Anything else we should know?',value=existing.notes if existing else '',max_chars=1500,placeholder='Quiet corners, great coffee, and please no competitive karaoke.')
        if st.form_submit_button('Save my profile',type='primary',disabled=frozen):
            if not area:raise ValueError('Select your starting US city before saving the profile.')
            lat,lon=area['lat'],area['lon']
            city=area['label']
            p=Profile(id=m['id'],name=m['name'],city=city,timezone=area['timezone'],lat=lat,lon=lon,budget=budget,interests=interests,diets=diets,accessible=accessible,notes=notes,reviewed=True,ai_consent=existing.ai_consent if existing else False,graph_consent=existing.graph_consent if existing else False,available_from=af.strftime('%H:%M'),available_until=au.strftime('%H:%M'))
            s.save_profile(key,p);st.success('Your profile is saved.');st.rerun()
    st.caption('Locations use city centers, not home addresses. Availability applies to the proposed outing day; the group confirms the date together.')
    st.subheader('The circle')
    for r in s.roster(key):
        p=json.loads(r['profile'])
        with st.container(border=True):
            st.markdown(f"**{r['name']}** · "+(f"{p['city']} · up to ${p['budget']:g}" if p else 'Profile not saved yet'))
            st.caption(' · '.join(p.get('interests',[])) or 'Waiting for their preferences')
    a,b,c=st.columns(3)
    with a:st.button('Discover our options',on_click=go,args=('Discover',),type='primary')
    with b:
        if g['owner']==m['id'] and frozen and st.button('Start a new planning round'):
            s.reset_round(key)
            for k in ['shortlist','rejected','advocates','coordinator','catalog']:st.session_state.pop(k,None)
            st.rerun()
    with c:
        if st.button('Leave this browser session'):
            for k in list(st.session_state):del st.session_state[k]
            st.rerun()
    from .membership import group_settings
    group_settings(s,key)


def discover_page():
    st.title('Find your common ground.')
    st.caption('Older detailed planning screen. Current simple groups choose venues directly on Your group.')
    key=require_group()
    if not key:return
    s=store();profiles=s.profiles(key);group=s.group(key);member=s.member(key)
    if len(profiles)!=len(s.roster(key)) or not profiles or not all(p.reviewed for p in profiles):
        st.info('Everyone needs a saved, reviewed profile before the referee can build a fair shortlist.');return
    if s.session(key) and s.session(key)['status'] in {'voting','confirming','finalized'}:
        st.info('Your current shortlist is frozen. Head to The vote, or ask the organizer to start a new planning round.');return
    planning_zone=st.selectbox('Outing / venue timezone',list(dict.fromkeys([profiles[0].timezone]+US_ZONES)),index=0)
    st.caption('Everyone’s availability is checked in their own local timezone. Confirm the venue timezone, especially near a timezone boundary.')
    if any(miles(a.lat,a.lon,b.lat,b.lon)>100 for a in profiles for b in profiles):
        st.info('At least two members are more than 100 miles apart. A place cannot be within 50 miles of both. Use a new planning round to choose starting areas near a shared trip destination.')
    with st.container(border=True):
        a,b,c=st.columns(3)
        with a:
            outing_date=st.date_input('Outing date',datetime.now(ZoneInfo(planning_zone)).date()+timedelta(days=1))
            outing_time=st.time_input('Start time (venue local time)',time(17))
        with b:
            duration=st.selectbox('Time together (minutes)',[60,90,120,180],index=2)
            source=st.selectbox('Places to explore',['Synthetic Dallas demo','OpenStreetMap','Google Places','Foursquare'])
        with c:
            mode=st.selectbox('Personal advocates',['Demo rules','Codex CLI'])
            use_graph=st.checkbox('Use Neo4j for graph matching',value=False)
        title=st.text_input('Give this adventure a name',value='A little less group chat',max_chars=100)
    st.caption('50 miles maximum for every person · straight-line distance · budgets include your entered per-person estimate')
    start=local_start(outing_date,outing_time,planning_zone)
    if source=='Synthetic Dallas demo':
        st.caption('Fictional venues, sample prices and sample hours. No external API calls in this catalog.')
        st.session_state.catalog=[p.model_dump() for p in demo_places()]
    elif st.button('Find live places',icon=':material/search:'):
        if clocktime.monotonic()-st.session_state.get('last_discovery',-1000)<30:
            raise ValueError('Please wait 30 seconds between discovery requests. You can enter a checked venue directly below.')
        st.session_state.last_discovery=clocktime.monotonic()
        with st.spinner('Finding real places near your group’s starting locations…'):
            places=discover(source,profiles[0].lat,profiles[0].lon)
        st.session_state.catalog=[p.model_dump() for p in places]
        st.session_state.catalog_source=source
        st.success(f'{len(places)} places returned by {source}. Details still need reviewing.')
    if source!='Synthetic Dallas demo':
        with st.expander('Add a venue directly — no discovery API needed'):
            st.caption('Use details you checked directly with the venue. These are your entries, not API-verified facts.')
            with st.form('manual_venue'):
                manual_name=st.text_input('Venue name',max_chars=100)
                manual_address=st.text_input('Full venue street address',max_chars=500)
                manual_category=st.selectbox('Venue category',['Restaurant','Activity'])
                manual_lat=st.number_input('Venue latitude',min_value=-90.0,max_value=90.0,value=float(profiles[0].lat),format='%.6f')
                manual_lon=st.number_input('Venue longitude',min_value=-180.0,max_value=180.0,value=float(profiles[0].lon),format='%.6f')
                manual_cost=st.number_input('Your checked total estimate per person (USD)',min_value=0.0,max_value=1000.0,value=25.0)
                manual_hours=st.text_input('Date-checked hours (e.g. Mo-Su 10:00-22:00)')
                manual_interests=st.multiselect('What does it offer?',INTERESTS)
                manual_diets=st.multiselect('Confirmed dietary options',DIETS)
                manual_access=st.checkbox('Venue confirmed step-free / wheelchair access')
                manual_zone=st.selectbox('Venue local timezone',list(dict.fromkeys([planning_zone]+US_ZONES)),key='manual_zone')
                manual_url=st.text_input('Official venue website')
                manual_check=st.checkbox('I checked the location, cost, hours and required features for our outing date')
                if st.form_submit_button('Add my checked venue'):
                    if not manual_check or not manual_name.strip() or not manual_hours.strip():raise ValueError('Enter the venue name and hours, then confirm your checks.')
                    entry=Place(id='verified-'+uuid.uuid4().hex,name=manual_name.strip(),category=manual_category,address=manual_address.strip(),timezone=manual_zone,lat=manual_lat,lon=manual_lon,cost=manual_cost,hours=manual_hours,
                        interests=manual_interests,diets=manual_diets,accessible=manual_access,website=safe_url(manual_url),source='Organizer-verified venue details',source_url=safe_url(manual_url),description='Entered by your group after direct venue review.')
                    st.session_state.catalog=st.session_state.get('catalog',[])+[entry.model_dump()]
                    st.session_state.shortlist=[]
                    st.success('Venue added. Build a fresh shortlist below.')
    catalog=[Place.model_validate(p) for p in st.session_state.get('catalog',[])]
    if source!='Synthetic Dallas demo':
        catalog=[p for p in catalog if not p.synthetic and ((source=='OpenStreetMap' and p.id.startswith('osm-')) or (source=='Google Places' and p.id.startswith(('google-','verified-'))) or (source=='Foursquare' and p.id.startswith(('fsq-','verified-'))))]
        if catalog:
            with st.expander('Review real venue details before recommending',expanded=True):
                choices={p.id:p for p in catalog}
                place_id=st.selectbox('Venue to check',list(choices),format_func=lambda pid:choices[pid].name)
                place=choices[place_id]
                st.write(place.description)
                st.caption(f'{place.source} · retrieved {place.retrieved_at}')
                if safe_url(place.source_url):st.link_button('View source',place.source_url)
                if safe_url(place.website):st.link_button('Venue website',place.website)
                st.write('Reported hours: '+(place.hours or 'Unknown'))
                with st.form('verify_venue'):
                    st.caption('Enter details you independently checked with the venue for your selected date. Unknowns are excluded from the shortlist. Photo imagery remains illustrative.')
                    verified_name=st.text_input('Venue name checked with the venue',value='' if source=='Google Places' else place.name)
                    verified_address=st.text_input('Full street address checked with the venue',value='' if source=='Google Places' else place.address,max_chars=500)
                    cost=st.number_input('Verified/organizer-estimated total cost per person (USD)',min_value=0.0,max_value=1000.0,value=float(place.cost or 0))
                    hours=st.text_input('Checked opening hours (e.g. Mo-Su 10:00-22:00)',value='' if source=='Google Places' else place.hours)
                    vd=st.multiselect('Dietary options confirmed',DIETS,default=[])
                    va=st.checkbox('Step-free / wheelchair access confirmed')
                    vi=st.multiselect('Interests this place offers',INTERESTS,default=[] if source=='Google Places' else place.interests)
                    vlat=st.number_input('Verified venue latitude',min_value=-90.0,max_value=90.0,value=None if source=='Google Places' else float(place.lat),format='%.6f')
                    vlon=st.number_input('Verified venue longitude',min_value=-180.0,max_value=180.0,value=None if source=='Google Places' else float(place.lon),format='%.6f')
                    verified_zone=st.selectbox('Checked venue timezone',list(dict.fromkeys([planning_zone]+US_ZONES)),key='verified_zone')
                    official=st.text_input('Official venue URL checked',value='' if source=='Google Places' else place.website)
                    checked=st.checkbox('I checked these details for our outing date, including exceptions or holiday hours')
                    if st.form_submit_button('Save reviewed venue'):
                        if not checked or not verified_name or not hours or vlat is None or vlon is None:raise ValueError('Check the venue details and fill the name and hours first.')
                        verified=place.model_copy(update={'id':'verified-'+place.id,'name':verified_name,'address':verified_address.strip(),'lat':vlat,'lon':vlon,'timezone':verified_zone,'cost':cost,'hours':hours,'diets':vd,'accessible':va,'interests':vi,'website':safe_url(official),'source':'Organizer-verified venue details','source_url':safe_url(official),'description':'Date-specific details entered after organizer review.'})
                        # Google content is for transient lookup only; durable decisions use independently entered venue details.
                        st.session_state.catalog=[p.model_dump() for p in catalog if p.id!=verified.id]+[verified.model_dump()]
                        st.session_state.shortlist=[]
                        st.success('Reviewed venue saved for this browser session. Rebuild the shortlist below.')
        catalog=[p for p in [Place.model_validate(v) for v in st.session_state.get('catalog',[])] if p.id.startswith('verified-')]
        st.caption('Live venues require reviewed cost, hours and required accommodations before voting. Google lookup content is not mirrored into permanent storage.')
    if st.button('Let the referee find a fair plan',type='primary',icon=':material/auto_awesome:',disabled=not catalog):
        with st.status('Personal advocates are getting to know your people…',expanded=True) as status:
            outputs=process_profiles(profiles,mode)
            st.write(f'{len(outputs)} independent profiles processed; all workers completed.')
            places=catalog
            if use_graph:
                s.owner(key)
                if any(p.source.startswith('Google') for p in places):raise ValueError('Review Google-discovered venue details independently before graph storage.')
                with Graph() as graph:
                    graph.sync(group,profiles,places)
                    ids=graph.candidate_ids(group['id'])
                    places=[p for p in places if p.id in ids]
                st.write('Neo4j checked shared geographic reach using point.distance.')
            proposals,rejected=rank_options(profiles,places,start,duration)
            intro=coordinate(profiles,proposals,mode,outputs)
            st.session_state.update(shortlist=[p.model_dump() for p in proposals],rejected=rejected,advocates=outputs,coordinator=intro,
                plan_start=start.isoformat(),plan_timezone=planning_zone,plan_duration=duration,plan_title=title,plan_graph=use_graph)
            status.update(label='Your shared ground, found.',state='complete',expanded=False)
    if st.session_state.get('advocates'):
        with st.expander('Meet your personal advocates'):
            by_id={p.id:p.name for p in profiles}
            for result in st.session_state.advocates:
                st.markdown('**'+by_id[result['person_id']]+'**');st.write(result['summary'])
                if result['questions']:st.caption('Clarify: '+' · '.join(result['questions']))
            st.caption('Advocates summarize only. Saved budgets and mandatory requirements are never overwritten by an LLM.')
    proposals=[Proposal.model_validate(p) for p in st.session_state.get('shortlist',[])]
    if st.session_state.get('coordinator'):st.write(st.session_state.coordinator)
    if proposals:
        st.caption('Shortlist prepared for '+datetime.fromisoformat(st.session_state.plan_start).strftime('%B %d, %I:%M %p')+' '+st.session_state.get('plan_timezone','America/Chicago')+'. Change controls and rebuild to create a different shortlist.')
        for column,(i,p) in zip(st.columns(len(proposals)),enumerate(proposals)):
            with column,st.container(border=True):
                st.caption('THE FAIREST FIT' if i==0 else 'ANOTHER GOOD STORY')
                st.subheader(p.place.name)
                st.caption(('Synthetic demo · ' if p.place.synthetic else '')+p.place.category)
                st.write(p.place.description)
                st.metric('Per person',f'${p.place.cost:g}')
                st.caption(f'Lowest fit {p.minimum_score:.0f}/100 · average {p.average_score:.0f}/100')
                st.progress(p.minimum_score/100)
                st.write(p.explanation)
                for person in profiles:st.caption(f'{person.name}: {p.distances[person.id]:.1f} miles · fit {p.scores[person.id]:.0f}/100')
                st.caption('Reported open for the full visit · '+p.place.source)
        if s.group(key)['owner']==member['id'] and st.button('These are our options — open the poll',type='primary'):
            # Use frozen generation inputs, not controls that may have changed since scoring.
            frozen_start=datetime.fromisoformat(st.session_state.plan_start)
            checked,_=rank_options(s.profiles(key),[p.place for p in proposals],frozen_start,st.session_state.plan_duration)
            if {p.place.id for p in checked}!={p.place.id for p in proposals}:raise ValueError('Profiles changed. Rebuild your shortlist before opening the poll.')
            s.start_poll(key,st.session_state.plan_title,frozen_start,st.session_state.plan_duration,checked,st.session_state.get('plan_timezone','America/Chicago'))
            st.session_state.page='The vote';st.rerun()
    if st.session_state.get('rejected'):
        with st.expander('Why some places did not make the cut'):
            for item in st.session_state.rejected:st.write(f"{item['place']['name']}: "+'; '.join(item['reasons']))
    if source!='Synthetic Dallas demo' and st.button('Check the weather for our day'):
        result=weather(profiles[0].lat,profiles[0].lon,outing_date,planning_zone)
        st.info(f"Forecast: high {result['high_f']}°F · rain chance {result['rain_probability']}%. Source: Open-Meteo. Forecast is advisory; no venue hours are inferred from weather.")


def vote_page():
    st.title('A plan worth saying yes to.')
    st.caption('Older detailed voting screen. Current simple groups vote and agree on a venue on Your group.')
    key=require_group()
    if not key:return
    s=store();session=s.session(key)
    if not session:
        st.info('Your organizer can open a poll after generating a shared shortlist.');return
    if session.get('kind')=='simple':
        st.info('This outing was planned on Your group. Its photos and memories are available in Our adventures.')
        st.button('Open our adventures',on_click=go,args=('Our adventures',))
        return
    meeting_card(session)
    st.subheader(session['title'])
    st.caption(f"{session_moment(session).strftime('%A, %B %d · %I:%M %p %Z')} · {session['timezone'] or 'America/Chicago'} · {session['duration']} minutes · {len(session['people'])} people")
    st.badge(session['status'].capitalize(),color='green' if session['status'] in {'finalized','completed'} else 'orange')
    m=s.member(key);g=s.group(key);ballots=s.ballots(key,session['id'])
    if session['status']=='voting':
        st.write('One editable ballot per person. No one gets volunteered for an outing they cannot join.')
        existing={r['place_id']:r['value'] for r in ballots if r['member_id']==m['id']}
        with st.form('ballot_'+session['id']+'_'+m['id']):
            choices={}
            for option in session['options']:
                p=Proposal.model_validate(option)
                st.markdown(f"**{p.place.name}** · ${p.place.cost:g}/person")
                st.caption(p.explanation)
                label=st.radio('How do you feel about '+p.place.name,['Would join','Maybe','Can’t join'],index={2:0,1:1,0:2}[existing.get(p.place.id,1)],horizontal=True,key='choice_'+session['id']+p.place.id+m['id'])
                choices[p.place.id]={'Would join':2,'Maybe':1,'Can’t join':0}[label]
            if st.form_submit_button('Save my vote',type='primary'):
                s.vote(key,session['id'],choices);st.rerun()
        voters={r['member_id'] for r in ballots}
        st.progress(len(voters)/len(session['people']))
        st.caption(f"{len(voters)} of {len(session['people'])} people have voted. Use Refresh to see votes from other browsers.")
        for p in session['people']:st.write(('✓ ' if p['id'] in voters else '○ ')+p['name'])
        if m['id']==g['owner'] and st.button('Close poll and propose the winner',disabled=len(voters)!=len(session['people']),type='primary'):
            s.close_poll(key,session['id']);st.rerun()
    if session['status'] in {'confirming','finalized','completed'}:
        winner=next(p for p in session['options'] if p['place']['id']==session['winner'])
        place=Place.model_validate(winner['place'])
        with st.container(border=True):
            st.caption('YOUR SHARED YES')
            st.header(place.name)
            st.write(place.description)
            st.markdown(f"**${place.cost:g} per person** · {place.category}")
            for person in session['people']:st.caption(f"{person['name']}: {winner['distances'][person['id']]:.1f} straight-line miles")
        if session['status']=='confirming':
            confirmations=s.confirmations(key,session['id'])
            st.info('The poll has a winner. Everyone must confirm this exact place and time before we finalize it.')
            st.caption(f"{len(confirmations)} of {len(session['people'])} confirmations")
            if m['id'] not in confirmations and st.button('Yes — I confirm this plan',type='primary'):
                s.confirm(key,session['id']);st.rerun()
        if session['status']=='finalized':
            st.success('Everyone confirmed. '+('The organizer has reported a booked and approved venue.' if session['booked_at'] else 'The plan is final; a reservation has not been made.'))
            with st.expander('Would you like help reserving for the group?',expanded=True):
                st.write(f"Party of {len(session['people'])} · {place.name} · {session_moment(session).strftime('%B %d, %I:%M %p %Z')}")
                st.caption('Review the venue’s availability, total cost and cancellation policy on its booking page. Opening a link does not create a reservation.')
                if place.synthetic:
                    st.info('This is a fictional demo venue. Booking is simulated; no real reservation can be made.')
                elif safe_url(place.website):
                    if st.checkbox('I want to open the venue website and review booking options',key='reservation_consent'):
                        st.link_button('Continue to the venue website',place.website,type='primary')
                else:st.info('No verified booking URL is available. Contact the venue directly; the app cannot place this reservation.')
                st.text_area('Your group plan to copy',value=f"{place.name}\n{session['start']}\nParty of {len(session['people'])}\nDuration: {session['duration']} minutes\nBudget estimate: ${place.cost:g} per person",disabled=True)
                if m['id']==g['owner']:
                    with st.form('reservation_note'):
                        note=st.text_input('Optional booking reference or note (entered by you)',value=session['booking'],max_chars=300)
                        if st.form_submit_button('Save booking note'):
                            s.booking_note(key,session['id'],note);st.rerun()
                    if session['booking']:st.caption('Organizer-reported booking note. The app has not independently verified a reservation.')
                    if not place.synthetic and not g['demo']:
                        with st.form('booking_approval'):
                            reference=st.text_input('Actual booking reference from the venue',max_chars=300)
                            approved=st.checkbox('As group coordinator, I approve this exact booking and confirm the venue accepted our reservation for this party, date and time')
                            if st.form_submit_button('Record booking and coordinator approval',disabled=bool(session['booked_at'])):
                                s.confirm_booking(key,session['id'],reference,approved);st.rerun()
                        if session['booked_at']:
                            st.markdown('**Booking text preview**')
                            st.code(message_body(session),language=None)
                            recipients=s.sms_recipients(key,session['id'])
                            eligible=[p for p in recipients if p['opt_in'] and p['phone']]
                            st.caption(f"{len(eligible)} of {len(recipients)} members opted in. Members without consent or a number will not be texted.")
                            for person in recipients:st.caption(person['name']+(': opted in' if person in eligible else ': not receiving SMS'))
                            if st.button('Send booking text to opted-in members',type='primary',disabled=not eligible):
                                notify_booking(s,key,session['id']);st.rerun()
                            if st.button('Refresh text delivery status'):
                                refresh_statuses(s,key,session['id']);st.rerun()
                            for item in s.sms_statuses(key,session['id']):
                                st.write(f"{item['name']}: {item['status']}")
                                if item['error']:st.caption(item['error'])
                            st.caption('Queued or sent does not mean delivered. Each recipient is attempted once for this booking; uncertain outcomes are never automatically retried.')

            if m['id']==g['owner']:
                happened=st.checkbox('Our outing has happened — we are ready to save memories',key='outing_happened')
                if st.button('Mark completed and open the scrapbook',disabled=not happened,type='primary'):
                    s.complete(key,session['id']);st.session_state.page='Our adventures';st.rerun()
        if session['status']=='completed':
            st.success('This outing is ready for your memories.')
            st.button('Open our scrapbook',on_click=go,args=('Our adventures',))
    st.button('Refresh group responses',icon=':material/refresh:',key='refresh_votes')


def memories_page():
    st.title('The good part was being there.')
    st.write('Your group’s photos and memories, together in one place. Any member can add moments from a completed adventure; everyone still in the group can see them.')
    key=require_group()
    if not key:return
    s=store()
    from .simple import SimplePlans
    from .meetup import Meetups
    simple=SimplePlans(s)
    if simple.plan(key):
        meetup=Meetups(simple)
        outing=meetup.current(key)
        if outing and outing['status']=='finalized' and not outing.get('adventure_id'):
            venue=next(p['place'] for p in outing['places'] if p['place']['id']==outing['winner'])
            with st.container(border=True):
                st.subheader('Ready to save this adventure?')
                st.text(venue['name'])
                if s.member(key)['id']==s.group(key)['owner']:
                    happened=st.checkbox('This outing has taken place and is ready for our photos')
                    if st.button('Mark adventure completed',disabled=not happened,type='primary'):
                        meetup.complete(key);st.rerun()
                else:st.info('Your coordinator can mark this adventure completed here to enable photo uploads.')
    if s.member(key)['id']==s.group(key)['owner']:
        with st.expander('Add a past adventure',expanded=False):
            st.caption('Already went somewhere together? Record it here to share photos without using venue search.')
            with st.form('past_adventure'):
                past_title=st.text_input('Adventure name',max_chars=100,placeholder='Coffee and catch-up in Prosper')
                past_day=st.date_input('When did it happen?',value=datetime.now(ZoneInfo('America/Chicago')).date())
                past_happened=st.checkbox('This is a past group outing')
                if st.form_submit_button('Create adventure for photos'):
                    if not past_happened:st.warning('Confirm this outing has already happened.')
                    else:
                        try:s.add_past_adventure(key,past_title,past_day.isoformat())
                        except ValueError as exc:st.warning(str(exc))
                        else:st.rerun()
    completed=s.completed_sessions(key);memories=s.memories(key)
    if completed:
        with st.container(border=True):
            st.subheader('Add photos and memories')
            sessions={p['id']:p for p in completed}
            sid=st.selectbox('Which adventure?',list(sessions),format_func=lambda i:sessions[i]['title']+' · '+sessions[i]['start'][:10])
            with st.form('memory_upload',clear_on_submit=True):
                caption=st.text_area('Tell the little story',max_chars=1500,placeholder='We came for the coffee. We stayed for the three-hour conversation.')
                uploads=st.file_uploader('Your photos (up to 8, 12 MB each)',type=['jpg','jpeg','png','webp'],accept_multiple_files=True,help='Select one or more photos. Add a caption, confirm sharing permission and click Keep this memory.')
                a,b=st.columns(2)
                with a:rating=st.slider('How was it?',1,5,5)
                with b:again=st.checkbox('Would happily do it again',value=True)
                permission=st.checkbox('I have permission to share these photos with my group')
                if st.form_submit_button('Keep this memory',type='primary'):
                    if not permission:raise ValueError('Confirm you can share these photos with the group.')
                    if not caption.strip() and not uploads:raise ValueError('Add a caption or a photo.')
                    s.add_memory(key,sid,caption,rating,again,[f.getvalue() for f in uploads]);st.rerun()
    else:
        st.info('Photo sharing opens after an outing is marked completed. Agree on your meetup venue in Your group, then the coordinator can mark the adventure completed here after it happens.')
        st.file_uploader('Your photos (up to 8, 12 MB each)',type=['jpg','jpeg','png','webp'],accept_multiple_files=True,disabled=True,help='The coordinator must mark an agreed outing completed before photos can be saved.')
    live_memory_gallery(key)


@st.fragment(run_every='5s')
def live_memory_gallery(key):
    s=store()
    try:
        s.member(key)
    except ValueError:
        for name in list(st.session_state):del st.session_state[name]
        st.session_state.update(page='Home',notice='Your group access has ended.')
        st.rerun()
    memories=s.memories(key)
    st.caption('Shared with your group · Gallery updates about every 5 seconds while this page is open.')
    if not memories:
        st.image(str(ROOT/'assets/dallas-after-hours.png'),caption='Your next shared story starts here. Illustrative AI-generated image.',alt='Friends together at a rooftop dinner, illustrating future group memories',width='stretch')
        return
    members={r['id']:r['name'] for r in s.roster(key)}
    who=st.selectbox('Memories by', ['Everyone']+list(members),format_func=lambda x:members.get(x,x))
    filtered=[m for m in memories if who=='Everyone' or m['member_id']==who]
    for row in filtered:
        with st.container(border=True):
            st.subheader(row['title'])
            st.caption(f"{row['start'][:10]} · Shared by {row['name']} · {row['rating']}/5 · "+('Do it again!' if row['again'] else 'A one-time adventure'))
            st.write(row['caption'])
            if row['photos']:
                cols=st.columns(min(3,len(row['photos'])))
                for i,photo in enumerate(row['photos']):
                    with cols[i%len(cols)]:st.html(inline_photo(s.photo_bytes(key,photo['id']),f"Group memory from {row['title']}, uploaded by {row['name']}"))
            if s.member(key)['id']==row['member_id']:
                if st.button('Delete my memory and its photos',key='delete_'+row['id']):
                    s.delete_memory(key,row['id']);st.rerun()
    st.caption('Photos are stored locally, with EXIF metadata removed. No photos or captions are sent to an LLM. Images are embedded in your authorized session rather than shared media URLs. Group membership keys gate access inside this local prototype.')


def help_page():
    st.title('A good plan deserves a good explanation.')
    st.caption('How friends turn shared interests and real spending limits into a meetup and memories.')
    overview,architecture,setup,privacy=st.tabs(['The plan','Architecture','Connections & setup','Privacy & limits'])
    with overview:
        usage_guide()
        st.caption('The current flow uses one shared meetup ZIP code. Search tiles cover roughly 10 straight-line miles around that ZIP, not 50 miles from every member. Individual travel, exact availability, accessibility and dietary needs still require a human check.')
    with architecture:
        st.subheader('How After Hours is built')
        video=ROOT/'demo/walkthrough.mp4'
        if video.exists():
            st.video(video,subtitles=ROOT/'demo/captions.vtt',alt='Captioned architecture walkthrough with a synthetic group decision, voting and meetup example')
            st.caption('Code-generated, silent slide walkthrough; not a screen recording. Regenerate after edits or run the demo watcher.')
            manifest=ROOT/'demo/manifest.json'
            if manifest.exists():
                info=json.loads(manifest.read_text())
                st.caption('Video generated: '+info['generated_at']+' · source '+info['source_sha256'][:10])
            with st.expander('Read the video transcript'):
                transcript=ROOT/'demo/transcript.txt'
                if transcript.exists():st.text(transcript.read_text())
        else:
            st.info('Generate the walkthrough with: python scripts/build_demo.py')
        st.graphviz_chart('''digraph { rankdir=LR; bgcolor="transparent"; node [shape=box style="rounded,filled" fillcolor="#243b45" fontcolor="#f7efe4"]; edge [color="#ffad85"]; "Create + invite" -> "Individual responses" -> "Activity agreement" -> "Venue tiles + votes" -> "Coordinator confirms" -> "Meetup + shared photos"; "Individual responses" -> "Budget + consensus rules"; "Place APIs" -> "Venue tiles + votes"; "Budget + consensus rules" -> "Optional AI suggestion" -> "Coordinator confirms"; "SQLite + private files" -> "Meetup + shared photos"; }''',width='stretch')
        st.markdown("""| Component | Current role |
|---|---|
| Streamlit | Home, Your group, Our adventures and Help |
| SQLite | Groups, memberships, responses, venue rounds, votes and memories |
| Python rules | Activity consensus, lowest definite attendee budget, venue vetoes and final approval |
| Geoapify + ZIP lookup | Nearby tiles and available hours; missing details remain unknown |
| Codex CLI, optional | Explains shared choices and recommends only eligible listed venues after consent |
| Private photo files | Validated, re-encoded images with metadata stripped; group-scoped gallery |

The assistant receives aliased responses and supplied venue facts, not membership keys, photos or contact details. Python validates its selected ID and rejects stale results. It cannot finalize, book or send messages.

The default experience does not run parallel advocates or Neo4j matching. Those original learning modules remain for older groups; they are not required to use the current meetup flow. Mem0 is not connected.
""")
        st.code('referee/simple.py         # group creation, responses, personal budgets\nreferee/common_ground.py  # optional activity recommendation\nreferee/nearby.py         # ZIP-based venue search\nreferee/meetup.py         # venue rounds, votes and agreement\nreferee/store.py          # persistent state and private photos\nreferee/membership.py     # leave and coordinator transfer\nreferee/ui.py             # pages, shared gallery and help',language='text')
    with setup:
        st.markdown("""**Run locally**
```bash
cd week2
.venv/bin/streamlit run streamlit_app.py --server.port 8502 --server.address 127.0.0.1
```
**Creator accounts:** copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, register a Google OAuth web client and set its client ID, client secret, callback URL and a random cookie secret. Follow `README.md` for host setup. Passwords are handled by Google; no password is stored by this app.\n\n**Nearby search:** the host configures `GEOAPIFY_API_KEY` in the ignored `.env` once, then restarts Streamlit. Members never enter keys. Searches run only when requested; provider failures do not produce invented fallback venues. Ratings and dollar estimates are often unavailable and must be checked separately.

**Optional AI:** the host installs Codex CLI and uses `codex login`. `CODEX_BIN` can specify its location. Every attending or tentative member must opt in before real group analysis. The Dallas demo uses offline rules.

**Storage:** SQLite and private photo files are saved under the configured `REFEREE_DATA_DIR`. Back up both together. This is local server storage, not cloud account sync.

**Sharing and accounts:** secure hosting, host-configured Google sign-in and durable private cloud media are required before remote use. Creator account support is implemented; configure it before creating a real event. Changing `PUBLIC_APP_URL` alone does not deploy the app or add authentication. The localhost restriction remains enabled.

**Reservations and messages:** the current simple flow records a venue agreement. It does not make reservations or send booking notifications. Text invitations are drafts reviewed in your messaging app. The older detailed workflow has a separately configured booking/SMS handoff; it is not part of the default meetup flow.

**Demo updates:** `python scripts/build_demo.py` rebuilds the captioned walkthrough. Run `python scripts/build_demo.py --watch` while editing to rebuild automatically. The video uses synthetic data and is a slide walkthrough, not a screen recording.
""")
    with privacy:
        st.markdown("""- Event creation requires a verified Google sign-in configured by the host. Guests joining invitations still use prototype membership sessions; Google sign-in alone does not secure guest access for production. Keep it on localhost with sample data until production authentication, authorization and private hosting are added.
- Invitation links expire after seven days and can be replaced by the coordinator. They grant new membership, not recovery of an existing identity. Existing prototype membership keys are stored hashed; do not share them.
- Group members can see group responses, votes and shared memories. Do not put private contact details in wishes or captions. AI analysis is optional; consenting response text and supplied venue details go to the host’s AI service. Personal tracing is disabled.
- Photos are not sent to the LLM. Uploads are validated, re-encoded and stripped of EXIF metadata. Gallery access is checked against membership. Uploaders can delete their own memories; leaving can optionally delete them too. Copies already downloaded by others cannot be recalled.
- Leaving revokes membership access. A coordinator transfers responsibility when others remain. Confirmed venue history and memories are retained unless the uploader deletes their own entries.
- Budget checks use entered estimates, not a guaranteed final bill. Unknown price, hours, ratings, dietary suitability, accessibility and booking availability need checking. Tentative members are not treated as confirmed attendees.
- A ZIP search radius is straight-line distance from a ZIP center, not each member’s travel route. The current simple flow does not enforce the older 50-mile-per-member rule.
- The Dallas demo, its venues and the landing illustration are synthetic. Failed services never silently substitute fictional places for real results.
""")
