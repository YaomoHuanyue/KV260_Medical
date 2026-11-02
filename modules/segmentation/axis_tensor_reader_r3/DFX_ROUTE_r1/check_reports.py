"""C5 physical report reader using the unchanged qualified 100 MHz/PR parser."""
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parents[2]
PARENT = ROOT / 'modules/reconstruction/mesh_topology_r1/axis_directed_portable_r3/dfx_static_adapter_route_r1/check_reports.py'
spec = importlib.util.spec_from_file_location('qualified_physical_reports_for_C5', PARENT)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
require, sha, physical_reports = parent.require, parent.sha, parent.physical_reports
REFERENCES = parent.REFERENCES
CANDIDATE = 'config_ct_tensor_r3'
ARTIFACTS = tuple(CANDIDATE + suffix for suffix in
                  ('.dcp', '.bit', '.bin', '_pblock_rp_partial.bit', '_pblock_rp_partial.bin'))
PARTIALS = ARTIFACTS[-2:]
REPORTS = ('timing_ct_tensor_r3.rpt', 'drc_ct_tensor_r3.rpt', 'utilization_ct_tensor_r3.rpt',
           'capacity_ct_tensor_r3.rpt') + tuple('pr_verify_ct_tensor_r3_' + role + '.log' for role in REFERENCES)
MARKER = 'OFFLINE_COMPLETE_ct_tensor_r3.txt'


def check_pr(text, reference):
    return parent.check_pr(text, reference, candidate=CANDIDATE)


def verify_build(build):
    build = Path(build)
    read = lambda name: (build / name).read_text(errors='replace')
    result = physical_reports(*(read(name) for name in REPORTS[:3]))
    result['five_reference_full_PR'] = [check_pr(read('pr_verify_ct_tensor_r3_' + role + '.log'), role)
                                        for role in REFERENCES]
    for name in ARTIFACTS + REPORTS + (MARKER,):
        require((build / name).is_file() and (build / name).stat().st_size > 0, 'Missing current artifact: ' + name)
    result.update(status='actual_C5_100MHz_route_full5_PR_and_firmware_outputs_verified_not_board',
        artifact_SHA256={name: sha(build / name) for name in ARTIFACTS + REPORTS + (MARKER,)},
        PL_accessed=False, production_promoted=False, whole_goal_completed=False)
    return result
