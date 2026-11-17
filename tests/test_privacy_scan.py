#!/usr/bin/env python3
"""Exercise privacy checks on decoded APK metadata and extracted payloads."""
import contextlib, hashlib, io, json, runpy, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
script = Path(__file__).resolve().parents[1] / 'tools/privacy_scan.py'
with tempfile.TemporaryDirectory(prefix='sr7420-privacy-test-') as tmp:
    root = Path(tmp)
    package = root / 'example.apk'
    package.write_bytes(b'ADB compressed metadata fixture')
    apk = root / 'apk'
    apk.touch()
    needles = root / 'needles.json'
    needles.write_text(json.dumps({'text': ['private-fixture-9ac1']}))
    def exercise(metadata, payload, expected, tool=True, reviewed=None):
        report = root / 'report.json'
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if 'adbdump' in command:
                return subprocess.CompletedProcess(command, 0, stdout=metadata)
            assert 'extract' in command and '--no-chown' in command
            destination = Path(command[command.index('--destination') + 1])
            (destination / 'example.txt').write_bytes(payload)
            return subprocess.CompletedProcess(command, 0, stdout=b'')
        argv = [str(script), str(package), '--needles-json', str(needles), '--report', str(report)]
        if tool:
            argv += ['--apk-tool', str(apk)]
        if reviewed:
            argv += ['--reviewed-matches-json', str(reviewed)]
        with patch.object(sys, 'argv', argv), patch('subprocess.run', side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(script), run_name='__main__')
            except SystemExit as e:
                assert e.code == (0 if expected else 1)
        result = json.loads(report.read_text())
        assert result['passed'] is expected
        assert not any('private-fixture-9ac1' in str(item) for item in result['findings'])
        return result, calls
    result, calls = exercise(b'info:\n  name: harmless\n', b'clean payload', True)
    assert len(calls) == 2
    result, calls = exercise(b'info:\n  description: private-fixture-9ac1\n', b'clean', False)
    assert any(x['path'].endswith('!APK-METADATA.txt') for x in result['findings'])
    result, calls = exercise(b'info: clean', b'private-fixture-9ac1', False)
    assert any(x['path'].endswith('!example.txt') for x in result['findings'])
    reviews = root / 'reviews.json'
    reviews.write_text(json.dumps({'entries': [{'artifact_sha256': hashlib.sha256(b'private-fixture-9ac1').hexdigest(),
        'needle_sha256': hashlib.sha256(b'private-fixture-9ac1').hexdigest(),
        'reason': 'Verified synthetic upstream test fixture', 'upstream_verified': True}]}))
    result, calls = exercise(b'info: clean', b'private-fixture-9ac1', True, reviewed=reviews)
    assert len(result['reviewed_upstream_matches']) == 1
    result, calls = exercise(b'info: clean', b'changed private-fixture-9ac1', False, reviewed=reviews)
    assert not result['reviewed_upstream_matches']

    reviews.write_text(json.dumps({'entries': [{'artifact_sha256': hashlib.sha256(b'private-fixture-9ac1').hexdigest(),
        'needle_sha256': hashlib.sha256(b'private-fixture-9ac1').hexdigest(),
        'reason': 'Synthetic intentional public repository URL fixture', 'public_repository_url_verified': True}]}))
    result, calls = exercise(b'info: clean', b'private-fixture-9ac1', True, reviewed=reviews)
    assert not result['reviewed_upstream_matches'] and len(result['reviewed_public_repository_matches']) == 1
    result, calls = exercise(b'info: clean', b'changed private-fixture-9ac1', False, reviewed=reviews)
    assert not result['reviewed_public_repository_matches']

    result, calls = exercise(b'clean', b'clean', False, tool=False)
    assert not calls and result['findings'][0]['reason'] == 'apk_payload_not_inspected'
    package = root / 'packages.adb'
    package.write_bytes(b'ADB compressed index fixture')
    result, calls = exercise(b'private-fixture-9ac1', b'clean', False)
    assert len(calls) == 1 and result['findings'][0]['path'].endswith('!ADB-METADATA.txt')
print('APK metadata and payload privacy checks, and missing-tool rejection passed')
