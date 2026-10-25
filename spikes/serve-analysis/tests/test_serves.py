"""Serve observations must not turn timing errors or duplicates into new events."""
from functools import partial
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import torch

from trophy.serves.events import decode_events, merge_views, evaluate_events
from trophy.serves.inference import predict_frames
from trophy.serves.attribution import attribute_events


def observation(t,player='p0',frame=10,score=.8):
    return dict(time_seconds=t,player_id=player,sampled_frame=frame,score=score)


def test_camera_clock_mapping_and_stable_id():
    views=[dict(id='a',events=[observation(3.)]),
           dict(id='b',source_offset_seconds=.4,events=[observation(3.42,frame=40)])]
    result=merge_views(views,session_id='match')
    assert len(result)==1
    assert result[0]['time_seconds']==pytest.approx(3.01)
    assert result[0]['supporting_views']==['a','b']
    assert merge_views(views,session_id='match')[0]['serve_id']==result[0]['serve_id']
    assert result[0]['fault_decision'] is None
    assert result[0]['release_interval_seconds'] is None


def test_hidden_camera_does_not_erase_a_serve():
    result=merge_views([dict(id='visible',events=[observation(2.)]),dict(id='hidden',events=[])])
    assert len(result)==1 and result[0]['event_status']=='candidate'


def test_disagreeing_players_require_review():
    result=merge_views([dict(id='a',events=[observation(2.,'p0')]),dict(id='b',events=[observation(2.1,'p1')])])
    assert len(result)==1
    assert result[0]['player_id'] is None and result[0]['event_status']=='review_needed'


def test_unknown_actor_in_one_view_does_not_override_supported_identity():
    result=merge_views([dict(id='a',events=[observation(2.,None,score=.95)]),
                       dict(id='b',events=[observation(2.1,'p0',score=.8)])])
    assert result[0]['player_id']=='p0'


def test_uncertain_side_scores_can_still_identify_serving_action():
    scores=np.array([[.1,.43,.42,.03,.02]])
    assert decode_events([2.],scores,threshold=.8)==[]
    events=decode_events([2.],scores,threshold=.8,aggregate_serves=True)
    assert len(events)==1 and events[0]['score']==pytest.approx(.85)


def test_motion_attribution_can_override_network_side_and_abstain():
    images=np.zeros((20,64,96,3),np.uint8)
    for i in range(20):images[i,15+i:25+i,15:25]=255
    times=np.arange(20)/15
    event=observation(1.,'p1');event['sampled_frame']=15
    result=attribute_events(images,times,[event],{'left':'p0','right':'p1'})
    assert result[0]['player_id']=='p0' and result[0]['network_player_id']=='p1'
    event=observation(1.,'p0')
    result=attribute_events(np.zeros_like(images),times,[event],{'left':'p0','right':'p1'})
    assert result[0]['player_id'] is None


def test_nearby_same_camera_events_never_merge():
    result=merge_views([dict(id='a',events=[observation(2.,frame=20),observation(2.1,frame=21)])])
    assert len(result)==2
    with pytest.raises(ValueError,match='unique'):
        merge_views([dict(id='a',events=[]),dict(id='a',events=[])])


def test_offset_outside_shared_time_is_excluded():
    assert merge_views([dict(id='a',source_offset_seconds=1.,events=[observation(.5)])])==[]


def test_decoder_uses_source_timestamps_and_explicit_player_map():
    times=np.array([10.,10.067,10.134,10.2,12.,12.067])
    scores=np.tile([.95,.01,.01,.02,.01],(6,1))
    scores[1]=[.05,.9,.01,.02,.02];scores[2]=[.05,.85,.02,.05,.03]
    scores[4]=[.05,.02,.9,.02,.01]
    events=decode_events(times,scores,player_map={'left':'black','right':'blue'})
    assert [(e['time_seconds'],e['player_id']) for e in events]==[(10.067,'black'),(12.,'blue')]
    with pytest.raises(ValueError,match='increasing'):
        decode_events([0,0],np.ones((2,5)))


def test_normal_stroke_is_not_a_serve_and_no_toss_rule_is_a_gate():
    scores=np.array([[.01,.02,.01,.95,.01],[.01,.94,.02,.02,.01]])
    events=decode_events([1.,2.],scores)
    assert len(events)==1 and events[0]['time_seconds']==2.


def test_duplicate_predictions_count_as_errors():
    truth=[observation(4.)]
    metrics=evaluate_events([observation(4.),observation(4.05,score=.7)],truth)
    assert metrics['true_positives']==1 and metrics['false_positives']==1
    assert metrics['precision']==.5 and metrics['recall']==1.
    wrong=evaluate_events([observation(4.,'p1')],truth)
    assert wrong['false_positives']==1 and wrong['false_negatives']==1


class FixedModel(torch.nn.Module):
    def forward(self,x):
        logits=torch.zeros((*x.shape[:2],5),device=x.device)
        logits[...,0]=4
        return logits


@pytest.mark.parametrize('length',[1,7,17,48,49,73,101])
def test_overlapping_windows_cover_real_frames_without_exporting_padding(length):
    result=predict_frames(FixedModel(),np.zeros((length,16,20,3),np.uint8))
    assert result.shape==(length,5)
    assert np.isfinite(result).all()
    np.testing.assert_allclose(result.sum(1),1.,atol=1e-6)
    assert (result.argmax(1)==0).all()


def test_media_server_ranges_and_file_allowlist(tmp_path):
    module_path=Path(__file__).resolve().parents[1]/'scripts/serve_serve_review.py'
    spec=importlib.util.spec_from_file_location('serve_review_server_test',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    media=tmp_path/'input.mp4';media.write_bytes(b'0123456789')
    (tmp_path/'serves.json').write_text(json.dumps({'views':[{'video':str(media)}]}))
    server=ThreadingHTTPServer(('127.0.0.1',0),module.handler_for(tmp_path))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        request=urllib.request.Request(url+'/media/0',headers={'Range':'bytes=2-5'})
        with urllib.request.urlopen(request) as response:
            assert response.status==206 and response.read()==b'2345'
            assert response.headers['Content-Range']=='bytes 2-5/10'
        with urllib.request.urlopen(urllib.request.Request(url+'/media/0',headers={'Range':'bytes=-3'})) as response:
            assert response.read()==b'789'
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url+'/media/1')
        assert error.value.code==404
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(url+'/media/0',headers={'Range':'bytes=20-30'}))
        assert error.value.code==416
    finally:
        server.shutdown();server.server_close();thread.join()
