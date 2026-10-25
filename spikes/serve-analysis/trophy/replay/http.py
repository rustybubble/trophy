"""Byte-range support for local replay files, including large source videos."""
from pathlib import Path
import re


def with_static_ranges(base):
    class Handler(base):
        def static_range(self, head=False):
            requested = self.headers.get('Range')
            if not requested:
                return False
            path = Path(self.translate_path(self.path)).resolve()
            root = Path(self.directory).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                return False
            size = path.stat().st_size
            interval = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not interval or not any(interval.groups()) or not size:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return True
            a, b = interval.groups()
            start = int(a) if a else max(0, size-int(b))
            end = min(size-1, int(b)) if a and b else size-1
            if start >= size or end < start or not a and int(b) == 0:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return True
            self.send_response(206)
            self.send_header('Content-Type', self.guess_type(str(path)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(end-start+1))
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if not head:
                try:
                    with path.open('rb') as source:
                        source.seek(start)
                        remaining = end-start+1
                        while remaining:
                            chunk = source.read(min(256*1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            return True

        def do_GET(self):
            if not self.static_range():
                super().do_GET()

        def do_HEAD(self):
            if not self.static_range(head=True):
                super().do_HEAD()
    return Handler
