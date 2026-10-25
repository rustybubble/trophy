"""Create/import a private, checksum-verified asset kit. No inference imports."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
REL = ROOT.relative_to(REPO)
MANIFEST = Path(__file__).with_name('asset-manifest.json')


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def destination(path, repo=REPO):
    relative = Path(path)
    allowed = [REL/'weights', REL/'samples', REL/'artifacts', Path('data/local/analysis-inputs')]
    if relative.is_absolute() or '..' in relative.parts or not any(relative.is_relative_to(p) for p in allowed):
        raise ValueError(f'Asset destination is outside ignored asset storage: {path}')
    result = (repo/relative).resolve()
    if not result.is_relative_to(repo.resolve()):
        raise ValueError(f'Asset destination escapes checkout through a symlink: {path}')
    return result


def inventory(workspace, recordings):
    workspace = Path(workspace).resolve()
    files = {}
    def add(source, target, group):
        if source.is_file() and not source.is_symlink():
            files[str(target)] = (source, group)
    for name in ['blurball_best', 'pose_landmarker_full.task']:
        add(workspace/'weights'/name, REL/'weights'/name, 'runtime')
    for folder in ['hmr2-assets', 'serves']:
        for source in (workspace/'weights'/folder).rglob('*'):
            if source.suffix != '.log':
                add(source, REL/source.relative_to(workspace), 'runtime')
    for source in (workspace/'samples').rglob('*'):
        add(source, REL/source.relative_to(workspace), 'samples')
    for name, source in recordings.items():
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f'Required original recording missing: {source}')
        add(source, Path('data/local/analysis-inputs')/name, 'recordings')
    omitted = {'ui', 'serve-sample-cache', 'hmr2-matplotlib', 'combined-legacy-fit-check', 'reproductions'}
    for source in (workspace/'artifacts').rglob('*'):
        relative = source.relative_to(workspace/'artifacts')
        if (relative.parts[0] not in omitted and source.suffix not in {'.log', '.part'} and
                '__pycache__' not in relative.parts and not source.name.startswith('.')):
            add(source, REL/source.relative_to(workspace), 'reference')
    return files


def export_bundle(workspace, recordings, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new bundle file; existing bundles are not overwritten')
    entries = inventory(workspace, recordings)
    manifest = dict(schema_version=1, private=True,
        note='Private participant footage, separately acquired models and reference outputs. Do not commit or publish the bundle.',
        files=[])
    for index, (target, (source, group)) in enumerate(sorted(entries.items())):
        destination(target)
        manifest['files'].append(dict(path=target, group=group, bytes=source.stat().st_size, sha256=digest(source)))
        if index % 250 == 0:
            print(f'Hashed {index+1}/{len(entries)} assets', flush=True)
    data = (json.dumps(manifest, indent=2)+'\n').encode()
    MANIFEST.write_bytes(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.partial')
    with tarfile.open(temporary, 'w', format=tarfile.PAX_FORMAT) as archive:
        info = tarfile.TarInfo('ASSET_MANIFEST.json'); info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        for index, item in enumerate(manifest['files']):
            source = entries[item['path']][0]
            archive.add(source, arcname=item['path'], recursive=False)
            if index % 250 == 0:
                print(f'Archived {index+1}/{len(entries)} assets', flush=True)
    temporary.replace(output)
    checksum = digest(output)
    output.with_suffix(output.suffix+'.sha256').write_text(f'{checksum}  {output.name}\n')
    print(json.dumps(dict(bundle=str(output), bytes=output.stat().st_size,
                         files=len(entries), sha256=checksum), indent=2), flush=True)
    return manifest


def import_bundle(bundle, repo=REPO, groups=None):
    expected = json.loads(MANIFEST.read_text())
    by_name = {item['path']: item for item in expected['files']}
    installed = 0
    with tarfile.open(bundle, 'r:*') as archive:
        first = archive.next()
        if first is None or first.name != 'ASSET_MANIFEST.json' or not first.isfile():
            raise ValueError('Missing bundle manifest')
        bundled = json.load(archive.extractfile(first))
        if bundled != expected:
            raise ValueError('Bundle does not match this checkout’s committed asset manifest')
        seen = set()
        while (member := archive.next()) is not None:
            item = by_name.get(member.name)
            if item is None or not member.isfile() or member.size != item['bytes'] or member.name in seen:
                raise ValueError(f'Unexpected, unsafe or duplicate bundle entry: {member.name}')
            seen.add(member.name)
            if groups and item['group'] not in groups:
                continue
            target = destination(member.name, repo)
            if target.exists():
                if target.is_file() and target.stat().st_size == item['bytes'] and digest(target) == item['sha256']:
                    installed += 1
                    continue
                raise ValueError(f'Existing asset differs; preserve it and use a clean checkout: {target}')
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temp = Path(output.name)
                try:
                    shutil.copyfileobj(archive.extractfile(member), output, 1024*1024)
                    output.flush()
                    if digest(temp) != item['sha256']:
                        raise ValueError(f'Asset checksum mismatch: {member.name}')
                    temp.replace(target)
                finally:
                    temp.unlink(missing_ok=True)
            installed += 1
            if installed % 250 == 0:
                print(f'Installed {installed} verified assets', flush=True)
        if seen != set(by_name):
            raise ValueError('Bundle is incomplete')
    print(f'Imported {installed} verified assets into {repo}', flush=True)


def verify(repo=REPO, groups=None):
    missing, mismatched, checked = [], [], 0
    for item in json.loads(MANIFEST.read_text())['files']:
        if groups and item['group'] not in groups:
            continue
        path = destination(item['path'], repo)
        if not path.is_file():
            missing.append(item['path'])
        elif path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            mismatched.append(item['path'])
        else:
            checked += 1
    result = dict(verified=checked, missing=missing, mismatched=mismatched)
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    exporter = actions.add_parser('export')
    exporter.add_argument('--workspace', type=Path, required=True)
    exporter.add_argument('--recordings', type=Path, required=True, help='JSON mapping stable names to original local paths')
    exporter.add_argument('--output', type=Path, required=True)
    importer = actions.add_parser('import')
    importer.add_argument('bundle', type=Path)
    importer.add_argument('--groups', nargs='+', choices=['runtime', 'recordings', 'samples', 'reference'])
    verifier = actions.add_parser('verify')
    verifier.add_argument('--groups', nargs='+', choices=['runtime', 'recordings', 'samples', 'reference'])
    args = parser.parse_args()
    if args.action == 'export':
        export_bundle(args.workspace, json.loads(args.recordings.read_text()), args.output)
    elif args.action == 'import':
        import_bundle(args.bundle, groups=args.groups)
    elif (result := verify(groups=args.groups))['missing'] or result['mismatched']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
