"""ZIP lookup and nearby Geoapify places, requested on demand."""
import re
import math
from .providers import fetch, geoapify, ProviderError
from .decision import miles


PLACE_CATEGORIES={
    'All categories':None,
    'Coffee shops':['catering.cafe'],
    'Restaurants':['catering.restaurant'],
    'Parks and gardens':['leisure.park'],
    'Museums and sights':['entertainment.museum','tourism.sights'],
}


def find_places(zipcode,categories=None):
    if not re.fullmatch(r'\d{5}',zipcode):raise ValueError('Enter a five-digit US ZIP code.')
    try:
        data=fetch('GET','https://api.zippopotam.us/us/'+zipcode,timeout=(5,12))
    except ProviderError as exc:
        if exc.status==404:raise ProviderError('This US ZIP code was not found. Check the ZIP and try again.') from None
        raise ProviderError('ZIP lookup failed: '+str(exc)) from None
    if not isinstance(data,dict):raise ProviderError('ZIP lookup returned an invalid result.')
    rows=data.get('places',[])
    if not rows:raise ProviderError('No location was found for this ZIP code.')
    origin=rows[0]
    try:lat,lon=float(origin['latitude']),float(origin['longitude'])
    except (KeyError,TypeError,ValueError):raise ProviderError('The ZIP lookup did not return usable coordinates.') from None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ProviderError('ZIP lookup returned invalid coordinates.')
    found=geoapify(lat,lon,radius=16093,**({'categories':categories} if categories else {}))
    places=[]
    for place in found:
        distance=miles(lat,lon,place.lat,place.lon)
        if distance<=10:places.append((distance,place))
    places.sort(key=lambda row:(row[0],row[1].name,row[1].id))
    return {'zip':zipcode,'area':origin.get('place name','')+', '+origin.get('state abbreviation',''),
            'places':[dict(place=p.model_dump(),miles=round(d,1)) for d,p in places[:24]]}
