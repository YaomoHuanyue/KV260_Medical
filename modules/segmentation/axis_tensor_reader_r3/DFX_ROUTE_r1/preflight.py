"""Bind actual complete C5 SYN and all full-scope prerequisites before route."""
from pathlib import Path
from contextlib import ExitStack
import hashlib,importlib.util,json,sys
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]
POOL=ROOT/'modules/segmentation/ct_pool_fusion_r1'
SYN=ROOT/'results/tensor_reader_R3_C5_SYN_20261022_r1/axis_hls'
STATIC='285f3d4a50af45cbea7f503f1f32789b0d84b55214163750a301267e2e72fcb9'
REFERENCES=dict(mc='6293f9bb59c16f7144a275b5d50adbf35781c953977464f21ce6ae51696e9a14',
    smooth='159fa568f3071736cb86a30ce6a72fac9eeaa34a24126fa75d7e05fa1c80611f',
    edt='c576a61fc713695660a7c4b7abe6d37454c763bfbf565fa93d644b3d3d30ef49',
    route='f20e2184a3ba57d870d5874252c21c4d06a11f73ce383017c7ec493ab3b74c1f',
    ct='c2c8bd3fc9388ec7fac40412434f8d341753d7acfe927a97971bb75f55ee865c')
CODEC=ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_fma3_area_r14/flow_RTL_r1/verify_collected.py'
REPORTS=ROOT/'modules/reconstruction/mesh_topology_r1/axis_directed_portable_r3/dfx_static_adapter_route_r1/check_reports.py'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def check(proof):
    for n,h in proof['source_and_evidence_SHA256'].items():assert sha(ROOT/n)==h,n

