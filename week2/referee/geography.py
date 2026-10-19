"""US city search and explicit local time zones, with a small offline starter list."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .providers import fetch,HEADERS

US_ZONES=['America/New_York','America/Chicago','America/Denver','America/Phoenix',
          'America/Los_Angeles','America/Anchorage','America/Adak','Pacific/Honolulu',
          'America/Indiana/Indianapolis','America/Detroit','America/Boise']

# Starter choices work offline; API search supports US cities and ZIP codes beyond this list.
STARTERS=[
 ('Dallas','Texas',32.7767,-96.7970,'America/Chicago'),
 ('Plano','Texas',33.0198,-96.6989,'America/Chicago'),
 ('Irving','Texas',32.8140,-96.9489,'America/Chicago'),
 ('Richardson','Texas',32.9483,-96.7299,'America/Chicago'),
 ('Austin','Texas',30.2672,-97.7431,'America/Chicago'),
 ('Houston','Texas',29.7604,-95.3698,'America/Chicago'),
 ('New York','New York',40.7128,-74.0060,'America/New_York'),
 ('Los Angeles','California',34.0522,-118.2437,'America/Los_Angeles'),
 ('San Francisco','California',37.7749,-122.4194,'America/Los_Angeles'),
 ('Seattle','Washington',47.6062,-122.3321,'America/Los_Angeles'),
 ('Chicago','Illinois',41.8781,-87.6298,'America/Chicago'),
 ('Denver','Colorado',39.7392,-104.9903,'America/Denver'),
 ('Phoenix','Arizona',33.4484,-112.0740,'America/Phoenix'),
 ('Miami','Florida',25.7617,-80.1918,'America/New_York'),
 ('Atlanta','Georgia',33.7490,-84.3880,'America/New_York'),
 ('Boston','Massachusetts',42.3601,-71.0589,'America/New_York'),
 ('Washington','District of Columbia',38.9072,-77.0369,'America/New_York'),
 ('Anchorage','Alaska',61.2181,-149.9003,'America/Anchorage'),
 ('Honolulu','Hawaii',21.3099,-157.8581,'Pacific/Honolulu'),
]


def starters():
    return [{'label':f'{n}, {state}', 'city':n,'state':state,'lat':lat,'lon':lon,'timezone':tz}
            for n,state,lat,lon,tz in STARTERS]


def search_us(query):
    query=query.strip()
    if len(query)<2:raise ValueError('Enter a US city or ZIP code, optionally followed by its state.')
    data=fetch('GET','https://geocoding-api.open-meteo.com/v1/search',headers=HEADERS,
               params={'name':query,'countryCode':'US','count':30,'language':'en','format':'json'})
    result=[]
    for row in data.get('results',[]):
        if row.get('country_code')!='US':continue
        tz=row.get('timezone','')
        try:ZoneInfo(tz)
        except (ZoneInfoNotFoundError,ValueError):continue
        if 'latitude' not in row or 'longitude' not in row:continue
        city,state=row['name'],row.get('admin1','')
        county=row.get('admin2','')
        result.append({'label':', '.join(x for x in [city,state,county] if x),'city':city,'state':state,
                       'lat':row['latitude'],'lon':row['longitude'],'timezone':tz})
    return result


def local_start(day,clock,timezone_name):
    """Reject DST gaps and ambiguous times rather than silently choosing an instant."""
    zone=ZoneInfo(timezone_name);naive=datetime.combine(day,clock)
    first=naive.replace(tzinfo=zone,fold=0)
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=naive:
        raise ValueError('That local time does not exist during the daylight-saving change. Choose another time.')
    if first.utcoffset()!=naive.replace(tzinfo=zone,fold=1).utcoffset():
        raise ValueError('That local time occurs twice during the daylight-saving change. Choose an unambiguous time.')
    return first


def session_moment(session):
    zone=ZoneInfo(session.get('timezone') or 'America/Chicago')
    moment=datetime.fromisoformat(session['start'])
    return moment.replace(tzinfo=zone) if moment.tzinfo is None else moment.astimezone(zone)
