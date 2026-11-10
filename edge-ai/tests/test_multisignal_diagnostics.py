from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml.multisignal_features import MultisignalWindow
from service.multisignal_diagnostics import decision_reason


class DiagnosticsTests(unittest.TestCase):
    def model(self, eyes=True, crop=True, score=.1):
        return SimpleNamespace(failed=False, region_diagnostics={"eyes_crop_available":crop},
            window=SimpleNamespace(last_quality_reason="WARMUP"),
            telemetry_signals=lambda:{"eyes_available":eyes,"fusion_score":score})

    def test_separates_face_loss_frame_gap_and_unconfident_eyes(self):
        head={"valid":True,"calibrating":False}
        self.assertEqual(decision_reason(self.model(),False,head,"UNKNOWN"),"NO_FACE")
        self.assertEqual(decision_reason(self.model(),True,head,"ATTENTIVE",policy_gap=True),"FRAME_GAP")
        self.assertEqual(decision_reason(self.model(False),True,head,"UNKNOWN"),"EYES_LOW_CONFIDENCE")
        self.assertEqual(decision_reason(self.model(False,False),True,head,"UNKNOWN"),"EYES_CROP_UNAVAILABLE")

    def test_warmup_and_head_calibration_are_distinct(self):
        self.assertEqual(decision_reason(self.model(score=None),True,None,"UNKNOWN"),"FUSION_WARMUP")
        self.assertEqual(decision_reason(self.model(),True,{"valid":True,"calibrating":True},"UNKNOWN"),"HEAD_CALIBRATING")

    def test_quality_instrumentation_preserves_admission_and_exposes_low_coverage(self):
        w=MultisignalWindow()
        w.add(0,{})
        self.assertIsNone(w.snapshot());self.assertEqual(w.last_quality_reason,"WARMUP")
        for i in range(1,12):w.add(i*.2,{})
        self.assertIsNone(w.snapshot());self.assertEqual(w.last_quality_reason,"LOW_COVERAGE")
        self.assertEqual(w.last_coverage['eye_sleepy'],0)
        w.add(4.,{'eye_sleepy':.9})
        self.assertEqual(w.reset_count,1)
        self.assertIsNone(w.snapshot());self.assertEqual(w.last_quality_reason,"WARMUP")

    def test_analysis_keeps_repeated_action_attempts_separate(self):
        from analyze_multisignal_trial import split_attempts
        rows=[{'phase':'OPEN_NATURAL','phase_elapsed_s':x} for x in (0,1,2,-3,-2,0,1)]
        attempts=split_attempts(rows)
        self.assertEqual([x['attempt'] for x in attempts],[1,2])
        self.assertEqual([len(x['rows']) for x in attempts],[3,4])

    def test_analysis_does_not_fill_a_long_gap_with_attentive_time(self):
        from analyze_multisignal_trial import summarize
        def row(t):return {'elapsed_monotonic':t,'phase_stage':'MEASURING',
            'raw_state':'ATTENTIVE','confirmed_state':'ATTENTIVE','reason':'OK',
            'regions':{},'signals':{}}
        result=summarize({'phase':'OPEN_NATURAL','attempt':1,'rows':[row(0),row(.2),row(1.2)]})
        self.assertAlmostEqual(result['observed_seconds']['confirmed_state']['ATTENTIVE'],.2)
        self.assertAlmostEqual(result['gap_seconds_not_scored'],1.)

    def test_binary_shadow_analysis_keeps_missing_scores_out_of_statistics(self):
        from analyze_multisignal_trial import summarize
        def row(t, scores):
            return {'elapsed_monotonic':t,'phase_stage':'MEASURING','raw_state':'UNKNOWN',
                'confirmed_state':'UNKNOWN','reason':'WARMUP','regions':{},'signals':{},
                'binary_eye_shadow':{'closed_scores':scores,'used_for_policy':False}}
        rows = [row(0,[None,.9]),row(.2,[.8,.9]),row(.4,[.6,.7])]
        report=summarize({'phase':'CLOSED','attempt':1,'rows':rows})
        self.assertAlmostEqual(report['binary_closed_score']['median'],.7)
        self.assertEqual(report['counts']['raw_state'],{'UNKNOWN':3})


if __name__=='__main__':unittest.main()
