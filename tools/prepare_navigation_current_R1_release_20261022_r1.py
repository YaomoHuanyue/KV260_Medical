"""Admit the unchanged qualified bit/host through a new exact-RTL certificate."""
from pathlib import Path
import hashlib,json
import project_storage
ROOT=project_storage.SYSTEM;HERE=ROOT/'modules/navigation_comparison/current_release_r1';LEGACY=ROOT/'dfx/navigation_profile'
PROOF=ROOT/'results/navigation_R1_repro_HLS_20261022_r1/axis_hls/verified_PC.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    project_storage.check(60_000_000);assert not (HERE/'runtime.py').exists() and not (HERE/'runtime_inputs.json').exists()
    proof=json.loads(PROOF.read_text())
    assert proof['actual_six_original_Csim_cases_exact'] and proof['all_actual_original_RTL_byte_identical']
    for n,h in proof['source_and_evidence_SHA256'].items():assert sha(ROOT/n)==h,n
    old=json.loads((LEGACY/'release_r1/manifest.json').read_text());bindings={}
    def bind(p):bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    for group in ('source_sha256','artifact_sha256'):
        for n,h in old[group].items():
            if group=='source_sha256' and n=='build/profile.cfg':continue
            assert sha(LEGACY/n)==h;bind(LEGACY/n)
    host=json.loads((LEGACY/'docs/host_build_ARM_r1.json').read_text())
    assert sha(LEGACY/'build/libprofile_xrt_r1.so')==host['library_sha256']
    for n,h in host['source_sha256'].items():assert sha(LEGACY/n)==h;bind(LEGACY/n)
    for p in (LEGACY/'release_r1/manifest.json',LEGACY/'build/libprofile_xrt_r1.so',LEGACY/'protocol_fast_r2.py',
        ROOT/'dfx/medical/release/manifest.json',ROOT/'dfx/surface_quality/release/manifest.json',ROOT/'dfx/surface_quality/release/medical_quality_partial.bin'):
        bind(p)
    dest=HERE/'reproduced/qualification.json'
    with dest.open('xb') as f:f.write(PROOF.read_bytes())
    for p in (HERE/'reproduced').rglob('*'):
        if p.is_file():bind(p)
    record=dict(schema='kv260.navigation.reproduced_R1_current_release.v1',identity=0xcd,
        unchanged_original_bitstream_and_byte_identical_host=True,
        missing_original_CFG_replaced_only_by_independent_all_RTL_sixcase_equivalence=True,
        current_quality_pin_explicitly_requalified_same_static=True,
        source_and_artifact_SHA256=bindings,actual_new_runtime_board_qualification_pending=True,whole_goal_completed=False)
    with (HERE/'runtime_inputs.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
    template=(HERE/'runtime_template.py').read_text();assert template.count('__QUALIFIED_INPUTS_SHA256__')==1
    source=template.replace('__QUALIFIED_INPUTS_SHA256__',sha(HERE/'runtime_inputs.json'));compile(source,str(HERE/'runtime.py'),'exec')
    (HERE/'runtime.py').write_text(source,encoding='utf8')
    proof=dict(exact_runtime_template_edit=['__QUALIFIED_INPUTS_SHA256__',sha(HERE/'runtime_inputs.json')],
        original_host_and_transfer_code_not_modified=True,original_legacy_release_and_current_quality_manifest_not_modified=True,
        source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),HERE/'runtime.py',HERE/'runtime_template.py',HERE/'runtime_inputs.json')},
        actual_board_tests_required_before_default_promotion=True,PL_accessed=False,whole_goal_completed=False)
    with (HERE/'runtime_derivation.json').open('x') as f:json.dump(proof,f,indent=2)
    print('PASS explicit exact-RTL requalification admission; original host and firmware untouched; board trial still required')
if __name__=='__main__':main()
