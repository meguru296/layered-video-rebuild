import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'tools/build_release.py'


class ReleaseTests(unittest.TestCase):
    def build(self, dest, version='v1.1.0'):
        return subprocess.run([sys.executable, '-B', str(BUILD), '--version', version, '--output', str(dest)], capture_output=True, text=True)

    def test_release_contains_current_direction_and_feedback_references_without_repo_artifacts(self):
        with tempfile.TemporaryDirectory(prefix='skill-release-') as td:
            p = Path(td)
            result = self.build(p)
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = p / 'layered-video-rebuild-v1.1.0.zip'
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                self.assertEqual(len(names), 11)
                for ref in ['references/direction-and-routing.md', 'references/feedback-and-iteration.md']:
                    self.assertEqual(z.read('layered-video-rebuild/' + ref), (ROOT / ref).read_bytes())
                self.assertFalse(any('/tests/' in n or '/tools/' in n or '/.git/' in n for n in names))
                self.assertIsNone(z.testzip())
                self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist()))
            checksum = archive.with_suffix('.zip.sha256').read_text('ascii').split()[0]
            self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_release_is_reproducible_across_output_directories(self):
        with tempfile.TemporaryDirectory(prefix='skill-repeat-') as td:
            p = Path(td)
            for name in ['one', 'two']:
                result = self.build(p / name)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((p / 'one/layered-video-rebuild-v1.1.0.zip').read_bytes(), (p / 'two/layered-video-rebuild-v1.1.0.zip').read_bytes())

    def test_invalid_release_version_fails_without_creating_archive(self):
        with tempfile.TemporaryDirectory(prefix='skill-invalid-') as td:
            p = Path(td)
            result = self.build(p, '../invalid')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(p.rglob('*.zip')))


if __name__ == '__main__':
    unittest.main()
