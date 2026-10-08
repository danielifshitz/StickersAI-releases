"""Private Release transport; no signing keys, Actions artifacts or public staging."""
import base64
import datetime
import hashlib
import json
import re
import stat
import subprocess
import zipfile
from pathlib import Path

SOURCE = 'danielifshitz/StickersAI'
TARGETS = ('darwin-arm64', 'win32-x64')
MAX_ASSET = 2 * 1024**3  # GitHub requires each asset to be strictly smaller.
GATES = (
    'Validate release version', 'Build account and disk preflight', 'Create isolated Python environment',
    'Frontend tests', 'Frontend typecheck', 'Build desktop editor', 'Build MCP editor',
    'Native tests', 'Backend tests', 'Freeze runtime and run real SAM/PDF release gate',
    'Packaged service smoke test', 'STDIO bridge integration test', 'Build installers',
    'Packaged update and recovery gate', 'Final package integrity', 'Stage private packages',
)
VERSION = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
# Forge's Windows installer includes one literal space. Keep all other names strict.
NAME = re.compile(r'(?:[A-Za-z0-9][A-Za-z0-9._-]{0,150}|StickersAI-(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*) Setup\.exe)\Z')


def digest(file):
    result = hashlib.sha256()
    with Path(file).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def gh(*args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=1800)
    if result.returncode:
        # Never include token-bearing subprocess environment or remote error bodies.
        raise ValueError('GitHub operation failed; check access, connectivity and the workflow log')
    return result.stdout


def api(path):
    return json.loads(gh('api', path))


def find_release(tag, repo=SOURCE, required=True):
    # The tag endpoint promises published releases; authenticated listing includes drafts.
    matches = []
    for page in range(1, 101):
        releases = api(f'repos/{repo}/releases?per_page=100&page={page}')
        matches.extend(value for value in releases if value.get('tag_name') == tag)
        if len(releases) < 100:
            break
    else:
        raise ValueError('Release inventory exceeds the safe pagination limit')
    if len(matches) > 1 or required and not matches:
        raise ValueError('Matching release is missing or duplicated; check draft read access')
    return matches[0] if matches else None


def positive(value):
    return type(value) is int and value > 0


def context(version, run_id, attempt, sha, target):
    if (not VERSION.fullmatch(version) or not re.fullmatch(r'[1-9]\d{0,19}', str(run_id))
            or not positive(attempt) or not SHA.fullmatch(sha) or target not in TARGETS):
        raise ValueError('Invalid release build identity')
    return {'version': version, 'sourceTag': 'v' + version, 'sourceSha': sha,
            'runId': str(run_id), 'attempt': attempt, 'target': target}


def staging_tag(identity):
    return f"build-v{identity['version']}-{identity['runId']}-{identity['attempt']}-{identity['target']}"


def release_record(raw, notes, version):
    value = json.loads(raw)
    if (not VERSION.fullmatch(version) or value.get('version') != version
            or value.get('sourceTag') != 'v' + version
            or value.get('targets') != list(TARGETS)
            or value.get('status') != 'prepared'
            or not isinstance(value.get('reason'), str) or not value['reason'].strip()
            or not isinstance(value.get('changes'), list) or not value['changes']
            or any(not isinstance(c, str) or not c.strip() for c in value['changes'])):
        raise ValueError('A matching prepared release record and release reason are required')
    previous = value.get('previousPublicVersion', '')
    if not VERSION.fullmatch(previous) or tuple(map(int, previous.split('.'))) >= tuple(map(int, version.split('.'))):
        raise ValueError('Release must be newer than the previous public version')
    datetime.date.fromisoformat(value['date'])
    text = notes.decode('utf-8')
    if not text.startswith('# StickersAI ' + version + '\n') or value['reason'] not in text:
        raise ValueError('Public notes must contain the matching version and release reason')
    return value


