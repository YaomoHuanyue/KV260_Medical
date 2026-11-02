import argparse
import json
import time
from pathlib import Path
from .pipeline import prepare, load_prepared, choose_target, run_route, write_json


def main():
    parser=argparse.ArgumentParser(description="Standalone KV260 airway navigation (PS or custom PL)")
    parser.add_argument('--backend',choices=['ps','pl'],default='ps',help='Distance field backend for new extraction')
    parser.add_argument('--planner-backend',choices=['ps','pl'],default='ps',help='Path, smoothing and camera backend; PL requires route firmware')
    parser.add_argument("--airway",type=Path)
    parser.add_argument("--prepared",type=Path,help="Reuse extraction, do not recompute centerline")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--root-lps",type=float,nargs=3)
    target=parser.add_mutually_exclusive_group()
    target.add_argument("--lesion",type=Path)
    target.add_argument("--endpoint",type=int)
    target.add_argument("--target-lps",type=float,nargs=3)
    parser.add_argument("--lesion-index",type=int,default=0)
    parser.add_argument("--scope-diameter",type=float,default=1.0)
    parser.add_argument("--safety-margin",type=float,default=.2)
    parser.add_argument("--sample-mm",type=float,default=.5)
    parser.add_argument("--no-smooth",action="store_true")
    args=parser.parse_args()
    worker_start=time.perf_counter()
    if (args.airway is None)==(args.prepared is None):parser.error("Choose --airway or --prepared")
    if args.prepared is not None and args.root_lps is not None:parser.error("--root-lps requires new --airway extraction")
    has_target=any(x is not None for x in (args.lesion,args.endpoint,args.target_lps))
    session=None
    try:
        # One process keeps the same XRT context and BOs from EDT to routing.
        # Extraction without a PL route also supports the legacy EDT firmware.
        if has_target and args.planner_backend=='pl':
            from pl.route_runtime import RouteXRT,RoutePlanner
            session=RouteXRT()
        elif args.airway is not None and args.backend=='pl':
            from pl.runtime import XRTSession
            session=XRTSession()
        if args.airway is not None:
            c,_=prepare(args.airway,args.output,args.root_lps,backend=args.backend,session=session)
        else:c=load_prepared(args.prepared)
        if has_target:
            target_start=time.perf_counter()
            target=choose_target(c,args.lesion,args.lesion_index,args.endpoint,args.target_lps)
            target_seconds=time.perf_counter()-target_start
            planner=RoutePlanner(c,session) if args.planner_backend=='pl' else None
            report=run_route(c,target,args.output,planner=planner,scope_diameter_mm=args.scope_diameter,safety_margin_mm=args.safety_margin,
                sample_mm=args.sample_mm,smooth=not args.no_smooth)
            report["timing"].update(target_preparation_seconds=target_seconds,worker_compute_seconds=time.perf_counter()-worker_start)
            write_json(args.output/"route.json",report)
            print(json.dumps({k:report[k] for k in ("status","reason","length_mm","final_target_gap_mm","timing","peak_process_rss_mib")},ensure_ascii=False))
        else:print(json.dumps(c.metadata,ensure_ascii=False))
    finally:
        if session is not None:session.close()


if __name__=="__main__":main()