def upstream():
    path=POOL/'DFX_SYN_r4/gate.py'
    spec=importlib.util.spec_from_file_location('exact_R7_RTL_writer_IP_before_route',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.inspect()

def validate_synthesis(proof):
    assert proof['actual_whole_C5_synthesis_qualified'] is True
    assert proof['physical_RP_bits']==1830
    assert proof['all_owned_bytes_and_closed_logs_verified_exact_root_absent'] is True
    assert proof['production_promoted'] is False and proof['whole_goal_completed'] is False
    key=(CORE/'DFX_SYN_r1/admission.json').relative_to(ROOT).as_posix()
    assert key in proof['source_and_evidence_SHA256'],'Not the actual R7 whole-C5 synthesis'
    area=proof['resources']
    assert all(type(area[k]) is int and area[k]>=0 for k in ('LUT','FF','DSP','URAM','RAMB36','RAMB18'))

def inspect():
    qualified=upstream()
    if not qualified['ready']:
        return dict(offline_route_admitted=False,pending_before_start=[qualified['pending']],
            full986_eightresets_actualbursts_and_qualified_writer_then_whole_SYN_required=True)
    if not (SYN/'verified_Windows.json').is_file():
        return dict(offline_route_admitted=False,pending_before_start=[(SYN/'verified_Windows.json').relative_to(ROOT).as_posix()],
            full986_and_writer_qualified_but_actual_whole_R7_SYN_not_yet_qualified=True)
    proof=json.loads((SYN/'verified_Windows.json').read_text());validate_synthesis(proof);check(proof)
    assert proof['physical_RP_bits']==1830 and proof['all_owned_bytes_and_closed_logs_verified_exact_root_absent']
    archive=SYN/'current_candidate.zip';assert sha(archive)==proof['archive_SHA256']
    spec=importlib.util.spec_from_file_location('C5_exact_SYN_DCP_view',CODEC);codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
    with ExitStack() as stack:
        view=codec.View(stack,archive);member='b/rm_ct_synth.dcp';digest=view.original[member]
        with view.stream(member) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest
    capacity_file=ROOT/'dfx/medical/build/rp_capacity.rpt'
    def available(label):
        values=[]
        for line in capacity_file.read_text().splitlines():
            row=[x.strip() for x in line.split('|')[1:-1]]
            if row and row[0]==label:values.append(float(row[7]))
        assert values and len(set(values))==1;return values[0]
    limits={key:available(label) for key,label in dict(LUT='CLB LUTs',FF='CLB Registers',
        DSP='DSPs',URAM='URAM',BRAM36_equivalent='Block RAM Tile').items()}
    assert limits==dict(LUT=88320,FF=176640,DSP=960,URAM=64,BRAM36_equivalent=132)
    area=proof['resources'];used={k:area[k] for k in ('LUT','FF','DSP','URAM')}
    used['BRAM36_equivalent']=area['RAMB36']+area['RAMB18']/2
    remaining={key:limits[key]-used[key] for key in limits};assert all(v>=0 for v in remaining.values())
    previous=(ROOT/'dfx/medical/build/rm_ct_synth_util.rpt').read_text()
    row=[line for line in previous.splitlines() if '|' in line and line.split('|')[1].strip()=='rm_medical']
    # Use the measured baseline values, and verify its exact report row.
    assert len(row)==1
    values=[v.strip() for v in row[0].split('|')[1:-1]];assert len(values)==11
    old=dict(zip(('LUT','Logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','URAM','DSP'),map(int,values[2:])))
    assert {k:old[k] for k in ('LUT','FF','RAMB36','RAMB18','DSP')}==dict(LUT=68728,FF=89869,RAMB36=100,RAMB18=14,DSP=842)
    files={}
    r3=ROOT/'results/tensor_reader_R3_RTL_20261022_r1/axis_rtl/verified_PC.json'
    ip=ROOT/'results/tensor_reader_R3_IP_R2_20261022_r1/axis_hls/verified_PC.json'
    a=json.loads(r3.read_text());b=json.loads(ip.read_text())
    assert a['actual_generated40RTL_full159_original_domains_both_schedules_passed'] and a['all330_full_frames_and8_actual_global_resets_verified']
    assert b['actual_Vivado_IPX_checksum_refresh_and_integrity_passed'] and b['all40_exported_RTL_exact_full330_frame8reset_qualified_R3']
    for p in (r3,ip):
        v=json.loads(p.read_text());check(v);files[p.relative_to(ROOT).as_posix()]=sha(p)
    for name,h in [('static_routed.dcp',STATIC),*[(f'config_{role}.dcp',value) for role,value in REFERENCES.items()]]:
        p=ROOT/'dfx/medical/build'/name;assert sha(p)==h,name;files[p.relative_to(ROOT).as_posix()]=h
    pending=[]
    rtl=ROOT/'results/CT_pool_full493_RTL_20261021_r7/axis_rtl/verified_Windows.json'
    assert qualified['full_RTL']['full986_eightresets_and_actualbursts_qualified']
    result=json.loads(rtl.read_text());check(result)
    files[rtl.relative_to(ROOT).as_posix()]=sha(rtl)
    files[POOL.relative_to(ROOT).as_posix()+'/DFX_writer_IP_r7/gate.py']=sha(POOL/'DFX_writer_IP_r7/gate.py')
    files[POOL.relative_to(ROOT).as_posix()+'/DFX_SYN_r4/gate.py']=sha(POOL/'DFX_SYN_r4/gate.py')
    full=POOL/'host_dual_r1/frontend_full139_r1/output/verified.json'
    if not full.exists():pending.append('complete typed dual-BO own139 CT native model comparison')
    else:
        result=json.loads(full.read_text());check(result)
        for key in ('full139_completed','all2502_convolution_inputs_and139_logits_full_bytes_SHA_exact',
            'actual2502_HLS_C_calls_and417_typed_dual_pool_calls','all_mock_BO_allocations_released_after_preparer_graph_and_backend_close'):assert result[key],key
        files[full.relative_to(ROOT).as_posix()]=sha(full)
    host=POOL/'host_dual_r1/ARM_native_r1/paired_verified.json';host_proof=json.loads(host.read_text());check(host_proof)
    assert host_proof['result']['numeric_and_lifecycle_checks']==311 and host_proof['result']['refusals_before_DMA']==13
    for p in (Path(__file__),HERE/'implement.tcl',REPORTS,CODEC,SYN/'verified_Windows.json',archive,host,
        capacity_file,ROOT/'dfx/medical/build/rm_ct_synth_util.rpt',ROOT/'dfx/medical/build/rp_ports.json'):
        files[p.relative_to(ROOT).as_posix()]=sha(p)
    return dict(status='C5_pool_physical_inputs_and_capacity_ready_full_scope_gates_pending' if pending else 'C5_R7_full986_writer_whole_SYN_original139_pre_route_gates_admitted',
        offline_route_admitted=not pending,pending_before_start=pending,
        actual_SYN_resources=area,baseline_SYN_resources=old,SYN_resource_delta={k:area[k]-old[k] for k in area},
        frozen_RP_capacity=limits,remaining_RP_from_SYN_not_final_route=remaining,
        candidate_DCP_archive=archive.relative_to(ROOT).as_posix(),candidate_DCP_archive_SHA256=sha(archive),
        candidate_DCP_member=member,candidate_DCP_SHA256=digest,
        frozen_static_DCP_SHA256=STATIC,five_full_PR_reference_config_SHA256=REFERENCES,
        original_100MHz_clock1830_boundary_bits_and_control8_ABI_preserved=True,
        future_inputs_must_stream_from_existing_archive_or_files_no_duplicate_local_DCP_extraction=True,
        only_necessary_partial_firmware_and_reports_retained_after_all_owned_bytes_collected=True,
        no_current_server_board_UI_or_release_changed=True,source_and_evidence_SHA256=files,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)

def admit():
    value=inspect()
    if not value['offline_route_admitted']:raise RuntimeError('Complete986 RTL, qualified R7 writer IP, actual whole R7 SYN and original typed139 model required before physical route')
    return value

if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'tools'));import project_storage;project_storage.check(1_000_000)
    value=inspect();target=HERE/'prepared_review_r1.json';assert not target.exists()
    with target.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps({k:value[k] for k in ('offline_route_admitted','pending_before_start','actual_SYN_resources','remaining_RP_from_SYN_not_final_route')}),flush=True)
