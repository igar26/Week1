"""Meetup summaries and destination-only Google Maps links; no network requests."""
from datetime import timedelta, timezone
from urllib.parse import urlencode
from .geography import session_moment
from .models import Place


def duration_label(minutes):
    hours, remainder = divmod(minutes, 60)
    return ' '.join(part for part in (
        f'{hours} hour' + ('s' if hours != 1 else '') if hours else '',
        f'{remainder} minute' + ('s' if remainder != 1 else '') if remainder else '',
    ) if part) or '0 minutes'


def meeting_details(session):
    start = session_moment(session)
    end = (start.astimezone(timezone.utc) + timedelta(minutes=session['duration'])).astimezone(start.tzinfo)
    winner = next((p['place'] for p in session['options'] if p['place']['id'] == session.get('winner')), None)
    status = {
        'voting': 'Options are auditioning',
        'confirming': 'The winner needs everyone’s yes',
        'finalized': 'Everyone said yes · reservation pending',
        'completed': 'Adventure accomplished',
    }.get(session['status'], 'Plan coming soon')
    if session['status'] == 'finalized' and session.get('booked_at'):
        status = 'Booked · coordinator approved'
    return {'start': start, 'end': end, 'duration': duration_label(session['duration']),
            'place': Place.model_validate(winner) if winner else None, 'status': status}


def maps_links(place):
    if place.synthetic:
        return {}
    destination = f'{place.name}, {place.address}' if place.address.strip() else f'{place.lat},{place.lon}'
    return {
        'View venue on Google Maps': 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': destination}),
        'Get directions': 'https://www.google.com/maps/dir/?' + urlencode({'api': 1, 'destination': destination}),
    }
