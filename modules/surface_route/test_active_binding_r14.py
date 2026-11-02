"""Current geometry/target/options binding, independent of the native UI cache."""
from pathlib import Path
import argparse,copy,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.active_actions_r14 import validate_bound_comparison
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    platform='Windows' if sys.platform=='win32' else 'ARM';label='network_probability_high_ported'
    parent=ROOT/f'modules/surface_route/results/selected_own_CT_{platform}_r13'/label
    comparison=parent/'comparison';proof=json.loads((comparison/'comparison.json').read_text(encoding='utf-8'))
    bundle=parent/'selected_full';meta=json.loads((bundle/'scene.json').read_text(encoding='utf-8'))
    entry=dict(receipt=str(comparison/'comparison.json'),receipt_sha256=sha(comparison/'comparison.json'),
        options=dict(lesion=3,diameter=1.8,margin=.3,minimum_bend=0.))
    scene=dict(result=proof['binding']['source_result'],input_sha256=proof['binding']['CT_input_sha256'],
        complete_surface=dict(bundle=str(bundle),scalar_sha256=meta['renderer_scalar_sha256']),navigation={})
    for key in ('whole_instrument_profiles','whole_alternative_routes'):
        scene['navigation'][key]=json.loads((comparison/(key+'.json')).read_text(encoding='utf-8'))
    bound=proof['binding']['source_files_sha256'];tests=[]
    def rejected(name,function):
        try:function()
        except ValueError:tests.append(name)
        else:raise AssertionError('Accepted '+name)
    validate_bound_comparison(scene,entry,bound);tests.append('comparison_survives_new_route_revision_on_identical_C1_surface')
    for key,value in [('lesion',4),('margin',.4),('minimum_bend',1.),('diameter',2.5)]:
        bad=copy.deepcopy(entry);bad['options'][key]=value
        rejected('changed_option_'+key,lambda:validate_bound_comparison(scene,bad,bound))
    bad=copy.deepcopy(entry);bad['receipt_sha256']='different-receipt'
    rejected('changed_comparison_receipt',lambda:validate_bound_comparison(scene,bad,bound))
    bad=copy.deepcopy(scene);bad['navigation']['whole_alternative_routes']['groups'][0]['candidates'][0]['gap_mm']+=1.
    rejected('changed_displayed_Pareto_data',lambda:validate_bound_comparison(bad,entry,bound))
    bad=copy.deepcopy(scene);bad['complete_surface']['scalar_sha256']='different-field'
    rejected('changed_active_scalar',lambda:validate_bound_comparison(bad,entry,bound))
    bad=copy.deepcopy(scene);bad['complete_surface']['bundle']=str(parent.parent/'accepted_binary_high_ported/selected_full')
    rejected('another_C1_mesh',lambda:validate_bound_comparison(bad,entry,bound))
    missing=dict(bound);missing.pop(next(iter(missing)))
    rejected('missing_original_case_proof',lambda:validate_bound_comparison(scene,entry,missing))
    write_json(a.output,dict(status='active_surface_comparison_target_constraints_and_display_integrity_passed',platform=platform,
        tests=tests,source_sha256={n:sha(ROOT/n) for n in ('modules/surface_route/active_actions_r14.py','modules/surface_route/test_active_binding_r14.py')},
        PL_access=False,production_promoted=False));print('passed',len(tests),flush=True)


if __name__=='__main__':main()
