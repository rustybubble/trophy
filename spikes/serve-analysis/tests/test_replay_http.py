"""Source clips need range responses for browser seeking, not only review media."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from trophy.replay.http import with_static_ranges


def test_replay_static_ranges_allow_seeking_and_reject_invalid_intervals(tmp_path):
    (tmp_path/'source1.mp4').write_bytes(b'0123456789')
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(with_static_ranges(SimpleHTTPRequestHandler), directory=str(tmp_path)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}/source1.mp4'
    try:
        for interval, expected in [('bytes=2-5', b'2345'), ('bytes=7-', b'789'), ('bytes=-3', b'789')]:
            with urlopen(Request(url, headers={'Range': interval})) as response:
                assert response.status == 206
                assert response.read() == expected
                assert response.headers['Accept-Ranges'] == 'bytes'
        with urlopen(Request(url, method='HEAD', headers={'Range': 'bytes=2-5'})) as response:
            assert response.status == 206
            assert response.headers['Content-Length'] == '4'
            assert response.read() == b''
        for interval in ['bytes=50-', 'bytes=5-2', 'bytes=-0', 'bytes=1-2,4-6']:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url, headers={'Range': interval}))
            assert error.value.code == 416
        with urlopen(url) as response:
            assert response.status == 200 and response.read() == b'0123456789'
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
