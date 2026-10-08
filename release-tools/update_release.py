"""Create target inventories, then sign one aggregate release after all native gates."""
import argparse
import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY = 'danielifshitz/StickersAI-releases'
TARGETS = ('darwin-arm64', 'win32-x64')
ROOT = Path(__file__).resolve().parent


def digest(file):
    value = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def inventory(folder, target, version):
    if target not in TARGETS or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Invalid stable release version or target')
    files = list(folder.rglob('*'))
    if target.startswith('darwin-'):
        packages = [p for p in files if p.name == f'StickersAI-{target}-{version}.zip']
    else:
        packages = [p for p in files if p.name == f'StickersAIDesktop-{version}-full.nupkg']
    if len(packages) != 1:
        raise ValueError('Exactly one target update package is required')
    package = packages[0]
    with zipfile.ZipFile(package) as archive:
        unpacked = sum(entry.file_size for entry in archive.infolist())
    artifacts = [{'kind': 'package', 'name': package.name, 'bytes': package.stat().st_size, 'sha256': digest(package)}]
    if target == 'win32-x64':
        releases = package.parent / 'RELEASES'
        artifacts.append({'kind': 'releases', 'name': releases.name, 'bytes': releases.stat().st_size, 'sha256': digest(releases)})
    value = {'version': version, 'target': target, 'unpackedBytes': unpacked, 'artifacts': artifacts}
    (folder / ('update-target-' + target + '.json')).write_text(json.dumps(value, sort_keys=True) + '\n')
    return value


def sign(folder, destination, key_pem, expected_public_key, *, expected_version=None, provenance=None):
    key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Release signing requires an Ed25519 key')
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    if public != expected_public_key:
        raise ValueError('Release private key does not match the embedded verification key')
    if provenance is not None:
        record = json.loads(provenance.read_bytes())
        if (record.get('format') != 1 or record.get('version') != expected_version
                or record.get('nativeValidation') != 'passed'
                or set(record.get('targets', {})) != set(TARGETS)):
            raise ValueError('Invalid verified release provenance')
        for target in TARGETS:
            child = folder / target
            expected_files = record['targets'][target]['files']
            if {p.name for p in child.iterdir()} != {a['name'] for a in expected_files}:
                raise ValueError('Release files changed after verified download')
            for artifact in expected_files:
                name = artifact['name']
                file = child / name
                if (Path(name).name != name or file.is_symlink() or not file.is_file()
                        or file.stat().st_size != artifact['bytes'] or digest(file) != artifact['sha256']):
                    raise ValueError('Release files changed after verified download')
    targets, release_version = {}, None
    for file in folder.rglob('update-target-*.json'):
        value = json.loads(file.read_text())
        target = value['target']
        if target not in TARGETS or target in targets:
            raise ValueError('Invalid or duplicate release target')
        if release_version and value['version'] != release_version:
            raise ValueError('Release targets have different versions')
        release_version = value['version']
        targets[target] = {name: value[name] for name in ('unpackedBytes', 'artifacts')}
        for artifact in value['artifacts']:
            candidates = [p for p in file.parent.rglob(artifact['name']) if p.is_file()]
            if len(candidates) != 1 or candidates[0].stat().st_size != artifact['bytes'] or digest(candidates[0]) != artifact['sha256']:
                raise ValueError('Release artifact does not match its tested inventory')
    if set(targets) != set(TARGETS):
        raise ValueError('All supported native targets must pass before signing a public release')
    if expected_version is not None and release_version != expected_version:
        raise ValueError('Requested version does not match tested artifacts')
    if destination.exists():
        raise ValueError('Release destination already exists; never overwrite signed assets')
    destination.mkdir(parents=True)
    raw = (json.dumps({'format': 1, 'repository': REPOSITORY, 'version': release_version, 'targets': targets}, sort_keys=True, separators=(',', ':')) + '\n').encode()
    (destination / 'update-manifest.json').write_bytes(raw)
    (destination / 'update-manifest.sig').write_bytes(key.sign(raw))
    for file in folder.rglob('*'):
        if file.is_file() and (file.suffix in ('.zip', '.dmg', '.exe', '.nupkg', '.txt') or file.name == 'RELEASES'):
            out = destination / file.name
            if out.exists():
                raise ValueError('Duplicate release asset name')
            shutil.copy2(file, out)
    return release_version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['inventory', 'sign'])
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--target', choices=TARGETS)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--provenance', type=Path)
    args = parser.parse_args()
    if args.command == 'inventory':
        version = json.loads((ROOT / 'package.json').read_text())['version']
        inventory(args.folder, args.target, version)
    else:
        key = os.environ.pop('STICKERSAI_UPDATE_PRIVATE_KEY').encode()
        expected = os.environ.get('STICKERSAI_RELEASE_VERSION')
        release_version = sign(args.folder, args.destination, key, (ROOT / 'update/public-key.pem').read_bytes(),
                               expected_version=expected, provenance=args.provenance)
        if expected and expected != release_version:
            raise ValueError('Requested version does not match tested artifacts')
        tag = os.environ.get('GITHUB_REF_NAME') if not expected else 'v' + expected
        if tag and tag != 'v' + release_version:
            raise ValueError('Release tag does not match tested artifacts')
        print('Verified and signed release', release_version)


if __name__ == '__main__':
    main()
