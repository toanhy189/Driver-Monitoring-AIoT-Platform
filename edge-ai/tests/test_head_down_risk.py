from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.head_down_risk import HeadDownRisk,model_identity


def motion(pitch=15.,yaw=0.,roll=0.,state="LOWERED"):
    return dict(available=True,calibrated=True,state=state,pitch_deg=pitch,yaw_deg=yaw,roll_deg=roll)


class PostureTests(unittest.TestCase):
    def active(self):
        policy=HeadDownRisk()
        for i in range(32):result=policy.update(i*.1,motion())
        self.assertTrue(result["risk_candidate"])
        return policy

    def test_brief_downward_looks_do_not_add_across_recovery(self):
        policy=HeadDownRisk()
        for i in range(100):
            self.assertFalse(policy.update(i*.1,motion(15. if i%30<20 else 0.))["risk_candidate"])

    def test_three_second_downward_posture_triggers_without_eye_measurements(self):
        policy=HeadDownRisk()
        for i in range(30):self.assertFalse(policy.update(i*.1,motion())["risk_candidate"])
        self.assertTrue(policy.update(3.,motion())["risk_candidate"])
        self.assertEqual(policy.snapshot("DOWN_RISK",3.)["version"],"sustained-head-down-v1")

    def test_side_turn_extreme_pose_and_missing_face_reset_risk(self):
        for bad in (None,motion(yaw=30.),motion(roll=25.),motion(50.),motion(state="OUT_OF_RANGE"),motion(pitch=float("nan"))):
            policy=self.active()
            result=policy.update(3.2,bad)
            self.assertFalse(result["risk_candidate"])
            self.assertEqual(result["observed_down_seconds"],0.)

    def test_timestamp_gap_and_backwards_time_never_continue_old_duration(self):
        for t in (5.,2.):
            policy=self.active()
            self.assertFalse(policy.update(t,motion())["risk_candidate"])
            self.assertFalse(policy.update(t+.1,motion())["risk_candidate"])

    def test_near_threshold_does_not_chatter_but_recovery_requires_current_observation(self):
        policy=self.active()
        self.assertTrue(policy.update(3.2,motion(10.))["risk_candidate"])
        self.assertEqual(policy.update(3.3,motion(0.))["state"],"RECOVERING")
        self.assertFalse(policy.update(3.4,None)["risk_candidate"])
        policy=self.active()
        for i in range(32,39):result=policy.update(i*.1,motion(0.))
        self.assertFalse(result["risk_candidate"])
        self.assertEqual(result["state"],"NORMAL")

    def test_nod_rearming_does_not_block_new_current_posture_duration(self):
        policy=HeadDownRisk()
        for i in range(32):result=policy.update(i*.1,motion(state="REACQUIRING"))
        self.assertTrue(result["risk_candidate"])

    def test_version_separates_posture_policy_from_frozen_eye_model(self):
        self.assertEqual(model_identity("base"),model_identity("base"))
        self.assertNotEqual(model_identity("base"),model_identity("other"))
        self.assertTrue(model_identity("base").startswith("eye-mouth-v2-posture-"))


if __name__=="__main__":unittest.main()
