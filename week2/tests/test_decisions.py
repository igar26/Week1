from datetime import datetime
import pytest
from referee.catalog import demo_profiles,demo_places
from referee.decision import miles,hours_status,rank_options,DALLAS_TZ

START=datetime(2026,10,18,17,tzinfo=DALLAS_TZ)


def test_distance_and_both_people_radius():
    assert miles(32,-96,32,-96)==0
    people=demo_profiles();places=demo_places()
    options,rejected=rank_options(people,places,START,120)
    assert len(options)==3
    assert all(max(p.distances.values())<=50 for p in options)
    assert any('Outside 50' in str(r['reasons']) for r in rejected)
    people[-1].lat=35
    options,_=rank_options(people,places,START,120)
    assert options==[]


@pytest.mark.parametrize('raw,hour,duration,expected',[
    ('24/7',17,120,'open'),('Mo-Su 09:00-23:00',22,120,'closed'),
    ('Mo-Su 09:00-23:00',21,120,'open'),('Su 20:00-02:00',23,120,'open'),
    ('Mo-Fr 09:00-23:00',17,60,'closed'),('',17,60,'unknown'),
    ('Mo-Su 09:00-23:00; PH off',17,60,'unknown'),
    ('Mo-Su 99:00-23:00',17,60,'unknown'),
    ('Su 09:00-12:00,17:00-22:00',17,120,'open'),
])
def test_hours_never_guess(raw,hour,duration,expected):
    assert hours_status(raw,START.replace(hour=hour),duration)==expected


def test_hard_constraints_are_not_preferences():
    people=demo_profiles();place=demo_places()[0]
    for update in [{'cost':None},{'cost':200},{'diets':[]},{'hours':''},{'hours':'closed'}]:
        options,rejected=rank_options(people,[place.model_copy(update=update)],START,120)
        assert not options and rejected
    people[-1].accessible=True
    assert not rank_options(people,[place.model_copy(update={'accessible':None})],START,120)[0]
    people[-1].available_until='18:00'
    assert not rank_options(people,[place],START,120)[0]


def test_least_satisfied_first_and_determinism():
    a,_=rank_options(demo_profiles(),demo_places(),START,120)
    b,_=rank_options(demo_profiles(),list(reversed(demo_places())),START,120)
    assert [p.place.id for p in a]==[p.place.id for p in b]
    assert a==sorted(a,key=lambda p:(-p.minimum_score,-p.average_score,p.maximum_distance,p.place.id))
    people=demo_profiles();people[0].reviewed=False
    with pytest.raises(ValueError):rank_options(people,demo_places(),START,120)
