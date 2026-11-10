from pathlib import Path
import math
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.head_motion import HeadMotionTracker, rotation_angles


class HeadMotionTests(unittest.TestCase):
    def setUp(self):
        self.tracker = HeadMotionTracker()
        self.now = 0.

    def feed(self, pitch=0., seconds=.1, **kwargs):
        result = None
        for _ in range(round(seconds/.1)):
            self.now += .1
            result = self.tracker.update(self.now, dict(pitch=pitch, yaw=kwargs.pop("yaw", 0.), roll=0.),
                                         neutral_allowed=True, **kwargs)
        return result

    def calibrate(self):
        result = self.feed(seconds=3.5)
        self.assertEqual(result["state"], "NEUTRAL")
        return result

    def nod(self, **kwargs):
        self.feed(7., .2, **kwargs)
        self.feed(17., .5, **kwargs)
        return self.feed(0., .2, **kwargs)

    def test_matrix_angles_remove_scale_and_ignore_translation(self):
        angle = math.radians(18)
        m = np.eye(4)
        m[:3, :3] = np.array([[1, 0, 0], [0, math.cos(angle), -math.sin(angle)],
                              [0, math.sin(angle), math.cos(angle)]])*1.2
        m[:3, 3] = [100, -20, -50]
        result = rotation_angles(m)
        self.assertAlmostEqual(result["pitch"], 18.)
        self.assertAlmostEqual(result["yaw"], 0.)
        self.assertAlmostEqual(result["roll"], 0.)

    def test_matrix_rejects_degenerate_reflected_nonfinite_and_singular(self):
        for value in (None, np.eye(3), np.zeros((4, 4)), np.eye(4)*float("nan"),
                      np.diag([-1, 1, 1, 1]), np.diag([2, 1, 1, 1])):
            self.assertIsNone(rotation_angles(value))
        singular = np.eye(4)
        singular[:3, :3] = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
        self.assertIsNone(rotation_angles(singular))

    def test_calibration_requires_continuous_stable_frontal_observations(self):
        for i in range(40):
            result = self.tracker.update(i*.1, dict(pitch=0., yaw=0., roll=0.), neutral_allowed=False)
        self.assertEqual(result["state"], "CALIBRATING")
        self.assertIsNone(result["pitch_deg"])
        for i in range(40, 80):
            result = self.tracker.update(i*.1, dict(pitch=10.*(i%2), yaw=0., roll=0.), neutral_allowed=True)
        self.assertFalse(result["calibrated"])

    def test_two_complete_cycles_are_observations_not_sleep_or_commands(self):
        self.calibrate()
        once = self.nod()
        self.assertEqual(once["nod_count"], 1)
        twice = self.nod()
        self.assertEqual(twice["state"], "REPEATED_NODS")
        self.assertEqual(twice["nod_count"], 2)
        self.assertEqual(twice["mode"], "OBSERVE_ONLY")
        self.assertFalse(twice["eye_closure_supported"])
        self.assertNotIn("driver_state", twice)

    def test_eye_support_requires_current_closure_and_clears_immediately(self):
        self.calibrate(); self.nod(); self.nod()
        self.assertTrue(self.feed(eye_closed=True)["eye_closure_supported"])
        self.assertFalse(self.feed(eye_closed=False)["eye_closure_supported"])

    def test_long_look_down_and_brief_twitch_are_not_nods(self):
        self.calibrate()
        self.feed(17., 7.)
        self.assertEqual(self.feed(0.)["nod_count"], 0)
        self.feed(17., .1)
        self.assertEqual(self.feed(0.)["nod_count"], 0)

    def test_face_loss_gap_and_backwards_time_clear_all_cycle_evidence(self):
        self.calibrate(); self.nod(); self.nod()
        baseline = dict(self.tracker.baseline)
        missing = self.tracker.update(self.now+.1, None)
        self.assertEqual(missing["state"], "UNAVAILABLE")
        self.assertEqual(missing["nod_count"], 0)
        self.assertIsNone(missing["pitch_deg"])
        self.now += .1
        self.nod()
        gap = self.tracker.update(self.now+1., dict(pitch=0., yaw=0., roll=0.))
        self.assertEqual(gap["state"], "UNAVAILABLE")
        self.assertEqual(gap["nod_count"], 0)
        self.assertEqual(self.tracker.baseline, baseline)
        backwards = self.tracker.update(self.now, dict(pitch=0., yaw=0., roll=0.))
        self.assertEqual(backwards["state"], "UNAVAILABLE")

    def test_side_turn_extreme_pitch_and_invalid_numbers_interrupt(self):
        self.calibrate(); self.nod()
        for angles in (dict(pitch=15., yaw=35., roll=0.), dict(pitch=70., yaw=0., roll=0.),
                       dict(pitch=float("nan"), yaw=0., roll=0.)):
            self.now += .1
            self.assertEqual(self.tracker.update(self.now, angles)["nod_count"], 0)

    def test_old_cycles_expire_without_a_new_nod(self):
        self.calibrate(); self.nod(); self.nod()
        result = self.feed(seconds=20.5)
        self.assertEqual(result["nod_count"], 0)
        self.assertEqual(result["state"], "NEUTRAL")

    def test_reacquisition_spike_is_not_a_nod_and_requires_a_neutral_interval(self):
        self.calibrate(); self.nod(); self.nod()
        self.now += .1
        self.tracker.update(self.now, None)
        self.assertEqual(self.feed(17., .7)["state"], "REACQUIRING")
        self.assertEqual(self.feed(0., .5)["state"], "REACQUIRING")
        self.assertEqual(self.feed(0., .7)["state"], "NEUTRAL")
        self.assertEqual(self.tracker.snapshot("NEUTRAL")["nod_count"], 0)
        self.assertEqual(self.nod()["nod_count"], 1)

    def test_analysis_excludes_gaps_and_does_not_count_nods_inherited_from_prep(self):
        from analyze_head_trial import summarize
        def row(t, stage, count):
            return dict(elapsed_monotonic=t, phase_stage=stage, signals={"head_motion":dict(
                state="REPEATED_NODS", available=True, nod_count=count, pitch_deg=2.)})
        result = summarize(dict(phase="NOD_OPEN", attempt=1, rows=[row(0, "PREP", 2),
            row(.1, "MEASURING", 2), row(.3, "MEASURING", 3), row(1.1, "MEASURING", 4)]))
        self.assertEqual(result["new_cycles_during_measuring"], 1)
        self.assertAlmostEqual(result["gap_seconds_not_scored"], .8)
        self.assertAlmostEqual(result["head_state_seconds"]["REPEATED_NODS"], .2)
        self.assertFalse(result["finished"])


if __name__ == "__main__":
    unittest.main()
