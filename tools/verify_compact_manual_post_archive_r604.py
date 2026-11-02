"""Verify full frozen RTL banks from a ZIP stream without filling the SD card."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,io,itertools,json,os,re,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/compact_manual_post_archive_r604'
def digest(file):
    h=hashlib.sha256()
    for block in iter(lambda:file.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def words(file,width,count):
    state='runtime';case=-1;index=0
    for line in io.TextIOWrapper(file,encoding='ascii'):
        t=line.strip()
        if not t:continue
        if state=='runtime':assert t=='[[[runtime]]]';state='transaction'
        elif state=='transaction':
            if t=='[[[/runtime]]]':state='end'
            else:
                m=re.fullmatch(r'\[\[transaction\]\]\s+(\d+)',t);assert m and int(m[1])==case+1
                case+=1;index=0;state='data'
        elif state=='data':
            if t=='[[/transaction]]':assert index==count;state='transaction'
            else:
                value=int(t,16 if t.startswith('0x') else 10);assert 0<=value<2**width and index<count
                yield case,index,value;index+=1
        else:raise AssertionError('Trailing bank data')
    assert state=='end' and case==6
def main():
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--sha256',required=True);p.add_argument('--count',type=int,required=True);a=p.parse_args()
    with a.archive.open('rb') as f:assert digest(f)==a.sha256
    with zipfile.ZipFile(a.archive) as z:
        manifest=json.loads(z.read('upload_manifest.json'));assert len(manifest)==a.count
        assert len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(manifest)|{'upload_manifest.json'}
        for n,h in manifest.items():
            path=PurePosixPath(n);assert not path.is_absolute() and '..' not in path.parts and ':' not in n
            with z.open(n) as f:assert digest(f)==h,n
        get=lambda n:json.loads(z.read(n))
        proof=get('results/compact_manual_independent_post_r586/acceptance.json')
        assert proof['all_original_6422850_writable_words_exact'] and proof['original_live_job_not_modified_or_restarted']
        for n,h in proof['source_and_evidence_sha256'].items():assert manifest[n]==h,n
        receipt=get('results/compact_manual_independent_post_r586/post_receipt.json')
        assert receipt['exit_code']==0 and receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified']
        assert receipt['resource_failure'] is None and not receipt['elapsed_time_abort']
        assert receipt['job_memory_limit_bytes']==32*1024**3 and receipt['minimum_system_free_commit_bytes']==int(1.5*1024**3)
        log=z.read('results/compact_manual_independent_post_r586/post.log').decode()
        assert 'ALL FULL INTEGER FMA SEVEN STRICT CASES PASSED' in log and 'PASS six independent native oracle invocations plus explicit invalid case' in log
        all_banks={};total=0;prefix='dfx/smooth_speed/manual_compact_r481/RTL_r499'
        for mode in ['ordinary','random']:
            suite=get(prefix+'/'+mode+'_simulate_receipt.json')['resource_receipt']
            assert suite['exit_code']==0 and suite['all_owned_processes_terminal'] and suite['resource_failure'] is None
            simlog=z.read(prefix+'/'+mode+'_simulate.log').decode()
            assert 'PASS full_original_R157_independent_bounded_AXI 7/7' in simlog and simlog.count('R157_BOUNDED_COMPLETED case=')==7
            assert not any(t in simlog for t in ['ERROR:','Fatal:','Critical WARNING'])
            for name,width,count in [('meta',32,131090),('coords',128,327685)]:
                raw=prefix+f'/{mode}/sim/tv/rtldatafile/rtl.mesh_smooth.autotvout_{name}.dat'
                gold=prefix+f'/{mode}/sim/tv/cdatafile/c.mesh_smooth.autotvout_{name}.dat'
                checked=0
                with z.open(raw) as r,z.open(gold) as g:
                    for x,y in itertools.zip_longest(words(r,width,count),words(g,width,count)):
                        assert x==y,(mode,name,x,y);checked+=1
                assert checked==7*count;all_banks[mode+'_'+name]=checked;total+=checked
        assert total==6422850
    OUT.mkdir(exist_ok=True);host='Windows' if os.name=='nt' else 'ARM'
    j=dict(status='all_14_actual_RTL_cases_6422850_words_and_frozen_independent_post_receipt_verified',host=host,archive=a.archive.resolve().relative_to(ROOT).as_posix(),archive_sha256=a.sha256,archive_entry_count=a.count,all_full_banks=all_banks,all_6422850_words_compared_independently=True,evidence_streamed_without_extracting_large_banks=True,ARM_did_not_execute_Windows_post_binary=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_R499_workflow_terminal_still_pending=True,PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (OUT/f'verified_{host}.json').open('x',encoding='utf-8') as f:json.dump(j,f,indent=2);f.write('\n')
    print('PASS streamed complete 14 cases and 6422850 RTL words',host,flush=True)
if __name__=='__main__':main()
