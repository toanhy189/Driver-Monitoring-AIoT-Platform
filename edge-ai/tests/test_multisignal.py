from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml.multisignal_data import LABELS, parse_auxiliary
from ml.multisignal_features import FEATURE_NAMES, MultisignalWindow, window_label
from ml.multisignal_runtime import MultisignalModel, fused_state
from ml.regions import mouth_aspect_ratio, extract_regions


class MultisignalTests(unittest.TestCase):
    def test_yawdd_class_is_file_content_and_not_the_constant_filename_suffix(self):
        from ml.yawdd_diagnostic import read_labels,PREFIX
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/"annotations.zip"
            with zipfile.ZipFile(archive,"w") as output:
                output.writestr(PREFIX+"00000000_0.txt","1 0.5 0.5 0.2 0.2\n")
                output.writestr(PREFIX+"00000001_0.txt","0 0.5 0.5 0.2 0.2\n")
            self.assertEqual(read_labels(archive),{0:1,1:0})

    def face(self):
        points=[SimpleNamespace(x=.5,y=.5) for _ in range(478)]
        for index,x,y in ((13,.5,.65),(14,.5,.75),(61,.35,.7),(291,.65,.7),
            (0,.5,.64),(17,.5,.76),(78,.4,.7),(308,.6,.7),
            (33,.25,.3),(133,.4,.3),(159,.33,.28),(145,.33,.32),
            (362,.6,.3),(263,.75,.3),(386,.67,.28),(374,.67,.32)):
            points[index]=SimpleNamespace(x=x,y=y)
        return points

    def test_mar_is_scale_invariant_and_not_a_yawn_decision(self):
        face=self.face()
        self.assertAlmostEqual(mouth_aspect_ratio(face,(1000,1000)),1/3)
        self.assertAlmostEqual(mouth_aspect_ratio(face,(500,500)),1/3)
        face[291]=face[61]
        self.assertIsNone(mouth_aspect_ratio(face,(1000,1000)))

    def test_mouth_survives_unusable_eye_crop(self):
        noise=np.random.default_rng(1).integers(0,255,(1000,1000,3),dtype=np.uint8)
        face=self.face()
        for index in (33,133,159,145,362,263,386,374):
            face[index]=SimpleNamespace(x=.5,y=.3)
        regions=extract_regions(noise,face)
        self.assertIsNone(regions["eyes"])
        self.assertEqual(regions["mouth"].shape,(96,96,3))

    def test_auxiliary_labels_keep_original_semantics(self):
        self.assertEqual(parse_auxiliary(b"0 1\n2", "mouth"),"012")
        self.assertEqual(LABELS["mouth"]["2"],"TALKING_LAUGHING")
        self.assertEqual(LABELS["eye"]["1"],"SLEEPY")
        with self.assertRaises(ValueError):
            parse_auxiliary(b"012", "eye")

    def test_missing_eyes_do_not_block_valid_mouth_history(self):
        window=MultisignalWindow()
        for now in np.arange(0,2.41,.2):
            window.add(float(now),{"mouth_yawn":.8,"mouth_talk":.1,"mar":.5})
        snapshot=window.snapshot()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["coverage"]["eye_sleepy_coverage"],0)
        self.assertAlmostEqual(snapshot["coverage"]["mouth_yawn_coverage"],1)
        self.assertEqual(len(snapshot["features"]),len(FEATURE_NAMES))
        window.add(4.,{"mouth_yawn":.8})
        self.assertIsNone(window.snapshot())

    def test_no_attentive_from_mouth_only_or_missing_pose(self):
        front={"valid":True,"calibrating":False,"is_distracted":False}
        self.assertEqual(fused_state(0,front,eyes_available=False,mouth_yawn=.01),"UNKNOWN")
        self.assertEqual(fused_state(0,front,eyes_available=True),"ATTENTIVE")
        self.assertEqual(fused_state(0,None,eyes_available=True),"UNKNOWN")
        self.assertEqual(fused_state(1,front,eyes_available=False,mouth_yawn=.1),"UNKNOWN")
        self.assertEqual(fused_state(1,front,eyes_available=False,mouth_yawn=.8),"DROWSY")
        self.assertEqual(fused_state(None,{**front,"is_distracted":True}),"DISTRACTED")

    def test_mixed_ground_truth_windows_not_relabelled_from_mar(self):
        rows=[{"time_s":i*.2,"drowsiness":i%2} for i in range(12)]
        self.assertIsNone(window_label(rows,0,2))
        self.assertEqual(window_label([{**row,"drowsiness":1} for row in rows],0,2),1)

    def test_lost_face_invalidates_cached_positive_immediately(self):
        model=MultisignalModel.__new__(MultisignalModel)
        model.failed=False;model.previous=1.;model.window=MultisignalWindow()
        model.last_score=.9
        model.signals={"_observed":1.,"_prediction":1,"eyes_available":True,"yawn_probability":.9}
        self.assertEqual(model.observe(None,None,1.01),"UNKNOWN")
        self.assertFalse(model.telemetry_signals()["eyes_available"])
        self.assertIsNone(model.last_score)
        self.assertNotIn("_prediction",model.telemetry_signals())

    def test_main_keeps_mouth_when_ear_and_pose_are_unavailable(self):
        import main as app
        frame=np.zeros((32,32,3),dtype=np.uint8)
        camera=Mock();camera.isOpened.return_value=True;camera.read.return_value=(True,frame)
        signals={"schema_version":"eye-mouth-v1","mar":.4,"mouth_state":"YAWN","eye_state":"UNKNOWN",
                 "mouth_available":True,"eyes_available":False,"yawn_probability":.8,"experimental":True}
        model=SimpleNamespace(model_version="eye-mouth-test",observe=Mock(return_value="UNKNOWN"),
            telemetry_signals=Mock(return_value=signals),last_inference_ms=1.,last_score=None)
        with patch("ml.multisignal_runtime.MultisignalModel",return_value=model), \
                patch.object(app,"AI_MODEL_MODE","multisignal"),patch.object(app,"init_db",return_value=True), \
                patch.object(app,"VideoUploadWorker"),patch.object(app,"LocalAlertWorker"), \
                patch.object(app.cv2,"VideoCapture",return_value=camera),patch.object(app.cv2,"imshow"), \
                patch.object(app.cv2,"destroyAllWindows"),patch.object(app.cv2,"waitKey",return_value=ord("q")), \
                patch.object(app,"FaceLandmarkDetector") as detector, \
                patch.object(app,"calculate_average_ear",return_value=float("nan")), \
                patch.object(app,"HeadPoseEstimator") as head,patch.object(app,"MQTTClient"), \
                patch.object(app,"create_video_writer",return_value=(None,None)), \
                patch.object(app,"publish_event"),patch.object(app,"RuntimeMetrics"), \
                patch.object(app,"EyeClosureGuard") as guard,patch.object(app,"publish_telemetry") as publish:
            detector.return_value.process.return_value=[[None]]
            head.return_value.estimate.return_value=None
            app.main()
        self.assertEqual(model.observe.call_args.args[1],[None])
        self.assertIsNone(model.observe.call_args.args[3])
        self.assertIsNone(model.observe.call_args.args[4])
        self.assertTrue(publish.call_args.kwargs["face_detected"])
        self.assertEqual(publish.call_args.kwargs["state_data"]["ai_signals"],signals)
        guard.assert_not_called()
        camera.release.assert_called_once()

    def test_full_video_replay_counts_missing_positive_intervals_as_missed(self):
        from ml.multisignal_evaluate import replay,aggregate
        rows=[{"time_s":round(i*.2,2),"drowsiness":1} for i in range(36)]
        report={"video_id":"missing-test","condition":"glasses","group":"validation","samples":rows}
        manifest={"window_seconds":5.,"min_history_seconds":2.,"max_gap_seconds":.5,
                  "model_version":"test","eye_confidence_threshold":.6,"mouth_confidence_threshold":.6}
        estimator=Mock();estimator.predict_proba.side_effect=lambda rows:np.tile([[0.,1.]],(len(rows),1))
        result=aggregate([replay(report,manifest,{"estimator":estimator,"threshold":.5})])
        self.assertEqual(result["eligible_intervals"],1)
        self.assertEqual(result["missed_intervals"],1)
        self.assertEqual(result["unknown_fraction"],1.)
        self.assertEqual(result["positive_time_recall"],0.)
        estimator.predict_proba.assert_not_called()
        # With continuously observable positive scores, the actual policy still
        # waits for temporal history, candidate confirmation and its 3s timer.
        for row in rows:
            row.update(eyes_path="synthetic",eye_confidence=.9,eye_sleepy=.9,ear=.1,yaw=0.,pitch=.1)
        result=replay(report,manifest,{"estimator":estimator,"threshold":.5})
        self.assertEqual(result["detected_intervals"],1)
        self.assertGreaterEqual(result["delay_seconds"][0],5.5)
        self.assertLessEqual(result["delay_seconds"][0],6.)


if __name__=="__main__":
    unittest.main()
