"""Verify every owned route byte; retain new artifacts and alias existing inputs."""
from pathlib import Path, PureWindowsPath
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import collect_AXIS_DFX_area_dedup_r2 as helper
parent = helper.parent
parent.OUT = ROOT / 'results/smooth_AXIS_D8_PR_r1/smooth'
AREA = ROOT / 'results/smooth_AXIS_DFX_area_r2/smooth_area/current_candidate.zip'
helper.CANONICAL.append(AREA)


def owner_check(owner):
    win = PureWindowsPath(owner['windows_root'])
    assert win.parent == PureWindowsPath('D:/') and win.name == owner['name']
    assert win.name.startswith('k26-r2602-') and len(win.name) == 26
    assert all(c in '0123456789abcdef' for c in win.name[10:])
    assert owner['remote_root'] == '/' + win.as_posix() and owner['job'] == 'smooth' == parent.OUT.name
    return win, owner['remote_root']


def necessary(names, archive, plan):
    selected = set(json.loads((parent.OUT / 'upload_plan.json').read_text())['payload_sha256']) | set(plan['input_manifest'])
    selected.update(name for name in names if name in ('terminal.json', 'state.json', 'worker_started.json',
        'own_worker_affinity.json', 'task_started.json', 'raw_task_receipt.json', 'task.log', 'release.json'))
    prefix = 'workspace/dfx/smooth_speed/route_D8_r1/'
    for location in (prefix, prefix + 'build/'):
        selected.update(name for name in names if name.startswith(location) and '/' not in name[len(location):]
            and name.endswith(('.json', '.log', '.jou', '.rpt', '.dcp', '.bit', '.bin', '.txt', '.tcl', '.py')))
    candidate = prefix + 'input/qualified_D8_RM.dcp'
    if candidate in names:
        selected.add(candidate)
    complete = prefix + 'complete.json'
    if complete in names:
        result = json.loads(archive.read(complete))
        selected.update('workspace/' + name for name in result['source_and_evidence_SHA256'])
    assert selected <= set(names)
    return selected


old_select = helper.select


def select(names, archive, plan):
    selected = old_select(names, archive, plan)
    direct = {parent.sha(AREA): AREA, parent.sha(ROOT / 'dfx/medical/build/static_routed.dcp'): ROOT / 'dfx/medical/build/static_routed.dcp'}
    for ref in ('mc', 'smooth', 'edt', 'route', 'ct'):
        path = ROOT / ('dfx/medical/build/config_' + ref + '.dcp')
        direct[parent.sha(path)] = path
    for name in list(selected):
        if names[name] in direct:
            path = direct[names[name]]
            selected.remove(name)
            parent.COLLECTED_ALIASES['logical_aliases'][name] = dict(kind='canonical_file',
                path=path.relative_to(ROOT).as_posix(), SHA256=names[name])
    return selected


parent.check_owner = owner_check
helper.ORIGINAL_SELECT = necessary
helper.select = select
if __name__ == '__main__':
    helper.main()
