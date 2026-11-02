"""Run the same full-word checker against the compact current archive.

Only archive addressing and retained-member count change. All native, Csim,
hardware identity, AXI, resource, oracle and 6,422,850-word checks are retained.
"""
from pathlib import Path
import hashlib
import inspect
import json
import os
import sys
import zipfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import verify_full_RTL_r3 as prior
OUT=prior.OUT

def sha(path): return prior.sha(path)

def main():
    curation=json.loads((OUT/'current_curation.json').read_text())
    assert curation['original_all1969_members_stream_SHA_checked']
    assert curation['both_actual_hosts_independently_verified_before_compaction']
    assert curation['all_new_RTL_job_declared_inputs_retained'] and curation['full_word_evidence_kept']
    assert curation['exact_owned_server_root_absent'] and not curation['precision_or_scope_changed']
    current=curation['current_archive']; receipt=json.loads((OUT/'download_verified_r2617.json').read_text())
    assert curation['original_archive']==receipt['archive']
    archive=OUT/current['archive']; assert sha(archive)==current['sha256']
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('outputs_manifest.json'))
        original=json.loads(z.read('collection/original_outputs_manifest.json'))
        assert len(manifest)==current['count']==1229 and len(original)==1969
        for name,h in manifest.items():
            with z.open(name) as f: assert hashlib.file_digest(f,'sha256').hexdigest()==h,name
            if not name.startswith('collection/'): assert original[name]==h,name
        proofs=[json.loads(z.read('collection/verified_full14_'+host+'.json')) for host in ['Windows','ARM']]
        assert proofs[0]['host']=='Windows' and proofs[1]['host']=='ARM'
        assert {k:v for k,v in proofs[0].items() if k!='host'}=={k:v for k,v in proofs[1].items() if k!='host'}
        assert proofs[0]['full_RTL_passed'] and proofs[0]['all_6422850_words_compared_independently']
        assert proofs[0]['archive_sha256']==receipt['archive']['sha256']
        assert hashlib.sha256(z.read('collection/raw_verifier.py')).hexdigest()==sha(HERE/'verify_full_RTL_r3.py')==proofs[0]['verifier_sha256']
    source=inspect.getsource(prior.inspect)
    original_source=source
    edits=[("archive=OUT/'result.zip'; meta=receipt['archive']", "archive=OUT/'current_candidate.zip'; meta=curation['current_archive']"),
           ("assert len(manifest)==meta['count']==1969", "assert len(manifest)==meta['count']"),
           ("archive_members=1969", "archive_members=meta['count']")]
    for before,after in edits:
        assert source.count(before)==1
        source=source.replace(before,after)
    scope=dict(prior.__dict__,curation=curation,__file__=__file__)
    exec(compile(source,str(Path(__file__)),'exec'),scope)
    result=scope['inspect']()
    result.update(host='Windows' if os.name=='nt' else 'ARM',
        status='compact_current16K_all_original_full14_words_and_gates_verified',
        original_archive_sha256=receipt['archive']['sha256'],original_archive_members=1969,
        compiler_caches_not_required_for_independent_full_word_checks=True,
        curation_sha256=sha(OUT/'current_curation.json'),
        reader_derivation=dict(parent_sha256=sha(HERE/'verify_full_RTL_r3.py'),
            original_inspect_sha256=hashlib.sha256(original_source.encode()).hexdigest(),
            actual_inspect_sha256=hashlib.sha256(source.encode()).hexdigest(),
            literal_edits=[dict(before=a,after=b,occurrences=1) for a,b in edits],
            all_numerical_protocol_and_resource_predicates_unchanged=True))
    path=OUT/('verified_current_full14_'+result['host']+'.json')
    with path.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2); f.write('\n')
    print('PASS',result['host'],'compact current16K full14 all6422850 words; no compiler caches',flush=True)

if __name__=='__main__': main()
