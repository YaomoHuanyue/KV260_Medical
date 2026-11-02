"""Require the original complete pool qualification plus an exact log-only host."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3]
SCHEMA='kv260.ct_pool.unique_log_hardware_trial.v1'


def verify_log_host(record,retained):
    binding=record.get('original_hardware_admission',{})
    if set(binding)!={'path','SHA256'}:raise RuntimeError('Original pool admission binding required')
    path=ROOT/binding['path']
    if retained(path)!=binding['SHA256']:raise RuntimeError('Changed original pool admission')
    original=json.loads(path.read_text())
    if original.get('schema')!='kv260.ct_pool.hardware_trial.v1':raise RuntimeError('Wrong original pool admission')
    log=record.get('unique_log_host',{})
    if set(log)!={'compile_proof','compile_proof_SHA256','library','library_SHA256'}:
        raise RuntimeError('Complete linked log-only host binding required')
    proof_path=ROOT/log['compile_proof']
    if retained(proof_path)!=log['compile_proof_SHA256']:raise RuntimeError('Changed linked host proof')
    proof=json.loads(proof_path.read_text())
    if not all(proof.get(k) is True for k in ('actual_unique_log_runtime_dependency_verified',
        'actual_full_C5_pool_bridge_byte_identical','no_CDLL_XRT_MMIO_PL_lock_or_firmware_access',
        'actual_repeated_hardware_sessions_and_full139_integration_pending')):
        raise RuntimeError('Full real ARM host qualification required before explicit trial')
    if proof.get('PL_resource_change')!=0 or len(proof.get('original_C_API_exports_exact',[]))!=20:
        raise RuntimeError('The full pool interface or hardware changed')
    if retained(ROOT/log['library'])!=log['library_SHA256'] or log['library_SHA256']!=proof['library_SHA256']:
        raise RuntimeError('Linked log-only host library mismatch')
    for name,digest in proof['source_and_evidence_SHA256'].items():
        if retained(ROOT/name)!=digest:raise RuntimeError('Changed full host input: '+name)
    expected=dict(original,schema=SCHEMA,library_SHA256=log['library_SHA256'],
        original_hardware_admission=binding,unique_log_host=log)
    if record!=expected:raise RuntimeError('Original hardware, numeric, ABI or physical qualification changed')
    return proof
