from trophy.recordings import live_snapshot

LIVE = (
    '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2.0,\nseg_000000.m4s\n#EXTINF:2.0,\nseg_000001.m4s\n'
)


def test_live_snapshot_closes_a_live_playlist_once():
    snap = live_snapshot(LIVE)
    assert snap.endswith("seg_000001.m4s\n#EXT-X-ENDLIST\n")
    assert live_snapshot(snap) == snap  # already final: unchanged
