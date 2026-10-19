"""Read-only external discovery. Missing data stays unknown; no LLM fabricates hours."""
import os
import time
import threading
import math
from datetime import datetime, timezone, date
from urllib.parse import urlsplit
import requests
from zoneinfo import ZoneInfo
from .models import Place

HEADERS={'User-Agent':'DallasAfterHours-LearningProject/1.0','Accept':'application/json'}


class ProviderError(RuntimeError):
    def __init__(self,message,status=None):
        super().__init__(message)
        self.status=status


OVERPASS_ENDPOINTS=(
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)
_overpass_cooldowns={}
_overpass_lock=threading.Lock()



def safe_url(url):
    try:
        p=urlsplit(url or '')
        return url if p.scheme in {'https','http'} and p.hostname and not p.username and not p.password else ''
    except ValueError:return ''


def stamp():return datetime.now(timezone.utc).isoformat()


def fetch(method,url,**kwargs):
    try:
        r=requests.request(method,url,timeout=kwargs.pop('timeout',35),**kwargs)
        if not r.ok:
            raise ProviderError(f'The data service returned HTTP {r.status_code}. Please try again shortly.',status=r.status_code)
        return r.json()
    except requests.Timeout:
        raise ProviderError('The data service timed out. Please try again shortly.') from None
    except requests.RequestException:
        raise ProviderError('The data service could not be reached. Check your network and try again.') from None
    except ValueError:
        raise ProviderError('The data service returned an unreadable response. Please try again shortly.') from None


def overpass_data(query):
    failures=[]
    for endpoint in OVERPASS_ENDPOINTS:
        with _overpass_lock:
            cooling=_overpass_cooldowns.get(endpoint,0)>time.monotonic()
        if cooling:
            failures.append('temporarily paused');continue
        try:
            data=fetch('GET',endpoint,params={'data':query},headers=HEADERS,timeout=(5,20))
            if not isinstance(data,dict) or not isinstance(data.get('elements'),list):
                raise ProviderError('Place service returned an invalid result.')
            if data.get('remark'):
                raise ProviderError('Place service could not complete the search (server runtime error).')
            return data
        except ProviderError as exc:
            failures.append(str(exc))
            # No immediate repeat requests to a failing/rate-limited public server.
            with _overpass_lock:_overpass_cooldowns[endpoint]=time.monotonic()+30
    raise ProviderError('Nearby place search is temporarily unavailable. ZIP lookup may still work. '
                        +' '.join(dict.fromkeys(failures))+' This does not mean there are no nearby places.')


def overpass(lat,lon,radius=80467.2):
    lat,lon,radius=float(lat),float(lon),float(radius)
    if not all(math.isfinite(v) for v in [lat,lon,radius]) or not -90<=lat<=90 or not -180<=lon<=180 or radius<=0:raise ValueError('Invalid place-search coordinates or radius.')
    radius=min(radius,80467.2)
    query=f'''[out:json][timeout:15];(nwr(around:{radius},{float(lat)},{float(lon)})[amenity~"^(restaurant|cafe)$"][name];nwr(around:{radius},{float(lat)},{float(lon)})[tourism~"^(museum|gallery|attraction)$"][name];nwr(around:{radius},{float(lat)},{float(lon)})[leisure=park][name];);out center 160;'''
    data=overpass_data(query)
    result=[]
    for item in data.get('elements',[]):
        t=item.get('tags',{});pos=item.get('center',item)
        if 'lat' not in pos or 'lon' not in pos or not t.get('name') or item.get('type') not in {'node','way','relation'} or 'id' not in item:continue
        food=t.get('amenity') in {'restaurant','cafe'}
        interests=['Food'] if food else ['Outdoors'] if t.get('leisure')=='park' else ['Art','Museums']
        if t.get('amenity')=='cafe':interests+=['Coffee']
        diets=[name for key,name in [('vegetarian','Vegetarian'),('vegan','Vegan'),('gluten_free','Gluten-free')] if t.get('diet:'+key) in {'yes','only'}]
        result.append(Place(id=f"osm-{item['type']}-{item['id']}",name=t['name'],category='Restaurant' if food else 'Activity',lat=pos['lat'],lon=pos['lon'],interests=interests,diets=diets,
            accessible=True if t.get('wheelchair')=='yes' else False if t.get('wheelchair')=='no' else None,
            address=t.get('addr:full') or ', '.join(filter(None,[' '.join(filter(None,[t.get('addr:housenumber'),t.get('addr:street')])),t.get('addr:city'),t.get('addr:state'),t.get('addr:postcode')])),
            hours=t.get('opening_hours',''),website=safe_url(t.get('website',t.get('contact:website',''))),
            source='OpenStreetMap contributors · ODbL',source_url=f"https://www.openstreetmap.org/{item['type']}/{item['id']}",retrieved_at=stamp(),
            description=t.get('description','Community-maintained place details. Cost and suitability may require checking with the venue.')))
    return result


