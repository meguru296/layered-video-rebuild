import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / 'scripts/audit_project.py'
spec = importlib.util.spec_from_file_location('audit_project', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT = None


def png(path, width=2, height=3):
    def chunk(name, payload):
        return struct.pack('>I', len(payload)) + name + payload + struct.pack('>I', zlib.crc32(name + payload))
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    image = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
    image += chunk(b'IDAT', zlib.compress((b'\x00' + bytes([200, 200, 200, 255]) * width) * height))
    path.write_bytes(image + chunk(b'IEND', b''))


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global ROOT
        temporary = tempfile.TemporaryDirectory(prefix='video-audit-')
        cls.addClassCleanup(temporary.cleanup)
        cls.temporary = temporary
        ROOT = Path(temporary.name) / '本地 project'
        ROOT.mkdir(parents=True, exist_ok=True)
        png(ROOT / '图稿.png')
        png(ROOT / 'f0001.png')
        png(ROOT / 'f0002.png')
        png(ROOT / 'wrong.png', height=4)

    def setUp(self):
        self.data = {
            'schema_version': 1,
            'timeline': {'frame_count': 2, 'fps_num': 24000, 'fps_den': 1001, 'width': 2, 'height': 3},
            'shots': [{'id': 'a', 'start': 0, 'end': 2}],
            'assets': [{'id': 'art', 'path': '图稿.png', 'status': 'approved'}],
            'layers': [{'id': 'figure', 'asset_ids': ['art'], 'intervals': [[0, 2]]}],
            'native_frames': [{'frame': 0, 'path': 'f0001.png'}, {'frame': 1, 'path': 'f0002.png'}],
            'tracks': [
                {'id': 'mirror', 'kind': 'affine', 'expected_sign': -1, 'samples': [{'frame': 0, 'matrix': [[-1, 0, 2], [0, 1, 0]]}]},
                {'id': 'correction', 'kind': 'affine', 'role': 'stabilization_correction', 'samples': [{'frame': 0, 'matrix': [[1, 0, 0], [0, 1, 0]]}]},
                {'id': 'draw', 'kind': 'progress', 'monotonic': 'increasing', 'bounds': [0, 360], 'required_value': 360,
                 'samples': [{'frame': 0, 'value': 0}, {'frame': 1, 'value': 360}, {'frame': 2, 'value': 360}]}
            ],
            'source_reuse': {'approved_intervals': [], 'used_intervals': []}
        }

    def run_audit(self, **kwargs):
        return module.audit(self.data, ROOT, **kwargs)

    def has_error(self, code, **kwargs):
        result = self.run_audit(**kwargs)
        self.assertFalse(result['ok'])
        self.assertIn(code, [x['code'] for x in result['errors']])

    def test_valid_mirror_proper_correction_rational_fps_and_boundary_key(self):
        self.assertTrue(self.run_audit(require_native=True)['ok'])

    def test_mirrored_stabilization_correction_rejected(self):
        self.data['tracks'][1]['samples'][0]['matrix'][1][1] = -1
        self.has_error('MATRIX_HANDEDNESS')

    def test_cannot_relabel_bad_correction_as_valid_mirror(self):
        self.data['tracks'][1]['expected_sign'] = -1
        self.has_error('CORRECTION_SIGN')

    def test_progress_reverses(self):
        self.data['tracks'][2]['samples'][2]['value'] = 300
        self.has_error('PROGRESS_REVERSAL')

    def test_never_completes_path(self):
        self.data['tracks'][2]['samples'][1]['value'] = 359
        self.data['tracks'][2]['samples'][2]['value'] = 359
        self.has_error('PROGRESS_REQUIRED_VALUE')

    def test_sequence_end_overflows(self):
        self.data['layers'][0]['intervals'][0][1] = 3
        self.has_error('INTERVAL')

    def test_glyph_sequence_bleeds_past_intended_end_inside_timeline(self):
        self.data['layers'][0]['expected_intervals'] = [[0, 1]]
        self.has_error('LAYER_INTERVAL_MISMATCH')

    def test_matching_actual_and_expected_strip_intervals(self):
        self.data['layers'][0]['expected_intervals'] = [[0, 2]]
        self.assertTrue(self.run_audit()['ok'])

    def test_duplicate_native_frame(self):
        self.data['native_frames'][1]['frame'] = 0
        self.has_error('NATIVE_DUPLICATE')

    def test_gap_is_allowed_only_for_partial_work(self):
        self.data['native_frames'].pop()
        self.has_error('NATIVE_GAP')
        self.assertTrue(self.run_audit(allow_partial=True)['ok'])

    def test_required_native_missing(self):
        self.data.pop('native_frames')
        self.has_error('NATIVE_REQUIRED', require_native=True)

    def test_shot_gap(self):
        self.data['shots'][0]['start'] = 1
        self.has_error('SHOT_GAP')

    def test_shot_overlap(self):
        self.data['shots'].append({'id': 'b', 'start': 1, 'end': 2})
        self.has_error('SHOT_OVERLAP')

    def test_path_traversal(self):
        self.data['assets'][0]['path'] = '../outside.png'
        self.has_error('MEDIA_ESCAPE')

    def test_absolute_windows_path(self):
        self.data['assets'][0]['path'] = 'C:/not-portable.png'
        self.has_error('MEDIA_PATH')

    def test_missing_asset(self):
        self.data['assets'][0]['path'] = 'missing.png'
        self.has_error('MEDIA_MISSING')

    def test_rejected_asset_in_render(self):
        self.data['assets'][0]['status'] = 'rejected'
        self.has_error('LAYER_UNAPPROVED_ASSET')

    def test_disabled_historical_layer_is_not_active(self):
        self.data['assets'][0]['status'] = 'rejected'
        self.data['layers'][0]['enabled'] = False
        self.assertTrue(self.run_audit()['ok'])

    def test_wrong_native_dimensions(self):
        self.data['native_frames'][1]['path'] = 'wrong.png'
        self.has_error('PNG_DIMENSIONS')

    def test_reuse_outside_approval(self):
        self.data['source_reuse'] = {'approved_intervals': [[0, 1]], 'used_intervals': [[0, 2]]}
        self.has_error('REUSE_OUTSIDE_APPROVAL')

    def test_adjacent_approved_intervals_form_a_union(self):
        self.data['source_reuse'] = {'approved_intervals': [[0, 1], [1, 2]], 'used_intervals': [[0, 2]]}
        self.assertTrue(self.run_audit()['ok'])

    def test_singular_matrix(self):
        self.data['tracks'][1]['samples'][0]['matrix'][0][0] = 0
        self.has_error('MATRIX_SINGULAR')

    def test_shear_not_representable_as_uniform_scale_rotation(self):
        self.data['tracks'][1]['representation'] = 'similarity'
        self.data['tracks'][1]['samples'][0]['matrix'][0][1] = .2
        self.has_error('MATRIX_REPRESENTATION')

    def test_uniform_reflection_is_still_a_similarity(self):
        self.data['tracks'][0]['representation'] = 'similarity'
        self.assertTrue(self.run_audit()['ok'])

    def test_nonfinite_matrix(self):
        self.data['tracks'][1]['samples'][0]['matrix'][0][0] = float('nan')
        self.has_error('MATRIX')

    def test_nonmonotonic_sample_frames(self):
        self.data['tracks'][2]['samples'][2]['frame'] = 1
        self.has_error('SAMPLE_ORDER')

    def test_boolean_frame_rate_is_not_integer(self):
        self.data['timeline']['fps_num'] = True
        self.has_error('FPS')

    def test_real_hash_validation(self):
        asset = self.data['assets'][0]
        asset['sha256'] = hashlib.sha256((ROOT / '图稿.png').read_bytes()).hexdigest()
        self.assertTrue(self.run_audit(verify_hashes=True)['ok'])
        asset['sha256'] = '0' * 64
        self.has_error('HASH_MISMATCH', verify_hashes=True)

    def test_cli_valid_and_invalid_exit_codes(self):
        manifest = ROOT / 'manifest.json'
        manifest.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        command = [sys.executable, '-X', 'utf8', str(SCRIPT), str(manifest), '--root', str(ROOT), '--require-native']
        good = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(good.returncode, 0, good.stderr + good.stdout)
        self.assertTrue(json.loads(good.stdout)['ok'])
        bad_data = copy.deepcopy(self.data)
        bad_data['tracks'][1]['samples'][0]['matrix'][1][1] = -1
        manifest.write_text(json.dumps(bad_data), encoding='utf-8')
        bad = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(bad.returncode, 1, bad.stderr + bad.stdout)
        self.assertFalse(json.loads(bad.stdout)['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
