"""Manual independent scalar-field producer; never installs a UI scene."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
from .case_io import load_case, save_field
from .field import Quality, build


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ct', type=Path, required=True)
    p.add_argument('--segmentation', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', choices=['accepted_binary','network_probability'], default='accepted_binary')
    p.add_argument('--quality', choices=['high','ultra'], default='high')
    args=p.parse_args()
    image, identity=load_case(args.ct,args.segmentation,args.source)
    quality=Quality() if args.quality=='high' else replace(Quality(),
        surface_smoothing_sigma_mm=.5,surface_smoothing_strength=.72,axial_smoothing_sigma_mm=1,
        quantization_mm=1/64)
    report=save_field(args.output,build(image,quality),identity)
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':main()
