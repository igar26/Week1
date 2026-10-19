"""Offline demo of the current ZIP/tiles/RSVP flow, with fictional people and choices."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .simple import SimplePlans


def create_outing_demo(store):
    owner,invite,keys=store.create_demo()
    plans=SimplePlans(store)
    today=datetime.now(ZoneInfo('America/Chicago')).date()
    day=today+timedelta(days=(5-today.weekday())%7 or 7)
    choices=['Coffee and catch-up (demo)','Picnic in the park (demo)','Pizza night (demo)']
    plans.save_plan(owner,dict(zip='75201',date=day.isoformat(),time='18:00',duration=120,budget=30,
                              interests=['Food','Coffee','Outdoors'],choices=choices))
    scenarios=[('Can join',[choices[0],choices[1]],['Coffee','Outdoors'],'A quiet spot for conversation.'),
               ('Can join',[choices[0],choices[2]],['Coffee','Food'],'Keep it affordable and relaxed.'),
               ('Maybe',[choices[0],choices[1]],['Outdoors','Coffee'],'I might arrive late; a short walk would be nice.'),
               ('Cannot join',[],['Art'],'Busy this Saturday. Catch you next time!')]
    for key,(attendance,picks,interests,wishes),budget in zip(keys.values(),scenarios,[30,25,20,15]):
        plans.respond(key,attendance,picks,interests,wishes,analysis_consent=False,budget=budget)
    return owner,invite,keys
