from unittest.mock import patch
from scripts import build_demo


def test_demo_runs_real_synthetic_flow_without_network():
    with patch('requests.request', side_effect=AssertionError('Demo must stay offline')):
        snapshot=build_demo.synthetic_snapshot()
    assert snapshot['people']==snapshot['advocates']==4
    assert snapshot['status']=='finalized'
    assert not snapshot['booked']
    assert snapshot['eligible']==3
    assert snapshot['memories']==1
    assert 'address' in snapshot['venue_fields']


def test_watched_sources_exclude_private_data_and_generated_outputs(tmp_path):
    (tmp_path/'referee').mkdir()
    (tmp_path/'referee/logic.py').write_text('answer = 42')
    (tmp_path/'data').mkdir()
    (tmp_path/'data/private.sqlite').write_bytes(b'personal')
    (tmp_path/'.env').write_text('SECRET=hidden')
    (tmp_path/'demo').mkdir()
    (tmp_path/'demo/walkthrough.mp4').write_bytes(b'video')
    with patch.object(build_demo,'ROOT',tmp_path):
        before=build_demo.fingerprint()
        (tmp_path/'.env').write_text('SECRET=changed')
        (tmp_path/'data/private.sqlite').write_bytes(b'changed')
        (tmp_path/'demo/walkthrough.mp4').write_bytes(b'changed')
        assert build_demo.fingerprint()==before
        (tmp_path/'referee/logic.py').write_text('answer = 43')
        assert build_demo.fingerprint()!=before


def test_walkthrough_has_ten_captioned_chapters():
    # Encoding is checked by the build command; captions have one cue per chapter.
    scenes=build_demo.chapters(build_demo.synthetic_snapshot())
    assert len(scenes)==10
    assert build_demo.timestamp(80)=='00:01:20.000'
