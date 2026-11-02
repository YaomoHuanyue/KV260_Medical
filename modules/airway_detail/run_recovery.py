"""Run the independent review producer inside a self-contained system result."""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.airway_detail.case_io import load_inputs, save_outputs, sha
from modules.airway_detail.recovery import recover_distal_components


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--segmentation', type=Path, required=True)
    p.add_argument('--lesion-index', type=int, default=0)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output, source = a.output.resolve(), a.segmentation.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Review outputs must be separate from the segmentation')
    if output.exists():
        raise FileExistsError('Output already exists')
    begin = time.perf_counter()
    image, ct, airway, lesion, probability, identity = load_inputs(a.input, source, a.lesion_index)
    result = recover_distal_components(airway, ct, lesion, image.GetSpacing(), probability)
    files = ['__init__.py', 'evidence.py', 'recovery.py', 'case_io.py', 'run_recovery.py']
    report = save_outputs(output, image, result, identity, time.perf_counter() - begin,
                          {f: sha(Path(__file__).parent / f) for f in files})
    print(json.dumps({k: report[k] for k in ['status', 'backend', 'algorithm_seconds', 'summary']}), flush=True)


if __name__ == '__main__':
    main()
