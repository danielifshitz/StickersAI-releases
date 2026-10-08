"""Fetch private Release assets only after all tagged self-hosted gates pass."""
import json
import os
import re
import tempfile
from pathlib import Path

from release_transport import (SOURCE, TARGETS, MAX_ASSET, VERSION, api, context,
                               digest, find_release, gh, release_record, source_file, staging_tag,
                               tag_commit, unpack_bundle, validate_run)


def download(version, run_id, destination=Path('artifacts'), notes_file=Path('release-notes.md'),
             provenance_file=Path('release-provenance.json')):
    if not VERSION.fullmatch(version) or not re.fullmatch(r'[1-9]\d{0,19}', run_id):
        raise ValueError('Use a numeric workflow run ID and a stable release version')
    if destination.exists() or notes_file.exists() or provenance_file.exists():
        raise ValueError('Publisher outputs already exist; start with a fresh checkout')
    run = api(f'repos/{SOURCE}/actions/runs/{run_id}')
    sha = tag_commit(version)
    result = api(f"repos/{SOURCE}/actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100")
    if result['total_count'] != len(result['jobs']):
        raise ValueError('Unexpected number of source jobs')
    validate_run(run, version, sha, result['jobs'])
    raw = source_file(f'docs/releases/{version}.json', sha)
    notes = source_file(f'docs/releases/{version}.md', sha)
    record = release_record(raw, notes, version)
    provenance = {'format': 1, 'version': version, 'sourceTag': 'v' + version, 'sourceSha': sha,
                  'runId': run_id, 'attempt': run['run_attempt'], 'reason': record['reason'],
                  'nativeValidation': 'passed', 'cleanMachineAcceptance': 'pending', 'targets': {}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stickersai-publisher-', dir=destination.parent) as temporary:
        temporary = Path(temporary)
        verified = temporary / 'verified'
        for target in TARGETS:
            identity = context(version, run_id, run['run_attempt'], sha, target)
            tag = staging_tag(identity)
            release = find_release(tag)
            filename = 'desktop-' + target + '.zip'
            assets = release.get('assets', [])
            if (release.get('draft') is not True or release.get('tag_name') != tag
                    or release.get('target_commitish') != sha or len(assets) != 1
                    or assets[0].get('name') != filename or assets[0].get('state') != 'uploaded'
                    or type(assets[0].get('size')) is not int or not 0 < assets[0]['size'] < MAX_ASSET):
                raise ValueError('Matching private tested package is missing or incomplete')
            incoming = temporary / ('incoming-' + target)
            gh('release', 'download', tag, '--repo', SOURCE, '--pattern', filename, '--dir', str(incoming))
            bundle = incoming / filename
            if bundle.stat().st_size != assets[0]['size'] or assets[0].get('digest') != 'sha256:' + digest(bundle):
                raise ValueError('Downloaded archive differs from the verified GitHub asset')
            build = unpack_bundle(bundle, verified / target, identity, raw, notes)
            provenance['targets'][target] = {'stagingReleaseId': release['id'],
                                              'transferSha256': digest(bundle), 'files': build['files']}
        latest = api(f'repos/{SOURCE}/actions/runs/{run_id}')
        if (tag_commit(version) != sha or latest.get('run_attempt') != run['run_attempt']
                or latest.get('status') != 'completed' or latest.get('conclusion') != 'success'):
            raise ValueError('Source build changed during download')
        verified.rename(destination)
    footer = (f'\n\nBuild provenance: `v{version}`, source `{sha}`, '
              f'[run {run_id}, attempt {run["run_attempt"]}]'
              f'(https://github.com/{SOURCE}/actions/runs/{run_id}). '
              'Both native release gates passed. Clean-machine acceptance is pending; '
              'this draft must not be promoted to stable/latest until acceptance is recorded.\n')
    notes_file.write_text(notes.decode('utf-8') + footer, encoding='utf-8')
    provenance_file.write_text(json.dumps(provenance, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print('Verified private packages for both native targets:', version)


if __name__ == '__main__':
    download(os.environ['STICKERSAI_RELEASE_VERSION'], os.environ['STICKERSAI_SOURCE_RUN_ID'])
