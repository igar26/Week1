"""Hard constraints and fairness are calculated in Python, never delegated to an LLM."""
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .models import Place, Profile, Proposal

DALLAS_TZ = ZoneInfo("America/Chicago")
DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def miles(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2-p1, math.radians(b_lon-a_lon)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(a)))


def hours_status(raw: str, start: datetime, duration: int, timezone_name=None):
    """Conservative subset of OSM hours. Complex/holiday expressions stay unknown."""
    zone=ZoneInfo(timezone_name) if timezone_name else (start.tzinfo or DALLAS_TZ)
    start = start.replace(tzinfo=zone) if start.tzinfo is None else start.astimezone(zone)
    end = (start.astimezone(timezone.utc)+timedelta(minutes=duration)).astimezone(zone)
    if raw.strip() == "24/7":
        return "open"
    if raw.strip() in {"off", "closed"}:
        return "closed"
    # Support weekdays, weekday ranges and multiple time intervals. Never guess other syntax.
    windows = []
    for rule in raw.split(";"):
        match = re.fullmatch(r"\s*([A-Za-z,\-]+)\s+((?:\d{2}:\d{2}-\d{2}:\d{2})(?:,\s*\d{2}:\d{2}-\d{2}:\d{2})*|off)\s*", rule)
        if not match:
            return "unknown"
        days, periods = match.groups()
        selected = set()
        try:
            for part in days.split(","):
                if "-" in part:
                    left,right = [DAYS.index(d) for d in part.split("-")]
                    selected.update([(left+i)%7 for i in range((right-left)%7+1)])
                else:
                    selected.add(DAYS.index(part))
            if periods == "off":
                # Overlapping exception rules are intentionally not interpreted.
                return "unknown"
            for period in periods.replace(" ", "").split(","):
                left,right = period.split("-")
                def minute(s):
                    h,m = map(int,s.split(":"))
                    if h>24 or m>59 or (h==24 and m!=0): raise ValueError
                    return h*60+m
                a,b=minute(left),minute(right)
                for offset in [-1,0,1]:
                    day = (start+timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                    if day.weekday() in selected:
                        opened,closed=day+timedelta(minutes=a),day+timedelta(minutes=b)
                        if b<=a: closed+=timedelta(days=1)
                        windows.append((opened,closed))
        except (ValueError,TypeError):
            return "unknown"
    if not windows and not raw.strip(): return "unknown"
    return "open" if any(a<=start and end<=b for a,b in windows) else "closed"


def rank_options(people: list[Profile], places: list[Place], start: datetime, duration: int):
    if not people or any(not p.reviewed for p in people):
        raise ValueError("Every participant must review and save their profile first.")
    accepted, rejected = [], []
    for place in places:
        distances={p.id:miles(p.lat,p.lon,place.lat,place.lon) for p in people}
        reasons=[]
        if any(hours_status(f'Mo-Su {p.available_from}-{p.available_until}',start,duration,p.timezone)!='open' for p in people): reasons.append('Outside a participant’s availability')
        if any(d>50 for d in distances.values()): reasons.append("Outside 50 miles for at least one person")
        if place.cost is None: reasons.append("Per-person cost needs verification")
        elif any(place.cost>p.budget for p in people): reasons.append("Over someone's budget")
        if place.category=="Restaurant" and any(not set(p.diets).issubset(place.diets) for p in people): reasons.append("Dietary suitability needs verification")
        if any(p.accessible for p in people) and place.accessible is not True: reasons.append("Accessibility needs verification")
        status=hours_status(place.hours,start,duration,place.timezone or None)
        if status!="open": reasons.append("Closed during the visit" if status=="closed" else "Opening hours need verification")
        if reasons:
            rejected.append({"place":place.model_dump(),"reasons":reasons})
            continue
        scores={}
        for p in people:
            fit=len(set(p.interests)&set(place.interests))/max(1,len(p.interests))
            scores[p.id]=round(100*(.75*fit+.25*(1-distances[p.id]/50)),1)
        least=min(scores.values()); avg=sum(scores.values())/len(scores)
        accepted.append(Proposal(place=place,distances=distances,scores=scores,minimum_score=least,
            average_score=round(avg,1),maximum_distance=max(distances.values()),hours_status=status,
            explanation=f"Everyone is within 50 miles and budget. Lowest individual fit: {least:.0f}/100; group average: {avg:.0f}/100. Nobody gets left behind."))
    accepted.sort(key=lambda p:(-p.minimum_score,-p.average_score,p.maximum_distance,p.place.id))
    return accepted[:3], rejected