def inventory_check(files, version, target):
    name = 'update-target-' + target + '.json'
    value = json.loads(files[name].read_bytes())
    package = f'StickersAI-{target}-{version}.zip' if target.startswith('darwin-') else f'StickersAIDesktop-{version}-full.nupkg'
    expected = [('package', package)] + ([('releases', 'RELEASES')] if target == 'win32-x64' else [])
    if (value.get('version') != version or value.get('target') != target
            or not positive(value.get('unpackedBytes'))
            or [(a.get('kind'), a.get('name')) for a in value.get('artifacts', [])] != expected):
        raise ValueError('Invalid target inventory or package version')
    for artifact in value['artifacts']:
        file = files.get(artifact['name'])
        if (not file or not positive(artifact.get('bytes')) or file.stat().st_size != artifact['bytes']
                or digest(file) != artifact.get('sha256')):
            raise ValueError('Package does not match its tested inventory')
    with zipfile.ZipFile(files[package]) as archive:
        if sum(entry.file_size for entry in archive.infolist()) != value['unpackedBytes']:
            raise ValueError('Unpacked package size differs from inventory')
    if target.startswith('darwin-'):
        if f'StickersAI-{version}-arm64.dmg' not in files:
            raise ValueError('Matching Mac installer is required')
    else:
        if len([name for name in files if name.endswith('.exe')]) != 1:
            raise ValueError('Exactly one Windows installer is required')
        metadata = files['RELEASES'].read_text(encoding='utf-8-sig').strip().splitlines()
        with files[package].open('rb') as stream:
            sha1 = hashlib.file_digest(stream, 'sha1').hexdigest()
        fields = metadata[0].split() if len(metadata) == 1 else []
        if (len(fields) != 3 or not re.fullmatch(r'[a-fA-F0-9]{40}', fields[0])
                or fields[0].lower() != sha1 or fields[1] != package
                or fields[2] != str(files[package].stat().st_size)):
            raise ValueError('Squirrel RELEASES does not match the full package')
    return value


