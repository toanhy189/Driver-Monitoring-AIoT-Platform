"""Synthetic timing and fusion cases; no real-camera accuracy claims."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.runtime import fuse_state
from service.eye_closure_guard import EyeClosureGuard


class EyeClosureGuardTests(unittest.TestCase):
    def test_blinks_do_not_add_up_to_prolonged_closure(self):
        guard = EyeClosureGuard()
        for tick in range(61):
            self.assertFalse(guard.update(tick / 10, .1 if tick % 5 < 2 else .3))

    def test_continuous_closure_and_open_recovery_need_full_duration(self):
        guard = EyeClosureGuard()
        for tick in range(10):
            self.assertFalse(guard.update(tick / 10, .1))
        self.assertTrue(guard.update(1, .1))
        for tick in range(11, 21):
            self.assertTrue(guard.update(tick / 10, .3))
        self.assertFalse(guard.update(2.1, .3))

    def test_short_open_interval_does_not_clear_active_guard(self):
        guard = EyeClosureGuard()
        for tick in range(11):
            guard.update(tick / 10, .1)
        self.assertTrue(guard.update(1.1, .3))
        self.assertTrue(guard.update(1.5, .3))
        self.assertTrue(guard.update(1.6, .1))

    def test_missing_and_invalid_ear_cancel_immediately(self):
        for missing in (None, float("nan"), float("inf"), -.1):
            with self.subTest(missing=missing):
                guard = EyeClosureGuard()
                for tick in range(11):
                    guard.update(tick / 10, .1)
                self.assertFalse(guard.update(1.1, missing))
                self.assertFalse(guard.update(1.2, .1))
                for tick in range(13, 22):
                    self.assertFalse(guard.update(tick / 10, .1))
                self.assertTrue(guard.update(2.2, .1))

    def test_gap_with_no_frames_does_not_extend_closure(self):
        guard = EyeClosureGuard()
        guard.update(0, .1)
        guard.update(.4, .1)
        self.assertFalse(guard.update(5, .1))
        self.assertFalse(guard.update(5.4, .1))
        self.assertFalse(guard.update(5.8, .1))
        self.assertTrue(guard.update(6, .1))
        self.assertFalse(guard.update(7, .1))

    def test_invalid_clock_and_settings_cannot_leave_active_evidence(self):
        for settings in ({"closed_seconds": 0}, {"recovery_seconds": float("inf")},
                         {"ear_threshold": -.2}, {"max_gap_seconds": 0}):
            with self.assertRaises(ValueError):
                EyeClosureGuard(**settings)
        guard = EyeClosureGuard()
        guard.update(1, .1)
        with self.assertRaises(ValueError):
            guard.update(.5, .1)
        self.assertFalse(guard.active)

    def test_fusion_uses_eye_evidence_without_overriding_missing_data(self):
        guard = EyeClosureGuard()
        head = {"valid": True, "calibrating": False, "is_distracted": False}
        for tick in range(11):
            active = guard.update(tick / 10, .1)
        self.assertEqual(fuse_state(0, head, eye_closure_risk=active), "DROWSY")
        self.assertEqual(fuse_state(None, head, eye_closure_risk=active), "DROWSY")
        active = guard.update(1.1)
        self.assertEqual(fuse_state(None, None, eye_closure_risk=active), "UNKNOWN")
        self.assertEqual(fuse_state(1, head, eye_closure_risk=active), "DROWSY")


if __name__ == "__main__":
    unittest.main()
