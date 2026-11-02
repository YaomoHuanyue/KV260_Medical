"""Requalified original R1 host with a fresh exact-RTL source certificate."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];LEGACY=ROOT/'dfx/navigation_profile'
INPUTS_SHA256='__QUALIFIED_INPUTS_SHA256__'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inputs():
    path=HERE/'runtime_inputs.json'
    if sha(path)!=INPUTS_SHA256:raise RuntimeError('Changed current R1 release admission')
    return json.loads(path.read_text())
def verify_current():
    record=inputs()
    for n,h in record['source_and_artifact_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=h:raise RuntimeError('Missing/changed requalified R1 dependency: '+n)
    manifest=json.loads((LEGACY/'release_r1/manifest.json').read_text())
    if manifest['schema']!='kv260.navigation_profile.dfx.v1' or manifest['identity']!=0xcd or not manifest['offline_verified']:
        raise RuntimeError('Wrong original profile hardware')
    proof=json.loads((HERE/'reproduced/qualification.json').read_text())
    if not (proof['actual_six_original_Csim_cases_exact'] and proof['all_actual_original_RTL_byte_identical'] and
        proof['every_owned_file_collected_and_exact_root_removed'] and proof['original_firmware_unchanged_and_no_new_bitstream']):
        raise RuntimeError('Full source reproduction qualification required')
    oldrtl=json.loads((LEGACY/'docs/rtl_r1.json').read_text())['direct_original_RTL_sha256']
    if proof['original_RTL_SHA256']!=oldrtl or proof['RTL_modules']!=len(oldrtl):raise RuntimeError('Incomplete original RTL source equivalence')
    if proof['original_missing_CFG_SHA256']!=manifest['source_sha256']['build/profile.cfg']:
        raise RuntimeError('Original missing-config record changed')
    if sha(HERE/'reproduced/regenerated.cfg')!=proof['regenerated_CFG_SHA256'] or proof['regenerated_CFG_SHA256']==proof['original_missing_CFG_SHA256']:
        raise RuntimeError('Regenerated configuration must be explicit and separately qualified')
    for name,h in proof['all_fresh_generated_members_SHA256'].items():
        if sha(HERE/'reproduced/RTL'/Path(name).name)!=h:raise RuntimeError('Changed actual generated RTL/initializer')
    # Every original source/artifact gate is retained, with only the lost cfg
    # replaced by the independent six-case/all-RTL source-equivalence proof.
    for group in ('source_sha256','artifact_sha256'):
        for name,h in manifest[group].items():
            if group=='source_sha256' and name=='build/profile.cfg':continue
            if sha(LEGACY/name)!=h:raise RuntimeError('Changed original release dependency: '+name)
    if sha(ROOT/'dfx/medical/release/manifest.json')!=manifest['static_base_manifest_sha256']:
        raise RuntimeError('Changed original static shell')
    if sha('/lib/firmware/medical_navigation_profile_r1_partial.bin')!=manifest['partial_bin_sha256']:
        raise RuntimeError('Changed original profile firmware')
    host=json.loads((LEGACY/'docs/host_build_ARM_r1.json').read_text())
    if host['status']!='compiled_no_PL_access' or sha(LEGACY/'build/libprofile_xrt_r1.so')!=host['library_sha256']:
        raise RuntimeError('Original byte-identical host required')
    for n,h in host['source_sha256'].items():
        if sha(LEGACY/n)!=h:raise RuntimeError('Changed original host source')
    quality=ROOT/'dfx/surface_quality/release';q=json.loads((quality/'manifest.json').read_text())
    if not(q['schema']=='kv260.surface_quality.dfx.v1' and q['identity']==0xc9 and q['offline_verified'] and q['clock_MHz']==100 and q['timing']['timing_passed']):
        raise RuntimeError('Qualified current surface release required')
    route=json.loads((LEGACY/'docs/route_r1.json').read_text())
    if q['static_routed_sha256']!=route['static_checkpoint_sha256']:
        raise RuntimeError('Current quality and original profile use different static platforms')
    if sha(quality/'medical_quality_partial.bin')!=q['partial_bin_sha256'] or sha('/lib/firmware/medical_quality_partial.bin')!=q['partial_bin_sha256']:
        raise RuntimeError('Changed current quality firmware')
    return manifest

def capsule():
    record=inputs();path=LEGACY/'runtime_r1.py'
    if sha(path)!=record['source_and_artifact_SHA256']['dfx/navigation_profile/runtime_r1.py']:
        raise RuntimeError('Changed original runtime implementation')
    sys.path.insert(0,str(LEGACY))
    namespace=dict(__file__=str(path),__name__='qualified_original_profile_R1_current_context')
    exec(compile(path.read_text(),str(path),'exec'),namespace)
    namespace['verify']=verify_current
    from protocol_fast_r2 import R1AdapterSession
    if Path(sys.modules['protocol_fast_r2'].__file__).resolve()!=LEGACY/'protocol_fast_r2.py':raise RuntimeError('Wrong profile protocol module')
    class CurrentSession(R1AdapterSession,namespace['Session']):pass
    return CurrentSession
Session=capsule()
