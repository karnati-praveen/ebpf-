#!/usr/bin/env python3
"""Export only completed voluntary migration observations from calibration runs."""
import argparse
import json
import math
from pathlib import Path


def export(identity, directories):
    retained={}
    for directory in directories:
        manifest_path=directory/'manifest.json'
        if not manifest_path.exists():raise ValueError('calibration campaign manifest required')
        manifest=json.loads(manifest_path.read_text())
        if manifest.get('phase')!='calibration' or manifest.get('identity')!=identity:
            raise ValueError('calibration data must be held out and fingerprint-compatible')
        for path in directory.rglob('migrations.json'):
            for row in json.loads(path.read_text()):
                if row.get('status')!='complete' or row.get('cause')!='voluntary' or not row.get('calibration_eligible'):
                    continue
                ratio=row.get('observed_to_predicted_ratio',0)
                if not math.isfinite(ratio) or ratio<=0:raise ValueError('invalid observed ratio')
                key=row['transition_id']
                observation={k:row[k] for k in ('transition_id','cause','status','calibration_eligible','observed_to_predicted_ratio')}
                if key in retained and retained[key]!=observation:raise ValueError('conflicting duplicate transition')
                retained[key]=observation
    if len(retained)<10:raise ValueError('at least ten independent completed voluntary transitions required')
    return {'identity':identity,'observations':list(retained.values())[-128:]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('directories',type=Path,nargs='+')
    args=parser.parse_args()
    result=export(json.loads(args.identity.read_text()),args.directories)
    if args.out.exists():raise ValueError('refusing to overwrite calibration artifact')
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(f"Saved {len(result['observations'])} voluntary calibration observations")


if __name__=='__main__':main()
