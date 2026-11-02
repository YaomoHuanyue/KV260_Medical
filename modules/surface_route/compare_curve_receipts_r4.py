"""Cross-platform equality, with complete array/source closure checks."""
from pathlib import Path
import argparse,json,sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.own_ct_trial import SHA


def main():
    p=argparse.ArgumentParser();p.add_argument('--windows',type=Path,required=True)
    p.add_argument('--arm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();receipts=[]
    for folder,platform in ((a.windows,'win32'),(a.arm,'linux')):
        receipt=json.loads((folder/'acceptance.json').read_text())
        assert receipt['platform']==platform and receipt['status']=='own_CT_Q5_Q6_physical_curve_quality_bend_wall_mask_camera_passed'
        for n,d in receipt['source_sha256'].items():assert SHA(SYSTEM/n)==d,n
        for scenario in receipt['scenarios']:
            for n,d in scenario['files_sha256'].items():assert SHA(folder/n)==d,n
        for case in receipt['cases']:
            for n,d in case['source_binding_sha256'].items():assert SHA(SYSTEM/n)==d,n
        receipts.append(receipt)
    w,b=receipts;assert len(w['scenarios'])==len(b['scenarios'])==8
    records=[]
    for x,y in zip(w['scenarios'],b['scenarios']):
        assert x['tier']==y['tier'] and x['minimum_bend_radius_mm']==y['minimum_bend_radius_mm']
        for n in ('query_trace','status','reason','selected_endpoint_id','requested_endpoint_id','bend_prefix_queries'):
            assert x['report'][n]==y['report'][n],n
        assert set(x['files_sha256'])==set(y['files_sha256'])
        maximum=0.
        for name in x['files_sha256']:
            if not name.endswith('.npz'):continue
            aa=dict(np.load(a.windows/name,allow_pickle=False));bb=dict(np.load(a.arm/name,allow_pickle=False))
            assert set(aa)==set(bb)
            for n in aa:
                v,u=aa[n],bb[n];assert v.shape==u.shape and v.dtype==u.dtype
                if v.dtype.kind in 'biu':np.testing.assert_array_equal(v,u)
                else:
                    np.testing.assert_array_equal(np.isinf(v),np.isinf(u))
                    np.testing.assert_allclose(v,u,rtol=2e-9,atol=1e-7 if 'bend' in n else 1e-11)
                    good=np.isfinite(v)&np.isfinite(u)
                    if np.any(good):maximum=max(maximum,float(np.max(np.abs(v[good]-u[good]))))
        records.append(dict(tier=x['tier'],minimum_bend_radius_mm=x['minimum_bend_radius_mm'],
            query_count=len(x['report']['query_trace']),point_count=x['report']['point_count'],
            status=x['report']['status'],length_mm=x['report']['length_mm'],
            all_prefix_decisions_and_integer_states_exact=True,maximum_float_absolute_difference=maximum))
    receipt=dict(status='own_CT_physical_curve_quality_Windows_ARM_full_arrays_and_original_prefix_decisions_match',
        scenarios=records,Windows_receipt_sha256=SHA(a.windows/'acceptance.json'),
        ARM_receipt_sha256=SHA(a.arm/'acceptance.json'),source_sha256=SHA(Path(__file__)),
        PL_access=False,production_promoted=False)
    a.output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(receipt['status'])


if __name__=='__main__':main()