def geoapify(lat,lon,radius=16093,categories=None):
    """Hosted places search; key stays in the server-side request header."""
    key=os.getenv('GEOAPIFY_API_KEY','').strip()
    if not key:raise ProviderError('Nearby places search is not connected yet. Ask the app host to enable the places connection; you can still enter your own choices.')
    lat,lon,radius=float(lat),float(lon),float(radius)
    if not all(math.isfinite(v) for v in [lat,lon,radius]) or not -90<=lat<=90 or not -180<=lon<=180 or not 0<radius<=80467.2:raise ValueError('Invalid place-search coordinates or radius.')
    try:
        data=fetch('POST','https://api.geoapify.com/v2/places',headers={**HEADERS,'x-api-key':key},timeout=(5,20),json={
            'categories':categories or ['catering.restaurant','catering.cafe','leisure.park','entertainment.museum','tourism.sights'],
            'filter':{'type':'circle','lat':lat,'lon':lon,'radius':radius},
            'bias':{'type':'proximity','lat':lat,'lon':lon},'limit':60,'lang':'en'})
    except ProviderError as exc:
        if exc.status in {401,403}:raise ProviderError('The places connection was rejected. Ask the app host to check its Geoapify key and restrictions.',status=exc.status) from None
        if exc.status==429:raise ProviderError('The places service has reached its request allowance. Please try later or ask the host to check usage.',status=429) from None
        raise ProviderError('Geoapify place search failed: '+str(exc),status=exc.status) from None
    if not isinstance(data,dict) or not isinstance(data.get('features'),list):raise ProviderError('Geoapify returned an invalid places response.')
    result=[];seen=set()
    for feature in data['features']:
        if not isinstance(feature,dict):continue
        props=feature.get('properties') or {};point=feature.get('geometry') or {}
        if not isinstance(props,dict) or not isinstance(point,dict):continue
        coords=point.get('coordinates') or []
        try:
            plat=float(props.get('lat',coords[1] if len(coords)>1 else None))
            plon=float(props.get('lon',coords[0] if coords else None))
        except (ValueError,TypeError):continue
        name=props.get('name');pid=props.get('place_id')
        if not isinstance(name,str) or not name.strip() or not pid or str(pid) in seen or not math.isfinite(plat) or not math.isfinite(plon) or not -90<=plat<=90 or not -180<=plon<=180:continue
        seen.add(str(pid))
        cats=props.get('categories') or []
        if not isinstance(cats,list):cats=[]
        food=any(str(c).startswith('catering.') for c in cats)
        interests=['Food'] if food else ['Outdoors'] if any(str(c).startswith('leisure.park') for c in cats) else ['Art','Museums']
        if 'catering.cafe' in cats:interests+=['Coffee']
        raw=(props.get('datasource') or {}).get('raw') or {}
        if not isinstance(raw,dict):raw={}
        address=props.get('formatted') or ', '.join(str(x) for x in [props.get('street'),props.get('city'),props.get('state'),props.get('postcode')] if x)
        hours=raw.get('opening_hours','')
        result.append(Place(id='geoapify-'+str(pid),name=name.strip(),category='Restaurant' if food else 'Activity',lat=plat,lon=plon,
            address=str(address),interests=interests,hours=hours if isinstance(hours,str) else '',website=safe_url(raw.get('website','')),
            source='Geoapify · OpenStreetMap contributors',source_url=f'https://www.openstreetmap.org/?mlat={plat}&mlon={plon}',
            retrieved_at=stamp(),description='Geoapify place listing. Verify hours, price and suitability directly with the venue.'))
    return result


