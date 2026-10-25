"""Serve a built replay and all assets locally; no hosted services."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trophy.replay.http import with_static_ranges

p=argparse.ArgumentParser()
p.add_argument('--directory',default='artifacts/replay/demo')
p.add_argument('--port',type=int,default=8502)
p.add_argument('--bind',default='127.0.0.1')
p.add_argument('--toss-calibration',help='Optional calibration for the embedded serve review')
a=p.parse_args()
root=Path(a.directory).resolve()
if not (root/'scene.json').exists():p.error('Build the replay first; scene.json is missing')
handler=partial(with_static_ranges(SimpleHTTPRequestHandler),directory=str(root))
if (root/'review/serves.json').is_file():
    from serve_serve_review import handler_for
    handler=with_static_ranges(handler_for(root/'review',a.toss_calibration,static_directory=root,route_prefix='/review'))
print(f'Trophy 3D replay: http://{a.bind}:{a.port}/',flush=True)
ThreadingHTTPServer((a.bind,a.port),handler).serve_forever()
