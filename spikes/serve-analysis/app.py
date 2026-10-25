"""Local Streamlit interface, sharing the exact CLI inference pipeline."""
from datetime import datetime
from pathlib import Path
import json
import socket
import subprocess
import sys
import uuid

import streamlit as st

from trophy.model import ROOT
from trophy.pipeline import analyze

st.set_page_config(page_title='Trophy · Rally analysis', layout='wide')
from trophy.session_ui import render as render_combined_analysis

combined_tab, existing_tab = st.tabs(['Two-camera · Combined analysis', 'Single-camera tracking & standalone serve review'])
with combined_tab:
    render_combined_analysis()

with existing_tab:
    st.title('Trophy · Table-tennis ball tracking')
    st.caption('Recorded clips · pretrained BlurBall · local CPU or Apple GPU inference')
    if (ROOT / 'artifacts/replay/demo/scene.json').exists():
        st.link_button('Open the 3D replay demo ↗', 'http://127.0.0.1:8502/')
        st.caption('Rotatable figures and ball path from this clip. Single-camera depth and hidden joints are inferred.')

    upload = st.file_uploader('Upload a table-tennis clip', type=['mp4', 'mov', 'm4v', 'avi', 'mkv'])
    local_path = st.text_input('Or select a local video by path', str(ROOT / 'samples/official-22-003.mp4'))
    left, middle, right = st.columns(3)
    with left:
        device = st.selectbox('Device', ['auto', 'mps', 'cpu'])
    with middle:
        threshold = st.slider('Heatmap threshold', min_value=.05, max_value=.99, value=.7, step=.01)
    with right:
        max_frames = st.number_input('Maximum source frames', min_value=1, max_value=100000, value=600, step=30)
    duration = st.number_input('Maximum duration in seconds (0 uses frame limit)', min_value=0., value=20., step=1.)
    st.caption('Coverage is not accuracy. Scores are uncalibrated heatmap peaks. Videos shorter than three unique frames export missing detections.')

    if st.button('Analyze clip', type='primary'):
        output = ROOT / 'artifacts/ui' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        source = Path(local_path).expanduser()
        if upload is not None:
            upload_dir = ROOT / 'artifacts/ui/uploads'
            upload_dir.mkdir(parents=True, exist_ok=True)
            source = upload_dir / (uuid.uuid4().hex + Path(upload.name).suffix.lower())
            source.write_bytes(upload.getbuffer())
        bar = st.progress(0., text='Preparing')
        status = st.empty()
        def progress(stage, done, total):
            fraction = min(1., done / total) if total and total != float('inf') else 0.
            bar.progress(fraction, text=f'{stage}: {done}/{total}')
            status.text(f'{stage}: {done} frames' if stage in ('Analyzing', 'Rendering', 'Complete') else stage)
        try:
            report = analyze(source, output, device=device, threshold=threshold,
                             max_frames=int(max_frames), max_duration=duration or None, progress=progress)
            st.session_state['result'] = {'output': str(output), 'report': report}
            status.success(f'Completed {report["analyzed_frame_count"]} frames on {report["device"]}.')
        except Exception as exc:
            status.error(f'Analysis failed: {exc}')
            bar.empty()

    result = st.session_state.get('result')
    if result:
        output, report = Path(result['output']), result['report']
        a, b, c, d = st.columns(4)
        a.metric('Device', report['device'].upper())
        b.metric('Detection coverage', f'{report["detection_coverage"]:.1%}')
        c.metric('End-to-end processing', f'{report["end_to_end_processing_fps"]:.1f} FPS')
        latency = report['inference_latency_ms']['mean']
        d.metric('Model per 3-frame window', f'{latency:.1f} ms' if latency is not None else 'No complete window')
        original, annotated = st.columns(2)
        with original:
            st.write('Original analyzed frames')
            st.video(str(output / 'original.mp4'))
        with annotated:
            st.write('Annotated detections')
            st.video(str(output / 'annotated.mp4'))
        st.caption('Preview playback preserves source reported average FPS; processing FPS is measured separately. Audio is omitted. Missing detections have no marker.')
        for name, label, mime in [
            ('annotated.mp4', 'Download annotated MP4', 'video/mp4'),
            ('detections.csv', 'Download per-frame CSV', 'text/csv'),
            ('detections.json', 'Download per-frame JSON', 'application/json'),
            ('report.json', 'Download performance report', 'application/json')]:
            st.download_button(label, (output / name).read_bytes(), file_name=name, mime=mime)
        with st.expander('Performance report and limitations'):
            st.json(report)
        st.caption(f'Saved to {output}')

    with st.expander('Find and review serves · one or two cameras', expanded=False):
        st.caption('Recorded video analysis · trained temporal event model · serve candidates with source-video review')
        serve_config = st.text_input('Serve session configuration JSON', str(ROOT / 'configs/serve-user-two-camera.json'))
        serve_checkpoint = st.text_input('Trained serve checkpoint', str(ROOT / 'weights/serves/table-tennis-final.pt'))
        toss_calibration = st.text_input('Toss measurement calibration JSON (optional)', str(ROOT / 'configs/serve-user-two-camera-toss-calibration.json'))
        st.caption('The supplied phone calibration is approximate. Toss overlays can record evidence; supported fault checks require validated geometry and timing.')
        serve_limit = st.number_input('Serve analysis duration limit (seconds)', min_value=1., max_value=600., value=120.)
        if st.button('Find serves'):
            interpreter = ROOT / '.venv-serves/bin/python'
            if not interpreter.exists():
                st.error('Set up the serve environment with bash scripts/bootstrap_serves.sh first.')
            elif not Path(serve_checkpoint).is_file():
                st.error('A trained table-tennis checkpoint is required. See SERVES.md for training and setup.')
            else:
                serve_out = ROOT / 'artifacts/ui' / ('serves-' + uuid.uuid4().hex[:12])
                with st.status('Finding serve events…', expanded=True) as task:
                    log = st.empty()
                    process = subprocess.Popen([str(interpreter), str(ROOT / 'scripts/detect_serves.py'),
                        '--config', serve_config, '--checkpoint', serve_checkpoint, '--output', str(serve_out),
                        '--max-seconds', str(serve_limit), '--device', device],
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    lines = []
                    for line in process.stdout:
                        lines.append(line.rstrip())
                        log.code('\n'.join(lines[-8:]))
                    code = process.wait()
                    if code:
                        task.update(label='Serve analysis failed', state='error')
                    else:
                        st.session_state['serve_result'] = str(serve_out)
                        st.session_state.pop('serve_review_url', None)
                        task.update(label='Serve candidates ready', state='complete')
        serve_result = st.session_state.get('serve_result')
        if serve_result:
            serve_out = Path(serve_result)
            serve_report = json.loads((serve_out / 'serves.json').read_text())
            st.write(f"{len(serve_report['events'])} serve candidates · {serve_report['device'].upper()}")
            st.caption('Candidates do not establish toss height or legality. Confirm or correct them in source-video review.')
            if st.button('Open serve review'):
                # Bind an available localhost port for this result; no remote hosting.
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1', 0))
                    review_port = listener.getsockname()[1]
                log_path = serve_out / 'review-server.log'
                review_command = [sys.executable, str(ROOT / 'scripts/serve_serve_review.py'),
                                  '--directory', str(serve_out), '--port', str(review_port)]
                if toss_calibration and Path(toss_calibration).is_file():
                    review_command.extend(['--calibration', toss_calibration])
                with log_path.open('a') as review_log:
                    subprocess.Popen(review_command,
                                     cwd=ROOT, stdout=review_log, stderr=review_log, start_new_session=True)
                st.session_state['serve_review_url'] = f'http://127.0.0.1:{review_port}/'
            if st.session_state.get('serve_review_url'):
                st.link_button('Open source-video serve review ↗', st.session_state['serve_review_url'])
            st.download_button('Download serve events JSON', (serve_out / 'serves.json').read_bytes(),
                               file_name='serves.json', mime='application/json')
