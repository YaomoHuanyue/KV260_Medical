"""Same active C1 surface, complete raw graph, PS1/PS4 and physical R4 comparison."""
from pathlib import Path
import argparse, json, os, sys, traceback
from time import perf_counter
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.comparison_r12 import Comparison
from modules.surface_route.comparison_r11 import solve_all
from modules.surface_route.bundle_r8 import sha, write_json
from modules.surface_route.test_comparison_r11 import heap_oracle, verify_native_model
from profile_session_r2 import ProfilePS

LABELS=('accepted_binary_high_ported','accepted_binary_ultra_ported',
        'network_probability_high_ported','network_probability_ultra_ported')


def semantic(value):
    if isinstance(value,dict):
        return {k:semantic(v) for k,v in value.items() if not k.endswith('_seconds') and k not in ('exact_wall_query_reuse','root_winding_query_reuse')}
    if isinstance(value,list):return [semantic(v) for v in value]
    return value


def verify_sources():
    manifest=ROOT/'modules/surface_route/comparison_source_closure_r12.json'
    doc=json.loads(manifest.read_text())
    for name,expected in doc['files_sha256'].items():assert sha(ROOT/name)==expected,name
    parent=ROOT/doc['sealed_parent_closure'];assert sha(parent)==doc['sealed_parent_closure_sha256']
    for name,expected in json.loads(parent.read_text())['files_sha256'].items():assert sha(ROOT/name)==expected,name
    proof=json.loads((ROOT/'modules/navigation_comparison/results/profile_ARM_r1.json').read_text())
    library=ROOT/'modules/navigation_comparison/build'/('profile_ps_r1.dll' if os.name=='nt' else 'libprofile_ps_r1.so')
    if os.name!='nt':assert sha(library)==proof['library_sha256']
    for name,expected in proof['source_sha256'].items():assert sha(ROOT/'modules/navigation_comparison'/name)==expected,name
    return sha(manifest)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--actual-PL',action='store_true');ap.add_argument('--label',choices=LABELS,action='append')
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args();assert 1<=args.repeats<=9 and not args.output.exists()
    platform='Windows' if os.name=='nt' else 'ARM'
    closure=verify_sources();model,model_sha=verify_native_model();cpu=ProfilePS()
    if args.actual_PL and platform!='ARM':raise ValueError('Physical PL trial requires ARM')
    output=args.output.resolve();assert output.is_relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=False)
    before={p:sha(ROOT/p) for p in ('ui/active_release.json','ui/run.sh','dfx/surface_quality/release/manifest.json')}
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip() if platform=='ARM' else None
    marker=Path('/run/kv260-dfx-medical-loaded.sha256').read_text() if platform=='ARM' else None
    session=None;rows=[];start=perf_counter()
    try:
        if args.actual_PL:
            fw=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes()
            assert fw.rstrip(b'\0')==b'dfx_medical.bin'
            path=ROOT/'dfx/navigation_profile';sys.path.insert(0,str(path))
            from runtime_r4 import Session as R4Session
            from protocol_host_r1 import HostCodec,HostCompleteChecks
            class Session(HostCompleteChecks,R4Session):pass
            session=Session();session.host_codec=HostCodec()
            before_session=perf_counter();session.__enter__();cold_session=perf_counter()-before_session
        for label in args.label or LABELS:
            print('PREPARE',label,flush=True)
            folder=output/label;folder.mkdir()
            bundle=ROOT/f'modules/surface_route/results/complete_bundles_{platform}_r8'/(label+'_bend_1p0')
            comp=Comparison.from_bundle(bundle,ROOT/'ui/runs/20261004_151324_f601e259',
                ROOT/'fixtures/own_ct/CT-chest.nrrd',native=platform=='ARM')
            q=comp.queries([1.,1.2,1.8,2.8,4.],.3)
            expected=solve_all(q,heap_oracle)
            for values in (solve_all(q,model.solve),solve_all(q,lambda g,d,m,w:cpu.solve(g,d,m,w,4)[1:])):
                for a,b in zip(values,expected):np.testing.assert_array_equal(a,b)
            cold={}
            if session is not None:
                at=len(session.calls);now=perf_counter();values=solve_all(q,session.solve)
                cold=dict(seconds=perf_counter()-now,calls=session.calls[at:])
                for a,b in zip(values,expected):np.testing.assert_array_equal(a,b)
            print('EXACT_COSTS',label,'raw_edges',len(comp.edges),flush=True)
            baseline=None;reference_arrays=None;samples=[]
            providers={'PS1':lambda g,d,m,w:cpu.solve(g,d,m,w,1)[1:],
                       'PS4':lambda g,d,m,w:cpu.solve(g,d,m,w,4)[1:]}
            if session is not None:providers['PL_R4']=session.solve
            for repeat in range(args.repeats):
                order=list(providers)
                if repeat%2:order.reverse()
                sample=dict(repeat=repeat,order=order,providers={})
                for name in order:
                    at=len(session.calls) if session else 0
                    now=perf_counter();values=solve_all(q,providers[name]);solve_seconds=perf_counter()-now
                    for a,b in zip(values,expected):np.testing.assert_array_equal(a,b)
                    whole,alternative,arrays=comp.produce(q,*values,minimum_bend_radius_mm=1.)
                    elapsed=perf_counter()-now
                    current=(semantic(whole),semantic(alternative))
                    if baseline is None:
                        baseline=current;reference_arrays=arrays
                        write_json(folder/'whole_instrument_profiles.json',whole)
                        write_json(folder/'whole_alternative_routes.json',alternative)
                        np.savez_compressed(folder/'whole_comparison_arrays.npz',**arrays)
                        write_json(folder/'prepared_input.json',dict(binding=comp.binding,
                            queries=[dict(diameter_mm=x.diameter,required_mm=x.required,threshold_mm=x.threshold,
                                root_passed=x.root_passed,edge_review=x.edge_report) for x in q],
                            geometry_preparation_seconds=comp.preparation_seconds,
                            query_geometry_preparation_seconds=comp.query_preparation_seconds,
                            wall_queries=comp.memo.metrics(),raw_nodes=len(comp.radii),raw_edges=len(comp.edges)))
                    else:
                        assert current==baseline,'Whole profiles or candidates differ: '+name
                        assert set(arrays)==set(reference_arrays)
                        for key in arrays:np.testing.assert_array_equal(arrays[key],reference_arrays[key],err_msg=key)
                    sample['providers'][name]=dict(solve_API_seconds=solve_seconds,full_report_API_seconds=elapsed,
                        candidate_and_report_seconds=alternative['candidate_and_report_seconds'],
                        wall_queries=alternative['exact_wall_query_reuse'],
                        PL_calls=session.calls[at:] if session and name=='PL_R4' else [])
                    print('FULL_REPORT',label,repeat,name,round(elapsed,4),flush=True)
                samples.append(sample)
            median={name:dict(solve_API_seconds=float(np.median([s['providers'][name]['solve_API_seconds'] for s in samples])),
                full_report_API_seconds=float(np.median([s['providers'][name]['full_report_API_seconds'] for s in samples]))) for name in providers}
            ps_name=min(('PS1','PS4'),key=lambda name:median[name]['full_report_API_seconds'])
            row=dict(label=label,binding=comp.binding,raw_nodes=len(comp.radii),raw_edges=len(comp.edges),
                original_forest_edges=len(comp.c.edges),candidate_counts=[g['candidate_count'] for g in baseline[1]['groups']],
                Pareto_counts=[len(g['pareto']) for g in baseline[1]['groups']],
                all_FP64_costs_parents_profiles_candidates_and_path_arrays_exact=True,samples=samples,medians=median,
                strongest_full_API_PS=ps_name,cold_PL=cold,
                files_sha256={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            if session is not None:
                row.update(PL_over_strongest_PS_full_API_speedup=median[ps_name]['full_report_API_seconds']/median['PL_R4']['full_report_API_seconds'],
                    PL_over_strongest_PS_solve_API_speedup=min(median['PS1']['solve_API_seconds'],median['PS4']['solve_API_seconds'])/median['PL_R4']['solve_API_seconds'])
            write_json(folder/'report.json',row);rows.append(row)
        if session is not None:session.__exit__(None,None,None);session=None
        assert before=={p:sha(ROOT/p) for p in before}
        if platform=='ARM':
            assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            assert marker==Path('/run/kv260-dfx-medical-loaded.sha256').read_text()
        if platform=='ARM':
            import resource
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        else:peak=None
        proof=dict(status='actual_surface_complete_original_graph_same_input_comparison_passed',platform=platform,
            cases=rows,PL_access=args.actual_PL,full_static_1MiB_echo_and_C6_restore_passed=bool(args.actual_PL),
            cold_session_seconds=cold_session if args.actual_PL else None,boot_id=boot,
            source_closure_sha256=closure,R4_C_model_sha256=model_sha,peak_test_process_RSS_MiB=peak,
            total_trial_seconds=perf_counter()-start,production_promoted=False,new_bitstream=False,
            performance_scope='Fresh solve plus complete all-node candidate, actual continuous-wall review and full report API; includes copies, guards and checks; excludes common geometry preparation and file serialization, recorded separately',
            further_UI_and_selected_route_integration_pending=True)
        write_json(output/'acceptance.json',proof);print(proof['status'],flush=True)
    except BaseException as error:
        write_json(output/'failure.json',dict(status='trial_failed',error=str(error),cases=rows,traceback=traceback.format_exc()))
        raise
    finally:
        if session is not None:session.__exit__(None,None,None)


if __name__=='__main__':main()
