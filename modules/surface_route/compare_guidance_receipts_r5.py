"""Compare independently prepared Windows/ARM geometry and exact C9 packets."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np

HERE=Path(__file__).resolve().parent;SYSTEM=HERE.parents[1]
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists()
    folders={k:HERE/f'results/guidance_own_CT_{k}_r5' for k in ('Windows','ARM')}
    proofs={k:READ(p/'acceptance.json') for k,p in folders.items()}
    for k,proof in proofs.items():
        for rel,digest in {**proof['source_sha256'],**proof['input_sha256']}.items():
            assert SHA(SYSTEM/rel)==digest,rel
        assert len(proof['scenarios'])==8 and len(proof['render_cases'])==6
        for row in proof['scenarios']:
            for name,digest in row['files_sha256'].items():assert SHA(folders[k]/name)==digest,name
        for row in proof['render_cases']:
            for name,digest in row['files_sha256'].items():assert SHA(folders[k]/'render_cases'/name)==digest,name
    matched=[]
    for a,b in zip(proofs['Windows']['scenarios'],proofs['ARM']['scenarios']):
        assert a['label']==b['label'] and a['scalar_sha256']==b['scalar_sha256']
        label=a['label']
        for suffix in ('route','camera','targets'):
            x=dict(np.load(folders['Windows']/(label+'_'+suffix+'.npz'),allow_pickle=False))
            y=dict(np.load(folders['ARM']/(label+'_'+suffix+'.npz'),allow_pickle=False))
            assert x.keys()==y.keys()
            for key in x:
                if x[key].dtype.kind in 'biu':np.testing.assert_array_equal(x[key],y[key])
                else:np.testing.assert_allclose(x[key],y[key],rtol=0,atol=1e-10)
        x=READ(folders['Windows']/(label+'_guidance.json'))
        y=READ(folders['ARM']/(label+'_guidance.json'))
        assert len(x['events'])==len(y['events'])
        for e,f in zip(x['events'],y['events']):
            for key in ('id','junction_point_ids','selected_branch_id','selected_exit_point_id','available'):
                assert e[key]==f[key],(label,key)
            if e['available']:
                for key in ('junction_arc_mm','exit_arc_mm','marker_arc_mm','marker_lps_mm','show_from_mm','hide_after_mm'):
                    np.testing.assert_allclose(e[key],f[key],rtol=0,atol=1e-9)
                assert e['target_voxels']==f['target_voxels']
        matched.append(dict(label=label,all_geometric_camera_and_audit_arrays_equivalent=True,
            all_scalar_target_voxels_exact=True,all_selected_branch_decisions_equal=True,
            Windows_route_id=a['route_id'],ARM_route_id=b['route_id']))
    for a,b in zip(proofs['Windows']['render_cases'],proofs['ARM']['render_cases']):
        assert a['name']==b['name']
        assert a['files_sha256']==b['files_sha256'],a['name']
    record=dict(status='eight_Windows_ARM_curves_cameras_selected_exits_and_targets_match_six_C9_packets_byte_exact',
        scenarios=matched,source_sha256=SHA(Path(__file__)),
        evidence_sha256={k:SHA(p/'acceptance.json') for k,p in folders.items()},
        PL_access=False,production_promoted=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(record['status'])


if __name__=='__main__':main()
