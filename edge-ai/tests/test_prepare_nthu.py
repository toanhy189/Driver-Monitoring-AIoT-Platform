"""Preparation must preserve frame labels, holdout isolation and user files."""

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.prepare_nthu import collect, member_key, parse_labels, prepare, safe_member, validate_roles


def fixture(path, subject="001", mixed=False):
    with zipfile.ZipFile(path, "w") as archive:
        if mixed:
            archive.writestr(f"{subject}/{subject}_nightnoglasses_mix.mp4", b"video-" + subject.encode())
            archive.writestr(f"{subject}/{subject}_night_noglasses_mixing_drowsiness.txt", "0011")
        else:
            archive.writestr(f"{subject}/glasses/sleepyCombination.avi", b"video-" + subject.encode())
            archive.writestr(f"{subject}/glasses/{subject}_sleepyCombination_drowsiness.txt", "0011")


class PreparationTests(unittest.TestCase):
    def test_frame_label_parser_rejects_unknown_labels(self):
        self.assertEqual(parse_labels(b"\xef\xbb\xbf0 0\n1 1\r\n"), "0011")
        for invalid in (b"", b"012", b"drowsy", b"0,1"):
            with self.assertRaises(ValueError):
                parse_labels(invalid)

    def test_training_and_mixed_name_pairing(self):
        self.assertEqual(member_key("004/004_nightnoglasses_mix.mp4"),
                         member_key("004/004_night_noglasses_mixing_drowsiness.txt"))
        with tempfile.TemporaryDirectory() as temporary:
            for mixed in (False, True):
                path = Path(temporary) / f"{mixed}.zip"
                fixture(path, mixed=mixed)
                with zipfile.ZipFile(path) as archive:
                    rows = collect(archive, path, "development")
                self.assertEqual(rows[0]["annotation_frames"], 4)
                self.assertEqual(rows[0]["drowsy_frames"], 2)

    def test_subject_leakage_and_duplicate_video_are_rejected(self):
        entry = {"subject_id": "nthu-001", "role": "development", "video_crc32": 1, "video_bytes": 5}
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_roles([entry, {**entry, "role": "heldout", "video_crc32": 2}])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_roles([entry, {**entry, "subject_id": "nthu-002"}])

    def test_unsafe_members_rejected(self):
        for name in ("../001/file.avi", "/001/file.avi", "001/../../file.avi", "C:/001/file.avi"):
            with self.assertRaises(ValueError):
                safe_member(name)

    def test_catalog_creates_no_videos_and_keeps_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a, b = root / "a.zip", root / "b.zip"
            fixture(a)
            fixture(b, "004", mixed=True)
            rows, audit = prepare([a], [b], root / "audit", root / "videos")
            self.assertEqual(len(rows), 2)
            self.assertFalse((root / "videos").exists())
            self.assertEqual(audit["roles"]["heldout"]["subjects"], ["nthu-004"])

    def test_mismatch_quarantined_and_existing_files_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a, b = root / "a.zip", root / "b.zip"
            fixture(a)
            fixture(b, "004", mixed=True)
            with patch("ml.prepare_nthu.video_metadata", return_value=(30.0, 3)), \
                    patch("ml.prepare_nthu.shutil.disk_usage", return_value=SimpleNamespace(free=100 * 1024 ** 3)):
                rows, audit = prepare([a], [b], root / "audit", root / "videos", extract=True)
            self.assertEqual(audit["statuses"], {"QUARANTINED": 2})
            self.assertTrue(all(r["annotation_frames"] == 4 for r in rows))
            path = Path(rows[0]["video_path"])
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "overwrite"):
                prepare([a], [b], root / "audit-again", root / "videos", extract=True)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
