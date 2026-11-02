"""Real CT, four immutable fields, full selected path, checked prefix and root-only."""
from pathlib import Path
import argparse,json,os,sys,traceback
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.surface_actions_r13 import Comparison,prepare_comparison,prepare_selected,verify_sources,COMPARISON_FILES
from modules.surface_route.bundle_r8 import arrays,sha,write_json
from modules.surface_route.bundle_reader_r9 import verify_bundle
from modules.surface_route.selected_surface_r13 import selected_source,selected_node_arcs,forest_for_path
from modules.surface_route.scene_runtime_r9 import SceneSnapshot

LABELS=('accepted_binary_high_ported','accepted_binary_ultra_ported',
        'network_probability_high_ported','network_probability_ultra_ported')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    output=a.output.resolve();assert output.is_relative_to(ROOT) and not output.exists();output.mkdir(parents=True)
    closure=verify_sources();platform='Windows' if os.name=='nt' else 'ARM';rows=[]
    defaults={n:sha(ROOT/n) for n in ('ui/active_release.json','ui/run.sh','dfx/surface_quality/release/manifest.json')}
    try:
        for label in LABELS:
            parent=ROOT/f'modules/surface_route/results/complete_bundles_{platform}_r8'/(label+'_bend_1p0')
            comp=Comparison.from_bundle(parent,ROOT/'ui/runs/20261004_151324_f601e259',ROOT/'fixtures/own_ct/CT-chest.nrrd',native=platform=='ARM')
            folder=output/label;folder.mkdir()
            prepare_comparison(comp,folder/'comparison',bend=0.)
            alt=json.loads((folder/'comparison/whole_alternative_routes.json').read_text(encoding='utf-8'))
            group=next(i for i,g in enumerate(alt['groups']) if g['scope_diameter_mm']==1.8)
            visible={p['candidate_id'] for p in alt['groups'][group]['pareto']}
            candidate=max((p for p in alt['groups'][group]['candidates'] if p['candidate_id'] in visible),key=lambda p:p['path_length_mm'])['candidate_id']
            def selected(name,comparison,g,c,expected):
                p,ids,u,options,binding=selected_source(comp,comparison,g,c)
                row=prepare_selected(comp,parent,comparison,g,c,folder/name)
                meta=verify_bundle(folder/name);route=arrays(folder/name/'route.npz');camera=arrays(folder/name/'camera.npz')
                report=json.loads((folder/name/'route.json').read_text(encoding='utf-8'))
                assert report['selection']==binding and not report['branch_guidance_application_pending']
                assert not report['automatic_route_replanning'] and report['bend_constraint_passed']
                assert meta['renderer_scalar_sha256']==comp.field.sha256 and meta['identity']['mesh_proof']==comp_binding['identity']['mesh_proof']
                assert np.all(route['bend_radius_mm']+1e-5>=options['minimum_bend_radius_mm'])
                context,_=forest_for_path(comp,ids);selected_node_arcs(context,route)
                snapshot=SceneSnapshot(folder/name);assert snapshot.revision==meta['revision']
                if expected=='full':
                    assert np.array_equal(route['points_lps_mm'][[0,-1]],p[[0,-1]])
                    assert len(route['arc_mm'])>2 and row['available_branch_events']>0
                    event=next(e for e in snapshot.guidance['events'] if e['available'])
                    distance=float(event['junction_arc_mm']);pose=snapshot.pose(distance,17.,-6.)
                    request=dict(revision=snapshot.revision,width=640,height=363,sequence=1,arc_mm=distance,
                        camera=pose['position_lps_mm'],forward=pose['forward_lps'],up=pose['up_lps'])
                    plan=snapshot.frame_plan(request);assert plan['branch_event']==event['id']
                    write_json(folder/(name+'_manual_request.json'),request)
                elif expected=='prefix':assert route['arc_mm'][-1]<np.linalg.norm(np.diff(p,axis=0),axis=1).sum()
                elif expected=='root':
                    assert len(route['arc_mm'])==1 and not row['available_branch_events']
                    assert all(not len(v) for v in camera.values())
                row.update(label=label,kind=expected,bundle=str((folder/name).relative_to(ROOT)).replace('\\','/'),
                    bundle_metadata_sha256=sha(folder/name/'scene.json'),comparison_sha256=sha(comparison/'comparison.json'),
                    group_index=g,candidate_id=c,geometry_unchanged=True,manual_camera_and_cue_revision_checked=expected=='full')
                rows.append(row);print(label,name,len(route['arc_mm']),'points',row['available_branch_events'],'cues',flush=True)
            comp_binding=verify_bundle(parent)
            selected('selected_full',folder/'comparison',group,candidate,'full')
            if label=='network_probability_high_ported':
                prepare_comparison(comp,folder/'comparison_bend_1',bend=1.)
                selected('selected_prefix',folder/'comparison_bend_1',group,candidate,'prefix')
                root_group=next(i for i,g in enumerate(alt['groups']) if g['scope_diameter_mm']==4.)
                selected('selected_root',folder/'comparison',root_group,alt['groups'][root_group]['pareto'][0]['candidate_id'],'root')
        assert defaults=={n:sha(ROOT/n) for n in defaults}
        peak=None
        if platform=='ARM':
            import resource
            peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        proof=dict(status='four_current_CT_fields_selected_full_curve_prefix_root_camera_cues_bundles_passed',
            platform=platform,cases=rows,source_closure_sha256=closure,PL_access=False,new_bitstream=False,
            production_promoted=False,peak_preparation_test_RSS_MiB=peak,
            native_UI_selected_path_controls_and_physical_review_pending=True,
            default_files_unchanged_sha256=defaults,
            evidence_sha256={str(p.relative_to(output)).replace('\\','/'):sha(p) for p in output.rglob('*') if p.is_file()})
        write_json(output/'acceptance.json',proof);print(proof['status'],flush=True)
    except BaseException as error:
        write_json(output/'failure.json',dict(error=str(error),completed=rows,traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
