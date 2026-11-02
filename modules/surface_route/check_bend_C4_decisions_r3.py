"""Check threshold decision vectors, not just approximate bend values."""
from pathlib import Path
import argparse,json,sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.own_ct_trial import SHA


def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists()
    receipt=json.loads((a.comparison/'acceptance.json').read_text());review=json.loads((a.review/'acceptance.json').read_text())
    assert receipt['status']=='actual_C4_nonzero_bend_prefix_queries_same_input_native_PS_PL_compared_no_promotion'
    assert receipt['review_receipt_sha256']==SHA(a.review/'acceptance.json')
    for n,d in receipt['files_sha256'].items():assert SHA(a.comparison/n)==d
    for n,d in review['source_sha256'].items():assert SHA(SYSTEM/n)==d
    inputs={x['tier']:x for x in review['cases']};records=[]
    for case in receipt['cases']:
        name=case['tier'];source=inputs[name];assert SHA(a.review/source['arrays_file'])==source['arrays_sha256']
        arrays=dict(np.load(a.review/source['arrays_file'],allow_pickle=False));n=len(arrays['arc_mm'])
        actual=np.fromfile(a.comparison/(name+'_PL_full_output.bin'),'<u8').reshape(8706,8)
        rows=actual.view('<f8')[1:n+1,:5]
        expected=np.fromfile(a.comparison/(name+'_PS_output.bin'),'<f8').reshape(n,5)
        original=np.column_stack([arrays[k] for k in ('bend_radius_mm','forward_adjusted_radius_mm',
            'forward_minimum_bend_radius_mm','spare_radius_mm','clearance_state')])
        np.testing.assert_allclose(expected,original,rtol=2e-9,atol=1e-7)
        threshold=source['instrument_parameters']['minimum_bend_radius_mm']
        point_decisions=rows[:,0]+1e-5<threshold
        forward_decisions=rows[:,2]+1e-5<threshold
        np.testing.assert_array_equal(point_decisions,original[:,0]+1e-5<threshold)
        np.testing.assert_array_equal(forward_decisions,original[:,2]+1e-5<threshold)
        np.testing.assert_array_equal(rows[:,4],original[:,4])
        records.append(dict(tier=name,points=n,minimum_bend_radius_mm=threshold,
            prefix_point_violation_count=int(point_decisions.sum()),
            all_point_and_lookahead_decisions_and_states_exact=True))
    assert len(records)==len(inputs)==12
    result=dict(status='actual_C4_all_twelve_own_CT_queries_original_prefix_point_and_forward_decisions_exact',
        cases=records,source_sha256=SHA(Path(__file__)),
        comparison_receipt_sha256=SHA(a.comparison/'acceptance.json'),review_receipt_sha256=SHA(a.review/'acceptance.json'),
        physical_wall_replanning_on='PS',only_bend_window_statistics_tested_on='actual_C4_PL',
        full_prefix_controller_uses_verified_identical_decision_vectors=True,
        new_bitstream=False,production_promoted=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'])


if __name__=='__main__':main()