def google(lat,lon):
    key=os.getenv('GOOGLE_PLACES_API_KEY','')
    if not key:raise ProviderError('Set GOOGLE_PLACES_API_KEY in week2/.env to use Google Places.')
    fields='places.id,places.displayName,places.location,places.websiteUri,places.googleMapsUri,places.regularOpeningHours,places.types,places.attributions'
    data=fetch('POST','https://places.googleapis.com/v1/places:searchText',headers={**HEADERS,'X-Goog-Api-Key':key,'X-Goog-FieldMask':fields},
        json={'textQuery':'restaurants museums parks activities','pageSize':20,'locationBias':{'circle':{'center':{'latitude':lat,'longitude':lon},'radius':50000}}})
    results=[]
    for p in data.get('places',[]):
        types=p.get('types',[]);food=any(t in types for t in ['restaurant','cafe','food'])
        # Do not interpret vague Google price levels as exact per-person dollars.
        regular=p.get('regularOpeningHours') or {}
        periods=regular.get('periods',[])
        hours=google_hours(periods)
        attribution='; '.join(a.get('provider','') for a in p.get('attributions',[]))
        results.append(Place(id='google-'+p['id'],name=p['displayName']['text'],category='Restaurant' if food else 'Activity',lat=p['location']['latitude'],lon=p['location']['longitude'],
            interests=['Food'] if food else ['Outdoors'] if 'park' in types else ['Art','Museums'],hours=hours,website=safe_url(p.get('websiteUri','')),
            source='Google Maps'+(' · '+attribution if attribution else ''),source_url=safe_url(p.get('googleMapsUri','')),retrieved_at=stamp(),description='Regular hours from Google Maps. Date-specific holiday hours and booking availability still need checking.'))
    return results


def google_hours(periods):
    days=['Su','Mo','Tu','We','Th','Fr','Sa']
    if len(periods)==1 and periods[0].get('open',{}).get('day')==0 and 'close' not in periods[0]:return '24/7'
    rows=[]
    for p in periods:
        a,b=p.get('open'),p.get('close')
        if not a or not b:return ''
        if b['day'] not in {a['day'],(a['day']+1)%7}:return ''
        rows.append(f"{days[a['day']]} {a.get('hour',0):02}:{a.get('minute',0):02}-{b.get('hour',0):02}:{b.get('minute',0):02}")
    return '; '.join(rows)


def foursquare(lat,lon):
    key=os.getenv('FOURSQUARE_API_KEY','')
    if not key:raise ProviderError('Set FOURSQUARE_API_KEY in week2/.env to use Foursquare.')
    data=fetch('GET','https://places-api.foursquare.com/places/search',headers={**HEADERS,'Authorization':'Bearer '+key,'X-Places-Api-Version':'2025-06-17'},params={'ll':f'{lat},{lon}','radius':50000,'limit':30,'query':'restaurants museums parks','fields':'fsq_place_id,name,latitude,longitude,categories,website,hours'})
    results=[]
    for p in data.get('results',[]):
        pos=p.get('geocodes',{}).get('main',{})
        latitude=p.get('latitude',pos.get('latitude'));longitude=p.get('longitude',pos.get('longitude'))
        if latitude is None or longitude is None:continue
        cats=' '.join(c.get('name','') for c in p.get('categories',[])).lower();food=any(x in cats for x in ['restaurant','cafe','food'])
        hours=p.get('hours') or {};raw='24/7' if hours.get('is_open_24h') else ''
        if not raw:
            lines=[]
            for item in hours.get('regular',[]):
                a,b=item.get('open',''),item.get('close','')
                if len(a)==len(b)==4 and 1<=item.get('day',0)<=7:
                    lines.append(f"{['Mo','Tu','We','Th','Fr','Sa','Su'][item['day']-1]} {a[:2]}:{a[2:]}-{b[:2]}:{b[2:]}")
            raw='; '.join(lines)
        results.append(Place(id='fsq-'+p['fsq_place_id'],name=p['name'],category='Restaurant' if food else 'Activity',lat=latitude,lon=longitude,
            interests=['Food'] if food else ['Outdoors'] if 'park' in cats else ['Art','Museums'],hours=raw,website=safe_url(p.get('website','')),source='Foursquare',retrieved_at=stamp(),description='Provider-supplied details. Check price and requirements directly with the venue.'))
    return results


def discover(source,lat,lon):
    return {'OpenStreetMap':overpass,'Google Places':google,'Foursquare':foursquare}[source](lat,lon)


def weather(lat,lon,day:date,timezone_name="America/Chicago"):
    if not 0<=(day-datetime.now(ZoneInfo(timezone_name)).date()).days<=15:raise ProviderError('Forecasts are available for today through the next 15 days only.')
    data=fetch('GET','https://api.open-meteo.com/v1/forecast',headers=HEADERS,params={'latitude':lat,'longitude':lon,'daily':'temperature_2m_max,precipitation_probability_max','timezone':timezone_name,'temperature_unit':'fahrenheit','start_date':day.isoformat(),'end_date':day.isoformat()})
    daily=data['daily']
    return {'high_f':daily['temperature_2m_max'][0],'rain_probability':daily['precipitation_probability_max'][0],'source':'Open-Meteo','retrieved_at':stamp()}
