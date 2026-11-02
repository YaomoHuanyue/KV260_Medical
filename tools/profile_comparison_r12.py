"""Measure remaining complete report work after the isolated PS/PL trial ends."""
from pathlib import Path
import cProfile,json,pstats,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from modules.surface_route.comparison_r12 import Comparison
from modules.surface_route.comparison_r11 import solve_all
from modules.surface_route.own_CT_comparison_r12 import verify_sources,semantic
from modules.surface_route.bundle_r8 import sha,write_json,arrays
from profile_session_r2 import ProfilePS


def main():
    closure=verify_sources();result=ROOT/'modules/surface_route/results/comparison_own_CT_ARM_r12'
    proof=json.loads((result/'acceptance.json').read_text());assert proof['full_static_1MiB_echo_and_C6_restore_passed']
    started=json.loads((ROOT/'modules/surface_route/results/comparison_trial_ARM_r12_started.json').read_text())
    assert not Path('/proc',str(started['PID'])).exists()
    output=ROOT/'modules/surface_route/results/comparison_profile_ARM_r12';output.mkdir(exist_ok=False)
    label='network_probability_high_ported'
    comp=Comparison.from_bundle(ROOT/'modules/surface_route/results/complete_bundles_ARM_r8'/(label+'_bend_1p0'),
        ROOT/'ui/runs/20261004_151324_f601e259',ROOT/'fixtures/own_ct/CT-chest.nrrd',native=True)
    q=comp.queries([1.,1.2,1.8,2.8,4.],.3);cpu=ProfilePS()
    values=solve_all(q,lambda g,d,m,w:cpu.solve(g,d,m,w,4)[1:])
    profiler=cProfile.Profile();profiler.enable()
    whole,alternative,saved=comp.produce(q,*values,minimum_bend_radius_mm=1.)
    profiler.disable();profiler.dump_stats(str(output/'report.prof'))
    for name,actual in [('whole_instrument_profiles.json',whole),('whole_alternative_routes.json',alternative)]:
        expected=json.loads((result/label/name).read_text());assert semantic(actual)==semantic(expected),name
    expected=arrays(result/label/'whole_comparison_arrays.npz');assert set(saved)==set(expected)
    for name in saved:np.testing.assert_array_equal(saved[name],expected[name],err_msg=name)
    stats=pstats.Stats(profiler);rows=[]
    for (file,line,name),(primitive,calls,own,cumulative,callers) in stats.stats.items():
        rows.append(dict(file=file,line=line,function=name,primitive_calls=primitive,calls=calls,
            self_seconds=own,cumulative_seconds=cumulative))
    rows.sort(key=lambda row:row['cumulative_seconds'],reverse=True)
    write_json(output/'acceptance.json',dict(status='actual_complete_report_profiled_with_full_output_equivalence',
        label=label,top_cumulative=rows[:60],top_self=sorted(rows,key=lambda r:r['self_seconds'],reverse=True)[:40],
        profiled_seconds=stats.total_tt,profiler_overhead_included=True,
        source_closure_sha256=closure,profiler_source_sha256=sha(Path(__file__)),
        raw_profile_sha256=sha(output/'report.prof'),PL_access=False,new_bitstream=False,production_promoted=False))
    print(json.dumps(rows[:12],indent=2),flush=True)


if __name__=='__main__':main()