def make_bundle(folder, docs, destination, identity):
    files = {}
    for file in folder.rglob('*'):
        if file.is_symlink():
            raise ValueError('Staging must not contain symbolic links')
        if not file.is_file():
            continue
        if file.suffix not in ('.zip', '.dmg', '.exe', '.nupkg', '.txt', '.json') and file.name != 'RELEASES':
            raise ValueError('Unexpected staging file')
        if not NAME.fullmatch(file.name) or file.name.casefold() in {name.casefold() for name in files}:
            raise ValueError('Duplicate or unsafe staging filename')
        files[file.name] = file
    record = docs / (identity['version'] + '.json')
    notes = docs / (identity['version'] + '.md')
    release_record(record.read_bytes(), notes.read_bytes(), identity['version'])
    for name, file in [('release.json', record), ('release-notes.md', notes)]:
        if name in files:
            raise ValueError('Reserved staging filename')
        files[name] = file
    if 'build-record.json' in files or {name for name in files if name.startswith('update-target-')} != {'update-target-' + identity['target'] + '.json'}:
        raise ValueError('Unexpected build record or target inventory')
    inventory_check(files, identity['version'], identity['target'])
    build = {'format': 1, **identity, 'files': [
        {'name': name, 'bytes': file.stat().st_size, 'sha256': digest(file)} for name, file in sorted(files.items())]}
    raw = (json.dumps(build, sort_keys=True) + '\n').encode()
    # ZIP_STORED avoids decompressing an untrusted transfer wrapper at the publisher.
    if sum(p.stat().st_size for p in files.values()) + len(raw) + 65536 >= MAX_ASSET:
        raise ValueError('Transfer archive reaches the 2 GiB release-asset limit')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = destination.with_suffix('.partial')
    if destination.exists() or partial.exists():
        raise ValueError('Staging output already exists; use a new build attempt')
    try:
        with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_STORED) as archive:
            partial.chmod(0o600)
            for name, file in sorted(files.items()):
                archive.write(file, name)
            archive.writestr('build-record.json', raw)
        if partial.stat().st_size >= MAX_ASSET:
            raise ValueError('Transfer archive reaches the 2 GiB release-asset limit')
        partial.rename(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return build


def unpack_bundle(bundle, destination, identity, expected_record, expected_notes):
    if bundle.stat().st_size >= MAX_ASSET or destination.exists():
        raise ValueError('Oversized bundle or occupied extraction destination')
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (len(entries) > 32 or len({name.casefold() for name in names}) != len(names)
                or sum(entry.file_size for entry in entries) >= MAX_ASSET
                or any(not NAME.fullmatch(e.filename) or e.is_dir()
                       or stat.S_ISLNK(e.external_attr >> 16) or e.compress_type != zipfile.ZIP_STORED
                       or e.flag_bits & 1 for e in entries)):
            raise ValueError('Unsafe transfer archive')
        if (not {'build-record.json', 'release.json', 'release-notes.md'}.issubset(names)
                or archive.getinfo('build-record.json').file_size > 1024 * 1024):
            raise ValueError('Missing or oversized build record')
        build = json.loads(archive.read('build-record.json'))
        if build.get('format') != 1 or any(build.get(key) != value for key, value in identity.items()):
            raise ValueError('Build record does not match workflow identity')
        records = build.get('files')
        if not isinstance(records, list) or len(records) != len(names) - 1:
            raise ValueError('Invalid build file inventory')
        indexed = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError('Invalid build file inventory')
            name = record.get('name', '')
            if (name not in names or name == 'build-record.json' or name in indexed
                    or type(record.get('bytes')) is not int or record['bytes'] < 0
                    or not HASH.fullmatch(record.get('sha256', ''))
                    or archive.getinfo(name).file_size != record['bytes']):
                raise ValueError('Invalid build file inventory')
            indexed[name] = record
        if archive.read('release.json') != expected_record or archive.read('release-notes.md') != expected_notes:
            raise ValueError('Release notes differ from the tagged source')
        release_record(expected_record, expected_notes, identity['version'])
        destination.mkdir(parents=True, mode=0o700)
        for name, record in indexed.items():
            file = destination / name
            with archive.open(name) as source, file.open('xb') as output:
                result = hashlib.sha256()
                while chunk := source.read(1024 * 1024):
                    result.update(chunk)
                    output.write(chunk)
            if result.hexdigest() != record['sha256']:
                raise ValueError('Tampered transfer file')
        files = {p.name: p for p in destination.iterdir()}
        if {n for n in files if n.startswith('update-target-')} != {'update-target-' + identity['target'] + '.json'}:
            raise ValueError('Duplicate or unexpected native inventory')
        inventory_check(files, identity['version'], identity['target'])
    return build


def source_file(path, sha):
    value = api(f'repos/{SOURCE}/contents/{path}?ref={sha}')
    if value.get('encoding') != 'base64' or value.get('type') != 'file' or value.get('size', MAX_ASSET) > 1024 * 1024:
        raise ValueError('Invalid source release record')
    return base64.b64decode(value['content'])


def validate_run(run, version, tag_sha, jobs):
    if (not VERSION.fullmatch(version) or run.get('status') != 'completed'
            or run.get('conclusion') != 'success' or run.get('event') != 'push'
            or run.get('head_branch') != 'v' + version or run.get('head_sha') != tag_sha
            or not SHA.fullmatch(tag_sha) or run.get('path') != '.github/workflows/desktop.yml'
            or run.get('repository', {}).get('full_name') != SOURCE
            or run.get('repository', {}).get('private') is not True
            or not positive(run.get('run_attempt'))):
        raise ValueError('Only a successful matching private tagged Desktop packages workflow can be published')
    if len(jobs) != len(TARGETS):
        raise ValueError('Exactly two supported native jobs are required')
    for target in TARGETS:
        matching = [job for job in jobs if job.get('name') == f'native ({target})']
        if len(matching) != 1:
            raise ValueError('Missing or duplicate native target job')
        job = matching[0]
        if (job.get('conclusion') != 'success' or job.get('head_sha') != tag_sha
                or job.get('run_attempt') != run['run_attempt']
                or not {'self-hosted', 'stickersai-release', 'stickersai-' + target}.issubset(set(job.get('labels', [])))):
            raise ValueError('Native job identity or runner does not match')
        for gate in GATES:
            steps = [step for step in job.get('steps', []) if step.get('name') == gate]
            if len(steps) != 1 or steps[0].get('conclusion') != 'success':
                raise ValueError('Every native release gate must pass')


def tag_commit(version):
    value = api(f'repos/{SOURCE}/git/ref/tags/v{version}')['object']
    for _ in range(4):
        if value['type'] == 'commit':
            return value['sha']
        if value['type'] != 'tag':
            break
        value = api(f"repos/{SOURCE}/git/tags/{value['sha']}")['object']
    raise ValueError('Release tag does not resolve to a commit')
