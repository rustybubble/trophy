"""Local review page with byte-range access to only its configured source videos."""
import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trophy.serves.legality import analyze_toss, rulebook


def handler_for(directory, calibration=None, *, static_directory=None, route_prefix=''):
    root=Path(directory).resolve()
    static_root=Path(static_directory).resolve() if static_directory else root
    if route_prefix and (not route_prefix.startswith('/') or route_prefix.endswith('/')):
        raise ValueError('Expected a slash-prefixed route without a trailing slash')
    session=json.loads((root/'serves.json').read_text())
    if calibration is None and (root/'toss-calibration.json').is_file():calibration=root/'toss-calibration.json'
    calibration=json.loads(Path(calibration).read_text()) if isinstance(calibration,(str,Path)) else calibration
    media=[Path(v.get('review_video',v['video'])).resolve() for v in session['views']]
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(static_root),**kwargs)

        def send_json(self,value,status=200):
            body=json.dumps(value,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)

        def serve_media(self,head=False):
            match=re.fullmatch(re.escape(route_prefix)+r'/media/(\d+)',urlsplit(self.path).path)
            if not match:return False
            index=int(match[1])
            if index>=len(media) or not media[index].is_file():self.send_error(404);return True
            path=media[index];size=path.stat().st_size
            start,end=0,size-1;requested=self.headers.get('Range')
            if requested:
                interval=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                if not interval or not any(interval.groups()):self.send_error(416);return True
                a,b=interval.groups()
                if a:start=int(a);end=min(int(b),end) if b else end
                else:start=max(0,size-int(b))
                if start>=size or end<start:
                    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return True
            self.send_response(206 if requested else 200)
            self.send_header('Content-Type',self.guess_type(str(path)))
            self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
            if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            if not head:
                try:
                    with path.open('rb') as source:
                        source.seek(start);remaining=end-start+1
                        while remaining:
                            chunk=source.read(min(256*1024,remaining))
                            if not chunk:break
                            self.wfile.write(chunk);remaining-=len(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
            return True

        def do_GET(self):
            if urlsplit(self.path).path==route_prefix+'/api/toss-rules':
                self.send_json(dict(rulebook=rulebook(),calibration={
                    'calibration_id':calibration.get('calibration_id'),
                    'fixture_only':calibration.get('fixture_only',False),
                    'sha256':hashlib.sha256(json.dumps(calibration,sort_keys=True).encode()).hexdigest(),
                    'validation':calibration.get('validation'),
                    'notes':calibration.get('notes',[])} if calibration else None));return
            if not self.serve_media():super().do_GET()

        def do_HEAD(self):
            if not self.serve_media(head=True):super().do_HEAD()

        def do_POST(self):
            if urlsplit(self.path).path!=route_prefix+'/api/toss-measure':self.send_error(404);return
            # This localhost API computes evidence only. No arbitrary paths,
            # calibration overrides, CORS, uploads or disk writes are accepted.
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':
                self.send_json({'error':'Cross-origin requests are not accepted'},403);return
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=65536:raise ValueError('Expected a JSON request of at most 64 KiB')
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('Expected application/json')
                request=json.loads(self.rfile.read(length))
                if not isinstance(request,dict):raise ValueError('Expected a JSON object')
                self.send_json(analyze_toss(session,request,calibration))
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                self.send_json({'error':str(error)},400)
    return Handler


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--port',type=int,default=8504)
    p.add_argument('--calibration',help='Optional source-linked metric toss calibration JSON')
    a=p.parse_args();print(f'Serve review: http://127.0.0.1:{a.port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),handler_for(a.directory,a.calibration)).serve_forever()
