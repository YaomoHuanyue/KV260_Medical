"""Full report equivalence and exact-point root proof reuse, without PL access."""
from pathlib import Path
import argparse,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.comparison_r11 import Comparison as R11,solve_all
from modules.surface_route.comparison_r12 import Comparison as R12,RootRegion
from modules.surface_route.test_comparison_r11 import fixture,heap_oracle
from modules.surface_route.own_CT_comparison_r11 import semantic
from modules.surface_route.bundle_r8 import sha


def without_reuse(value):
    value=dict(semantic(value));value.pop('root_winding_query_reuse',None)
    return value


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists();tests=[]
    for n in (1,8,201):
        args=fixture(n=n)[:5];old=R11(*args,binding={});new=R12(*args,binding={})
        previous=None
        for comp in (old,new):
            q=comp.queries([.2,1.,2.,20.],.1);values=solve_all(q,heap_oracle)
            whole,alt,arrays=comp.produce(q,*values,candidate_slack_mm=100.)
            if previous is None:previous=whole,alt,arrays
            else:
                assert without_reuse(whole)==without_reuse(previous[0])
                assert without_reuse(alt)==without_reuse(previous[1])
                assert set(arrays)==set(previous[2])
                for key,value in arrays.items():np.testing.assert_array_equal(value,previous[2][key],err_msg=key)
                total=sum(g['candidate_count'] for g in alt['groups'])
                assert alt['root_winding_query_reuse']['reused_exact_same_root']>=total
                assert alt['root_winding_query_reuse']['computed_other_roots']==0
        tests.append('all_reports_paths_arrays_equal_R11_n_'+str(n))
    root=new.c.points_lps_mm[new.raw.root];wrapper=new.region
    result=wrapper.root_winding(root);result['value']=float('nan')
    assert np.isfinite(wrapper.root_winding(root)['value'])
    point=root.copy();point[0]=np.nextafter(point[0],np.inf)
    count=wrapper.computed;wrapper.root_winding(point);assert wrapper.computed==count+1
    wrapper.root_winding(root+[0.,.01,0.]);assert wrapper.computed==count+2
    tests.append('exact_point_only_and_caller_mutation_cannot_change_cached_winding')
    source=['modules/surface_route/comparison_r11.py','modules/surface_route/comparison_r12.py',
            'modules/surface_route/test_comparison_r12.py']
    record=dict(status='exact_root_winding_reuse_full_R11_equivalence_passed',tests=tests,
        source_sha256={p:sha(ROOT/p) for p in source},PL_access=False,production_promoted=False)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(record['status'],len(tests))


if __name__=='__main__':main()
