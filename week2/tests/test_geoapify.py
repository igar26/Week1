from unittest.mock import patch
import pytest
from referee.providers import geoapify,ProviderError


def test_geoapify_request_uses_server_header_and_parses_real_fields(monkeypatch):
    monkeypatch.setenv('GEOAPIFY_API_KEY','fake-test-key')
    payload={'features':[{'geometry':{'type':'Point','coordinates':[-96.7954,33.2362]},'properties':{
        'place_id':'venue-1','name':'Test Cafe','formatted':'123 Main St, Prosper, TX',
        'categories':['catering.cafe'],'datasource':{'raw':{'opening_hours':'Mo-Su 09:00-21:00','website':'https://example.org'}}}}]}
    with patch('referee.providers.fetch',return_value=payload) as fetch:
        result=geoapify(33.2362,-96.7954)
    method,url=fetch.call_args.args
    kwargs=fetch.call_args.kwargs
    assert method=='POST' and url=='https://api.geoapify.com/v2/places'
    assert kwargs['headers']['x-api-key']=='fake-test-key'
    assert kwargs['json']['filter']=={'type':'circle','lat':33.2362,'lon':-96.7954,'radius':16093.0}
    assert 'apiKey' not in url and 'fake-test-key' not in str(kwargs['json'])
    assert result[0].address=='123 Main St, Prosper, TX'
    assert result[0].hours=='Mo-Su 09:00-21:00'
    assert result[0].cost is None and not result[0].synthetic
    assert result[0].interests==['Food','Coffee']
    assert 'fake-test-key' not in result[0].model_dump_json()


def test_geoapify_missing_key_does_not_use_overpass(monkeypatch):
    monkeypatch.delenv('GEOAPIFY_API_KEY',raising=False)
    with patch('referee.providers.fetch') as fetch,patch('referee.providers.overpass') as old:
        with pytest.raises(ProviderError,match='not connected'):geoapify(33.23,-96.79)
        fetch.assert_not_called();old.assert_not_called()


@pytest.mark.parametrize('status,phrase',[(401,'rejected'),(403,'rejected'),(429,'allowance')])
def test_auth_and_quota_errors_are_actionable_without_key_exposure(monkeypatch,status,phrase):
    monkeypatch.setenv('GEOAPIFY_API_KEY','fake-private-key')
    with patch('referee.providers.fetch',side_effect=ProviderError('HTTP failure',status=status)):
        with pytest.raises(ProviderError,match=phrase) as error:geoapify(33.23,-96.79)
        assert 'fake-private-key' not in str(error.value)


def test_malformed_results_fail_and_unknown_hours_stay_unknown(monkeypatch):
    monkeypatch.setenv('GEOAPIFY_API_KEY','fake-test-key')
    with patch('referee.providers.fetch',return_value={'features':'bad'}):
        with pytest.raises(ProviderError,match='invalid'):geoapify(33.23,-96.79)
    payload={'features':[{'properties':{'place_id':'p','name':'Park','lat':33.23,'lon':-96.79,'categories':['leisure.park']}}]}
    with patch('referee.providers.fetch',return_value=payload):result=geoapify(33.23,-96.79)
    assert result[0].hours=='' and result[0].accessible is None
