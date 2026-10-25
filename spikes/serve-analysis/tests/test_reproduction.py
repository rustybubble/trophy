"""Private assets must restore into ignored storage, never arbitrary source paths."""
import io
import json
from pathlib import Path
import tarfile

import pytest

from repro import bundle


@pytest.mark.parametrize('path', ['../secrets', '/tmp/video.mp4', 'README.md',
                                   'spikes/serve-analysis/repro/bundle.py', 'data/local/../../README.md'])
def test_asset_paths_cannot_overwrite_code_or_escape_checkout(tmp_path, path):
    with pytest.raises(ValueError):
        bundle.destination(path, tmp_path)


def test_asset_paths_cannot_follow_external_symlinks(tmp_path):
    outside = tmp_path/'elsewhere'; outside.mkdir()
    repo = tmp_path/'repo'; (repo/'data/local').mkdir(parents=True)
    (repo/'data/local/analysis-inputs').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        bundle.destination('data/local/analysis-inputs/video.mov', repo)


def test_verified_bundle_restores_exact_bytes_and_refuses_corruption(tmp_path, monkeypatch):
    import hashlib
    data = b'fixture asset bytes'
    name = 'data/local/analysis-inputs/fixture.mov'
    manifest = dict(files=[dict(path=name, group='recordings', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())])
    manifest_path = tmp_path/'manifest.json'; manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(bundle, 'MANIFEST', manifest_path)
    def archive(path, contents):
        with tarfile.open(path, 'w') as tar:
            payload = json.dumps(manifest).encode()
            info = tarfile.TarInfo('ASSET_MANIFEST.json'); info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
            info = tarfile.TarInfo(name); info.size = len(contents)
            tar.addfile(info, io.BytesIO(contents))
    valid = tmp_path/'valid.tar'; archive(valid, data)
    repo = tmp_path/'repo'; repo.mkdir()
    bundle.import_bundle(valid, repo)
    assert (repo/name).read_bytes() == data
    bundle.import_bundle(valid, repo)  # Existing identical assets are reusable.
    corrupt = tmp_path/'corrupt.tar'; archive(corrupt, b'X'*len(data))
    empty = tmp_path/'other'; empty.mkdir()
    with pytest.raises(ValueError, match='checksum'):
        bundle.import_bundle(corrupt, empty)
    assert not (empty/name).exists()
    (repo/name).write_bytes(b'preserve user changes')
    with pytest.raises(ValueError, match='Existing asset differs'):
        bundle.import_bundle(valid, repo)
