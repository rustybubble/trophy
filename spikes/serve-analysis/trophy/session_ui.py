"""Two-angle upload UI; existing single-camera and serve workflows stay usable."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

import cv2
import numpy as np
import streamlit as st

from trophy.session import ROOT, analyze_two_camera, video_info
from trophy.corner_picker import pick_corners
from trophy.table_detection import detect_table


@st.cache_data(show_spinner=False)
def automatic_table(_frame, source_identity, start, version='demo-table-v2'):
    return detect_table(_frame)


def uploaded_source(upload):
    data = upload.getbuffer()
    digest = hashlib.sha256(data).hexdigest()
    path = ROOT / 'artifacts/ui/uploads' / (digest + Path(upload.name).suffix.lower())
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path


def pixel_values(value, count, label):
    if not value.strip():
        return [None] * count
    try:
        result = [float(part.strip()) for part in value.split(',')]
        if len(result) != count or not np.isfinite(result).all():
            raise ValueError
        return result
    except ValueError:
        raise ValueError(f'{label}: enter {count} comma-separated pixel coordinates') from None


def camera_setup(source, index, start):
    info = video_info(source)
    cap = cv2.VideoCapture(str(source))
    try:
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        raise ValueError(f'Camera {index+1}: selected start is outside this recording')
    w, h = info['width'], info['height']
    identity = f'{index}-{hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]}-{source.stat().st_mtime_ns}'
    st.subheader(f'Camera {index+1}')
    st.caption(f'{w} × {h} · {info["fps"]:.2f} FPS · {info["duration"]:.1f} seconds')
    detected = automatic_table(frame, identity, start)
    if detected:
        st.caption('Table segmented automatically · drag corners only if the outline needs adjusting.')
    else:
        st.caption('No stable automatic outline found. Click the four table corners in A–B–C–D order.')
    points = pick_corners(frame, key=f'auto-table-v1-{identity}-{start:.3f}',
                         initial_points=detected['corners'] if detected else None)
    st.write('Player regions · x0, y0 = top-left; x1, y1 = bottom-right')
    default_regions = detected['player_rois_px'] if detected else [[0, 0, w//2, h], [w//2, 0, w, h]]
    boxes = [pixel_values(st.text_input(f'Player {pid+1} · x0, y0, x1, y1',
             value=', '.join(map(str, box)), key=f'auto-region-{pid}-{identity}-{start:.3f}'), 4, f'Player {pid+1}')
             for pid, box in enumerate(default_regions)]
    with st.expander('Advanced camera calibration'):
        focal = st.number_input('Focal length in pixels (0 estimates from corners)', min_value=0.,
                                value=float(detected['focal_px']) if detected else 0., key=f'auto-focal-{identity}-{start:.3f}')
    overlay = frame.copy()
    if all(v is not None for row in points for v in row):
        cv2.polylines(overlay, [np.asarray(points, np.int32)], True, (0, 255, 255), 3)
        for label, p in zip('ABCD', points):
            cv2.putText(overlay, label, tuple(map(int, p)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
    for pid, box in enumerate(boxes):
        if all(v is not None for v in box):
            x0, y0, x1, y1 = map(int, box)
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (100, 220, 120) if pid == 0 else (220, 150, 100), 3)
            cv2.putText(overlay, f'Player {pid+1}', (x0+8, y0+30), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
    with st.expander('Check corner labels and player regions', expanded=False):
        st.image(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB), width='stretch')
    return dict(video=str(source), table_corners_px=points, player_rois_px=boxes, focal_px=focal,
                calibration_mode='automatic_demo' if detected else 'manual', table_segmentation=detected)


def open_replay(directory):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with (directory / 'server.log').open('a') as log:
        process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/serve_replay.py'),
            '--directory', str(directory / 'replay'), '--port', str(port)],
            cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError(f'Replay server failed; see {directory / "server.log"}')
        with socket.socket() as client:
            if client.connect_ex(('127.0.0.1', port)) == 0:
                return f'http://127.0.0.1:{port}/'
        time.sleep(.05)
    process.terminate()
    raise RuntimeError('Replay server did not start')


def completed_session(views, start, duration):
    """Restore finished results for these inputs, including a recovered run."""
    reports = sorted((ROOT / 'artifacts/sessions').glob('*/session-report.json'),
                     key=lambda path: path.stat().st_mtime, reverse=True)
    for path in reports:
        try:
            report = json.loads(path.read_text())
            if report.get('status') != 'complete':
                continue
            cfg = json.loads(path.with_name('session-config.json').read_text())
            if (cfg.get('start_seconds', 0) == start and cfg.get('duration_seconds', 6) == duration and
                    [Path(v['video']).resolve() for v in cfg['views']] == [Path(v['video']).resolve() for v in views] and
                    (path.parent / 'replay/scene.json').is_file()):
                return report
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def render():
    st.title('Trophy · Two-camera analysis')
    st.write('Upload two angles of the same rally to synchronize cameras, detect the ball and serves, and reconstruct both players with 4D Humans in one 3D replay.')
    st.caption('Use fixed cameras with overlapping footage. Start with a short segment: body reconstruction is computationally intensive. All analysis runs locally.')
    left, right = st.columns(2)
    uploads = [left.file_uploader('Camera 1 recording', type=['mp4', 'mov', 'm4v', 'avi', 'mkv'], key='combined-upload1'),
               right.file_uploader('Camera 2 recording', type=['mp4', 'mov', 'm4v', 'avi', 'mkv'], key='combined-upload2')]
    with st.expander('Use existing local files instead'):
        paths = [st.text_input(f'Camera {i+1} local path', key=f'combined-path{i}') for i in range(2)]
    a, b, c = st.columns(3)
    start = a.number_input('Start in camera 1 (seconds)', min_value=0., value=0., step=1., key='combined-start')
    duration = b.number_input('Analyze duration (seconds)', min_value=1.5, max_value=120., value=6., step=.5, key='combined-duration')
    device = c.selectbox('Inference device', ['auto', 'mps', 'cpu'], key='combined-device')
    mode = st.radio('Camera synchronization', ['Match audio, then refine visually', 'Enter coarse offset, then refine visually'], key='combined-sync')
    offset = st.number_input('Camera 2 minus camera 1 offset (seconds)', value=0., step=.01, disabled=mode.startswith('Match'), key='combined-offset',
        help='For the same instant: camera 1 at 8.0 s and camera 2 at 8.4 s means +0.4. Use this mode for silent recordings.')
    with st.expander('Ball detection settings'):
        threshold = st.slider('Ball heatmap threshold', .05, .99, .7, .01, key='combined-threshold')
        gray = st.checkbox('Orange-ball color neutralization (experimental)', key='combined-gray')
    sources = [uploaded_source(u) if u is not None else Path(p).expanduser().resolve() if p else None for u, p in zip(uploads, paths)]
    views = None
    if all(s is not None for s in sources):
        st.write('The demo automatically segments the table in both views. Check the highlighted surface; drag a corner if needed.')
        st.caption('A and D mark Player 1’s end; B and C mark Player 2’s end. Keep the player identities consistent between cameras. Automatic table geometry is an estimate.')
        try:
            if sources[0] == sources[1]:
                raise ValueError('Choose two different camera recordings')
            views = []
            for i, column in enumerate(st.columns(2)):
                with column:
                    views.append(camera_setup(sources[i], i, max(0, start + (offset if i and not mode.startswith('Match') else 0))))
        except Exception as exc:
            st.error(str(exc))
            views = None
    else:
        st.info('Add both camera recordings to preview frames and set table corners and player regions.')
    if st.button('Analyze both cameras', type='primary', disabled=views is None):
        output = ROOT / 'artifacts/sessions' / uuid.uuid4().hex[:16]
        config = dict(views=views, start_seconds=start, duration_seconds=duration, device=device,
                      sync_mode='audio' if mode.startswith('Match') else 'manual', offset_seconds=offset,
                      threshold=threshold, photometric='max-channel-gray' if gray else 'rgb')
        with st.status('Analyzing both cameras…', expanded=True) as task:
            log = st.empty()
            def update(stage, detail):
                task.update(label=stage)
                log.code(detail or stage)
            try:
                report = analyze_two_camera(config, output, update)
                st.session_state['combined-result'] = report
                st.session_state.pop('combined-url', None)
                task.update(label='Combined analysis complete', state='complete')
            except Exception as exc:
                task.update(label='Analysis needs attention', state='error')
                st.error(str(exc))
                st.caption(f'Session logs and any completed stages: {output}')
    result = st.session_state.get('combined-result')
    if result is None and views is not None:
        result = completed_session(views, start, duration)
        if result is not None:
            st.session_state['combined-result'] = result
    if result:
        output = Path(result['output'])
        st.subheader('Combined analysis result')
        a, b, c = st.columns(3)
        a.metric('3D body frames', result['frames'])
        b.metric('Serve candidates', result['serve_candidates'])
        c.metric('Camera 2 minus camera 1', f'{result["synchronization"]["original_offset_seconds"]:+.4f} s')
        if st.button('Open combined 3D replay', key='combined-open'):
            try:
                st.session_state['combined-url'] = open_replay(output)
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get('combined-url'):
            url = st.session_state['combined-url']
            st.link_button('3D replay + synchronized sources + serve timeline ↗', url)
            st.link_button('Review and correct serve candidates ↗', url + 'review/')
        for relative, label in [('session-report.json', 'Download combined report'),
                                ('session-config.json', 'Download session configuration'),
                                ('replay/ball-3d.csv', 'Download 3D ball positions'),
                                ('serves/serves.json', 'Download serve candidates')]:
            path = output / relative
            st.download_button(label, path.read_bytes(), file_name=path.name, key=f'combined-download-{relative}')
        st.caption(f'Results saved to {output}. Missing ball points stay missing; body shape, hidden joints and table calibration remain estimates.')
