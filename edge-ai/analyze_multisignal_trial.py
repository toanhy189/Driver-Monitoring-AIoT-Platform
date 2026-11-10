"""Summarize requested action trials without calling frame counts accuracy."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np


def split_attempts(rows):
    result=[];current=None;previous_elapsed=None
    for row in rows:
        phase=row.get('phase','IDLE');elapsed=row.get('phase_elapsed_s')
        if phase=='IDLE':continue
        restarted=(elapsed is not None and previous_elapsed is not None and elapsed < previous_elapsed-1.)
        if current is None or phase!=current['phase'] or restarted:
            current={'phase':phase,'attempt':1+sum(x['phase']==phase for x in result),'rows':[]}
            result.append(current)
        current['rows'].append(row);previous_elapsed=elapsed
    return result


def summarize(attempt):
    rows=[x for x in attempt['rows'] if x['phase_stage']=='MEASURING']
    counts={key:Counter() for key in ('raw_state','confirmed_state','reason')}
    times={key:Counter() for key in counts}
    missing_time=0.
    for first,second in zip(attempt['rows'],attempt['rows'][1:]):
        if first['phase_stage']!='MEASURING':continue
        dt=second['elapsed_monotonic']-first['elapsed_monotonic']
        if dt<=0:continue
        # Report dropped wall time separately; never label a long missing span attentive.
        if dt>.5:missing_time+=dt;continue
        for key in times:times[key][first[key]]+=dt
    for row in rows:
        for key in counts:counts[key][row[key]]+=1
    def percentiles(getter):
        values=[getter(row) for row in rows];values=[x for x in values if x is not None and np.isfinite(x)]
        return dict(zip(('p10','median','p90'),[float(x) for x in np.percentile(values,[10,50,90])])) if values else None
    return {'phase':attempt['phase'],'attempt':attempt['attempt'],'measured_frames':len(rows),
        'measurement_completed':any(x['phase_stage']=='DONE' for x in attempt['rows']),
        'counts':counts,'observed_seconds':times,'gap_seconds_not_scored':missing_time,
        'ear':percentiles(lambda x:x.get('ear_raw')),
        'eye_sleepy_before_gate':percentiles(lambda x:(x['regions'].get('eye_probabilities') or [None,None])[1]),
        'eye_confidence':percentiles(lambda x:x['regions'].get('eye_confidence')),
        'mouth_yawn_before_gate':percentiles(lambda x:(x['regions'].get('mouth_probabilities') or [None,None])[1]),
        'mar':percentiles(lambda x:x['signals'].get('mar')),
        'fusion_score':percentiles(lambda x:x['signals'].get('fusion_score')),
        'binary_closed_score':percentiles(lambda x:min(x['binary_eye_shadow']['closed_scores'])
            if x.get('binary_eye_shadow') and x['binary_eye_shadow']['closed_scores']
            and all(v is not None for v in x['binary_eye_shadow']['closed_scores']) else None),
        'frame_gap_ms':percentiles(lambda x:x.get('frame_gap_ms'))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial',type=Path)
    args=parser.parse_args()
    rows=[]
    with (args.trial/'observations.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:pass  # The final row can be mid-write during a live read.
    report={'trial':str(args.trial),'metadata':json.loads((args.trial/'trial.json').read_text(encoding='utf-8')),
        'attempts':[summarize(x) for x in split_attempts(rows)],
        'limits':['Requested actions need visual/user confirmation; no independently labeled final test.',
                  'Frame counts and repeated attempts are correlated, not accuracy.',
                  'Wall-time gaps over .5 seconds are reported separately, not filled with the prior state.',
                  'No threshold/model changes are chosen automatically by this report.']}
    (args.trial/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
