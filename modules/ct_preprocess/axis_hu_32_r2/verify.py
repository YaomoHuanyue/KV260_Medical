"""Recheck closed HU proofs from their actual source, logs and transaction data."""
from pathlib import Path
import argparse
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def transactions(path):
    text=Path(path).read_text()
    rows=re.findall(r'\[\[transaction\]\]\s+(\d+)\s+(.*?)\[\[/transaction\]\]',text,re.S)
    assert len(rows)==80 and [int(n) for n,_ in rows]==list(range(80)),path
    return [[int(v,16) for v in values.split()] for _,values in rows]


def verify():
    native=[json.loads((HERE/('build_'+host+'/verified.json')).read_text()) for host in ['Windows','ARM']]
    a,b=native
    assert a['source_SHA256']==b['source_SHA256'] and a['cases']==b['cases'] and len(a['cases'])==79
    assert a['model']==b['model'] and a['invalid_calls']==b['invalid_calls']==8
    assert a['own_CT_SHA256']==b['own_CT_SHA256']=='4507b664690840abb6cb9af2d919377ffc4ef75b167cb6fd0f747befdb12e38e'
    for name,digest in a['source_SHA256'].items():assert sha(ROOT/name)==digest,name
    for name,digest in a['model']['model_SHA256'].items():
        assert sha(ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model'/name)==digest
    for host,item in zip(['Windows','ARM'],native):
        lib=HERE/('build_'+host)/('hu_axis.dll' if host=='Windows' else 'libhu_axis.so')
        assert sha(lib)==item['library_SHA256']
        assert len(item['complete_volumes'])==2 and item['PL_accessed'] is False
    for x,y in zip(a['complete_volumes'],b['complete_volumes']):
        for key in ['voxels','shape_zyx','spacing_xyz','candidate_SHA256','reference_SHA256','slices']:assert x[key]==y[key],key
        assert x['voxels']==36438016 and x['shape_zyx']==[139,512,512]
        assert x['candidate_SHA256']==x['reference_SHA256']
    for name in ['csim','hls','cosim']:
        item=json.loads((HERE/'HLS_r1'/name/'complete.json').read_text())
        assert item['passed'] and item['PL_accessed'] is False
        for n,h in item['source_and_evidence_SHA256'].items():assert sha(ROOT/n)==h,n
    suffixes=['output_r_V_data_V','output_r_V_keep_V','output_r_V_strb_V','output_r_V_last_V','output_r_V_user_V','memory']
    tv=HERE/'HLS_r1/component/hls/sim/tv'
    words={}
    for suffix in suffixes:
        c=tv/'cdatafile'/('c.ct_hu_axis.autotvout_'+suffix+'.dat')
        rtl=tv/'rtldatafile'/('rtl.ct_hu_axis.autotvout_'+suffix+'.dat')
        if suffix == 'memory':
            # HLS serializes AXI memory in binary, unlike the textual AXIS TV.
            expected, actual = c.read_bytes(), rtl.read_bytes()
            assert len(expected) == 115848 and expected == actual
            words[suffix]=dict(c_SHA256=sha(c),RTL_SHA256=sha(rtl),compared_bytes=len(actual))
        else:
            expected,actual=transactions(c),transactions(rtl)
            assert expected==actual,suffix
            words[suffix]=dict(c_SHA256=sha(c),RTL_SHA256=sha(rtl),compared_words=sum(map(len,actual)))
    sizes=[0,1,2,7,8,15,16,17,31,32,33,63,64,65,95,96,97,127,128,129,1023,1024,1025,65535,65536,65537]
    logical=[(n,0,0) for n in sizes]+[(97,e,0) for e in range(1,16) for _ in [0,1,3]]
    for n in [1,33,65,1025]:logical.extend([(n,0,1),(n,0,0)])
    logical.append((268435457,0,0))
    assert len(logical)==80
    modes={}
    for mode in ['ordinary','random']:
        path=HERE/'rtl_r1'/(mode+'_r2')/'complete.json'
        value=json.loads(path.read_text())
        assert value['complete_cases']==80 and value['identity']==0xd6
        assert value['logical_cases']==[[i,*row] for i,row in enumerate(logical)]
        for field in ['source_SHA256','evidence_SHA256']:
            for n,h in value[field].items():assert sha(ROOT/n)==h,n
        assert value['observed']['stress']==int(mode=='random') and value['observed']['input_stalls']>0
        if mode=='random':
            for key in ['output_stalls','ar_stalls','aw_stalls','w_stalls']:assert value['observed'][key]>0,key
        modes[mode]=dict(receipt_SHA256=sha(path),observed=value['observed'])
    # Independent negative evidence: the original core really returned stale
    # upper-tail bytes for transaction 13, while the unchanged oracle expected 0.
    old=HERE.parent/'axis_hu_r1/HLS_r1/component/hls/sim/tv'
    suffix='output_r_V_data_V'
    c=old/'cdatafile'/('c.ct_hu_axis.autotvout_'+suffix+'.dat')
    rtl=old/'rtldatafile'/('rtl.ct_hu_axis.autotvout_'+suffix+'.dat')
    original_c,original_rtl=transactions(c),transactions(rtl)
    assert original_c[13][0]==original_rtl[13][0] and len(original_c[13])==len(original_rtl[13])==2
    assert original_c[13][1]>>256==0 and original_rtl[13][1]>>256!=0
    assert original_c[13][1]&((1<<256)-1)==original_rtl[13][1]&((1<<256)-1)
    value=dict(status='two_host_native_full_CT_and_vendor80_and_wrapped80_each_mode_verified',
        each_host_native_cases=79,each_host_native_invalid_calls=8,all65536_HU_exact=True,
        own_CT_voxels=36438016,raw_and_inference_grid_exact_each_host=True,
        each_wrapped_RTL_mode_cases=80,actual_RTL_transaction_comparisons=words,
        actual_backpressure=modes,original_stale_tail_regression_confirmed_from_actual_RTL=True,
        original_failure_artifacts_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [c,rtl]},
        HLS_estimates=json.loads((HERE/'HLS_r1/hls/complete.json').read_text())['HLS_estimates'],
        actual_PL_board_tested=False,full_PR_passed=False,production_promoted=False,whole_goal_completed=False)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=verify();result['verifier_SHA256']=sha(__file__)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
