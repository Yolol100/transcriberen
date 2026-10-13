"""Evidence-only outer grouping: 1,000 videos = two existing 500-video batches.

This module does NOT dispatch work, download source content, or certify review completion.
Each internal batch is authorized only by the existing verified_advance gate.
"""
from __future__ import annotations
import argparse
import json

SOURCE_TOTAL = 18875
INNER_SIZE = 500
OUTER_SIZE = 1000

class BatchPlanError(ValueError):
    pass

def plan_1000(total: int = SOURCE_TOTAL) -> list[dict]:
    if type(total) is not int or total != SOURCE_TOTAL:
        raise BatchPlanError('unexpected supplied v15 corpus count')
    result = []
    for group_idx, first in enumerate(range(0, total, OUTER_SIZE), 1):
        end = min(total, first + OUTER_SIZE)
        internal = []
        for offset in range(first, end, INNER_SIZE):
            idx = offset // INNER_SIZE + 1
            internal.append({'internal_batch': idx, 'video_count': min(INNER_SIZE, total-offset)})
        if sum(i['video_count'] for i in internal) != end-first:
            raise BatchPlanError('internal group mismatch')
        result.append({'group': group_idx, 'start_index_zero_based': first,
                       'end_index_exclusive': end, 'video_count': end-first,
                       'existing_500_video_batches': internal,
                       'status': 'planned_not_dispatched'})
    if (len(result) != 19 or sum(g['video_count'] for g in result) != total or
            sorted(i['internal_batch'] for g in result for i in g['existing_500_video_batches']) != list(range(1,39))):
        raise BatchPlanError('group coverage mismatch')
    return result

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--group', type=int, default=0, help='one-based group; 0 prints only summary')
    args=p.parse_args()
    groups=plan_1000()
    if args.group:
        if args.group not in range(1,len(groups)+1): p.error('group outside source count')
        print(json.dumps(groups[args.group-1],sort_keys=True))
    else:
        print(json.dumps({'groups':len(groups),'videos':SOURCE_TOTAL,'internal_batches':38,
                          'last_group_videos':groups[-1]['video_count'],
                          'status':'planned_not_dispatched'},sort_keys=True))

if __name__=='__main__': main()
