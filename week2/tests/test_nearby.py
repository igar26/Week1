from unittest.mock import patch
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from referee.nearby import find_places
from referee.models import Place
from referee.store import Store
from referee.simple import SimplePlans
from referee.providers import ProviderError


def place(id,name,lat=32.78,lon=-96.8):
    return Place(id=id,name=name,lat=lat,lon=lon,category='Restaurant',source='OpenStreetMap',source_url='https://www.openstreetmap.org/node/1')


def test_lookup_sorts_and_filters_places_and_validates_zip():
    with patch('referee.nearby.fetch',return_value={'places':[{'latitude':'32.78','longitude':'-96.8','place name':'Dallas','state abbreviation':'TX'}]}),patch('referee.nearby.geoapify',return_value=[place('far','Too far',34,-96),place('near','Near')]) as query:
        result=find_places('75201')
        assert [r['place']['name'] for r in result['places']]==['Near']
        query.assert_called_once_with(32.78,-96.8,radius=16093)
    with pytest.raises(ValueError):find_places('not-a-zip')


def test_creation_collects_choices_before_any_nearby_search(tmp_path):
    store=Store(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.accounts.identity',return_value={'id':'verified-test-subject','name':'Alex'}),patch('referee.ui.store',return_value=store),patch('referee.simple.nearby_places') as search:
        app=AppTest.from_file(str(appfile)).run()
        next(b for b in app.button if b.label=='Plan something good').click().run()
        assert not any(b.label in {'Find nearby places','Find meetup venues'} for b in app.button)
        assert not any(x.label=='What nearby places would you like to see?' for x in app.selectbox)
        next(x for x in app.text_input if x.label=='Meetup ZIP code').set_value('75201')
        next(x for x in app.text_input if x.label=='Group name').set_value('Friends')
        next(x for x in app.text_input if x.label=='Your name').set_value('Alex')
        next(x for x in app.text_area if x.label=='Places or activities to choose from — one per line').set_value('Coffee and a walk\nPicnic')
        next(b for b in app.button if b.label=='Create group').click().run()
        assert not app.exception and not app.error
        assert SimplePlans(store).plan(app.session_state['member_key'])['choices']==['Coffee and a walk','Picnic']
        search.assert_not_called()
        assert not any(b.label=='Find meetup venues' for b in app.button)


def test_zip_404_has_a_zip_specific_error():
    with patch('referee.nearby.fetch',side_effect=ProviderError('HTTP 404',status=404)):
        with pytest.raises(ProviderError,match='ZIP code was not found'):find_places('00000')


def test_overpass_uses_alternate_and_does_not_cache_runtime_failure():
    from referee import providers
    providers._overpass_cooldowns.clear()
    bad={'elements':[],'remark':'runtime error: Query timed out'}
    good={'elements':[{'type':'node','id':1,'lat':32.78,'lon':-96.8,'tags':{'name':'Coffee','amenity':'cafe'}}]}
    with patch('referee.providers.fetch',side_effect=[bad,good]) as fetch:
        result=providers.overpass(32.78,-96.8,radius=16093)
        assert result[0].name=='Coffee'
        assert fetch.call_count==2
        assert fetch.call_args_list[0].args[0]=='GET'
        assert fetch.call_args_list[0].args[1]!=fetch.call_args_list[1].args[1]
    providers._overpass_cooldowns.clear()


def test_server_failure_is_not_misreported_as_no_places_and_cools_down():
    from referee import providers
    providers._overpass_cooldowns.clear()
    with patch('referee.providers.fetch',side_effect=ProviderError('HTTP 406',status=406)) as fetch:
        with pytest.raises(ProviderError,match='does not mean there are no nearby places'):providers.overpass(32.78,-96.8)
        attempts=fetch.call_count
        with pytest.raises(ProviderError,match='temporarily paused'):providers.overpass(32.78,-96.8)
        assert fetch.call_count==attempts
    providers._overpass_cooldowns.clear()


def test_valid_empty_place_result_does_not_trigger_failover():
    from referee import providers
    providers._overpass_cooldowns.clear()
    with patch('referee.providers.fetch',return_value={'elements':[]}) as fetch:
        assert providers.overpass(32.78,-96.8)==[]
        assert fetch.call_count==1


def test_http_error_preserves_status_for_zip_diagnosis():
    from unittest.mock import MagicMock
    from referee.providers import fetch
    response=MagicMock(ok=False,status_code=404)
    with patch('referee.providers.requests.request',return_value=response):
        with pytest.raises(ProviderError) as error:fetch('GET','https://api.zippopotam.us/us/00000')
    assert error.value.status==404
    assert 'HTTP 404' in str(error.value)


def test_invalid_coordinates_are_rejected_before_place_request():
    with patch('referee.nearby.fetch',return_value={'places':[{'latitude':'nan','longitude':'-96.8'}]}),patch('referee.nearby.geoapify') as request:
        with pytest.raises(ProviderError,match='invalid coordinates'):find_places('75201')
        request.assert_not_called()


def test_category_cache_wrapper_passes_only_selected_category():
    from referee.simple import nearby_places
    nearby_places.clear()
    with patch('referee.nearby.find_places',return_value={'zip':'75078','area':'Prosper, TX','places':[]}) as find:
        result=nearby_places('75078','Coffee shops')
        find.assert_called_once_with('75078',categories=['catering.cafe'])
        assert result['category']=='Coffee shops'
    nearby_places.clear()


def test_selected_tiles_survive_category_change_and_can_be_cleared(tmp_path):
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    coffee={'zip':'75078','area':'Prosper, TX','places':[{'place':place('cafe','Cafe choice').model_dump(),'miles':1.0}]}
    park={'zip':'75078','area':'Prosper, TX','places':[{'place':place('park','Park choice').model_dump(),'miles':2.0}]}
    def result(zipcode,category):return coffee if category=='Coffee shops' else park
    with patch('referee.ui.store',return_value=Store(tmp_path)),patch('referee.simple.nearby_places',side_effect=result) as search:
        app=AppTest.from_string("from referee.simple import nearby_picker\nnearby_picker('75078')").run()
        next(x for x in app.selectbox if x.label=='What nearby places would you like to see?').select('Coffee shops')
        next(b for b in app.button if b.label=='Find nearby places').click().run()
        next(x for x in app.checkbox if x.label=='Add to outing choices').check().run()
        assert 'cafe' in app.session_state['nearby_basket']['places']
        next(x for x in app.selectbox if x.label=='What nearby places would you like to see?').select('Parks and gardens').run()
        assert search.call_count==1
        assert not any(x.value=='Cafe choice' for x in app.text)
        app.session_state['nearby_last_request']=0
        next(b for b in app.button if b.label=='Find nearby places').click().run()
        next(x for x in app.checkbox if x.label=='Add to outing choices').check().run()
        assert set(app.session_state['nearby_basket']['places'])=={'cafe','park'}
        next(b for b in app.button if b.label=='Clear selected places').click().run()
        assert app.session_state['nearby_basket']['places']=={}
        assert not next(x for x in app.checkbox if x.label=='Add to outing choices').value
