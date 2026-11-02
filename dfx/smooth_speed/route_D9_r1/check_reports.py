"""Strict offline D9 physical gates; never assert board qualification."""
from pathlib import Path
import hashlib
import json
import re

BUDGET = dict(LUT=88320, FF=176640, DSP=960, BRAM36_equivalent=132, URAM=64)
REFERENCES = ('mc', 'smooth', 'edt', 'route', 'ct')
CANDIDATE = 'config_smooth_D9_r1'
ARTIFACTS = tuple(CANDIDATE + suffix for suffix in
                  ('.dcp', '.bit', '.bin', '_pblock_rp_partial.bit', '_pblock_rp_partial.bin'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resource_row(text, instance):
    header = None
    matches = []
    for line in text.splitlines():
        row = [v.strip() for v in line.split('|')[1:-1]]
        if row and row[0] == 'Instance' and 'Total LUTs' in row:
            header = row
        if header and row and row[0] == instance:
            fields = dict(zip(header, row))
            columns = dict(LUT='Total LUTs', FF='FFs', DSP='DSP Blocks',
                           BRAM36='RAMB36', BRAM18='RAMB18', URAM='URAM')
            matches.append({key: int(fields[col].replace(',', '')) for key, col in columns.items()})
    require(len(matches) == 1, 'Expected one actual routed resource row: ' + instance)
    require(all(v >= 0 for v in matches[0].values()), 'Negative resource count')
    return matches[0]


def physical_reports(timing, drc, util):
    require(re.search(r'Tool Version\s*:\s*Vivado v\.2025\.2\.1\b', timing), 'Wrong Vivado version')
    require(re.search(r'Design State\s*:\s*Routed\b', timing), 'Timing report is not routed')
    require(re.search(r'Design\s*:\s*system_top\b', timing), 'Wrong design')
    match = re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+[-\d.]+\s+\d+\s+\d+\s+([-\d.]+)', timing, re.S)
    require(match is not None, 'Missing setup/hold summary')
    wns, whs = map(float, match.groups())
    require(wns >= 0 and whs >= 0, 'Negative setup/hold slack')
    require('All user specified timing constraints are met.' in timing, 'Timing constraints failed')
    for clock in ('clk_pl_0', 'clk_pl_1'):
        require(re.search(r'^' + clock + r'\s+\{0\.000 5\.000\}\s+10\.000\s+100\.000\s*$', timing, re.M),
                'Missing original 100 MHz clock: ' + clock)
    for name in ('no_clock', 'unconstrained_internal_endpoints', 'multiple_clock', 'loops', 'latch_loops'):
        counts = re.findall(r'checking ' + name + r' \((\d+)\)', timing)
        require(bool(counts) and all(int(n) == 0 for n in counts), 'Timing check failed: ' + name)
    require(not re.search(r'\|\s*(?:Error|Critical Warning)\s*\|', drc, re.I), 'DRC error/critical warning')
    require(re.search(r'Design State\s*:\s*Fully Routed\b', drc), 'DRC report is not fully routed')
    whole, rp = resource_row(util, 'system_top'), resource_row(util, 'rp')
    used = {key: rp[key] for key in ('LUT', 'FF', 'DSP', 'URAM')}
    used['BRAM36_equivalent'] = rp['BRAM36'] + rp['BRAM18'] / 2
    remaining = {key: limit - used[key] for key, limit in BUDGET.items()}
    require(all(v >= 0 for v in remaining.values()), 'DFX region capacity exceeded')
    return dict(clock_MHz=100, WNS_ns=wns, WHS_ns=whs,
                whole_resources=whole, RP_resources=rp, remaining_RP=remaining)


def check_pr(log, reference, candidate=CANDIDATE):
    require(reference in REFERENCES, 'Unknown reference')
    require(not re.search(r'(?m)^\s*(?:ERROR|FATAL)\s*[:\[]', log), 'PR verification error')
    pattern = (r'PR_VERIFY: check points\s+[^\r\n]*[/\\]config_' + re.escape(reference) +
               r'\.dcp and\s+[^\r\n]*[/\\]' + re.escape(candidate) + r'\.dcp are compatible')
    require(len(re.findall(pattern, log)) == 1, 'Missing exact full PR compatibility: ' + reference)
    require('pr_verify -full_check ' in log, 'Full PR mode not proven')
    require('PR Verify Summary:' in log, 'Missing actual PR comparison summary')
    return dict(reference=reference, full_check_passed=True)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_build(build):
    build = Path(build)
    read = lambda name: (build / name).read_text(errors='replace')
    result = physical_reports(read('timing_D9_r1.rpt'), read('drc_D9_r1.rpt'), read('utilization_D9_r1.rpt'))
    result['five_reference_full_PR'] = [check_pr(read('pr_verify_D9_r1_' + ref + '.log'), ref) for ref in REFERENCES]
    names = ARTIFACTS + ('OFFLINE_COMPLETE_D9_r1.txt',)
    for name in names:
        require((build / name).is_file() and (build / name).stat().st_size > 0, 'Missing artifact: ' + name)
    result.update(status='D9_offline_100MHz_route_five_reference_fullPR_and_five_artifacts_verified',
                  artifact_SHA256={name: sha(build / name) for name in names},
                  ARM_native_and_XRT_and_board_PS4_and_release_still_pending=True,
                  PL_accessed=False, production_promoted=False, whole_goal_completed=False)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('build', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_build(args.build), indent=2))
