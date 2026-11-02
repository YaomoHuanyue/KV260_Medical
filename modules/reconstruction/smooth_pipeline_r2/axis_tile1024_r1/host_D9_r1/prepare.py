"""Derive the complete D9 XRT bridge, preserving original ownership and drain checks."""
from pathlib import Path
import ast
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OLD = HERE.parents[1] / 'axis_load4_r1/host_D8_r1'
sys.path.insert(0, str(ROOT / 'tools'))
import project_storage


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def derive(parent, target, extra=()):
    original = parent.read_text()
    source = original
    edits = []
    for before, after in [('D8', 'D9'), ('smooth_d8', 'smooth_d9'), *extra]:
        count = source.count(before)
        if count == 0:
            assert (before, after) in [('D8', 'D9'), ('smooth_d8', 'smooth_d9')], (parent, before)
            continue
        source = source.replace(before, after)
        edits.append(dict(before=before, after=after, count=count))
    reverse = source
    for edit in reversed(edits):
        assert reverse.count(edit['after']) == edit['count'], (parent, edit)
        reverse = reverse.replace(edit['after'], edit['before'])
    assert reverse.encode() == parent.read_bytes(), 'Unexpected source encoding or algorithm change'
    if target.suffix == '.py':
        ast.parse(source)
    if target.exists():
        assert target.read_bytes() == source.encode(), 'Refuse changed partial derived source'
    else:
        target.write_text(source, encoding='utf-8', newline='\n')
    return dict(parent=parent.relative_to(ROOT).as_posix(), parent_SHA256=sha(parent),
        generated=target.relative_to(ROOT).as_posix(), generated_SHA256=sha(target), edits=edits)


def main():
    project_storage.check(2_000_000)
    hardware = HERE / 'hardware_r1'
    assert not (hardware / 'build_inputs_r1.json').exists()
    hardware.mkdir(exist_ok=True)
    records = []
    for leaf in ('protocol.hpp', 'driver.hpp', 'graph_memory.hpp', 'register_port.hpp', 'xrt_memory.hpp',
                 'test_control.cpp', 'test_memory.cpp'):
        edits = []
        if leaf in ('register_port.hpp', 'test_control.cpp'):
            edits.append(('0xd800', '0xd900'))
        if leaf == 'test_control.cpp':
            edits.append(('0xc2u,0xd7u,0u', '0xc2u,0xd7u,0xd8u,0u'))
        records.append(derive(OLD / leaf, HERE / leaf, edits))
    session_records = []
    for leaf in ('session.hpp', 'require.hpp', 'file_io.hpp'):
        edits = []
        if leaf == 'session.hpp':
            edits.extend([
                ('axis_load4_r1/host_D9_r1', 'axis_tile1024_r1/host_D9_r1'),
                ('identity==0xd8)', 'identity==0xd8||identity==0xd9)'),
                ('name=="axis_smooth"?0xd8', 'name=="axis_smooth"?0xd9')])
        row = derive(OLD / 'hardware_r1' / leaf, hardware / leaf, edits)
        records.append(row)
        session_records.append(row)
    for leaf in ('bridge.cpp', 'build_on_board.py'):
        records.append(derive(OLD / 'hardware_r1' / leaf, hardware / leaf))
    value = dict(derivations=session_records, original_D8_parent_not_modified=True,
        root_static_lock_DMA_idle_isolation_sentinel_count_boot_and_low_DDR_checks_preserved=True,
        D9_identity217_only_for_new_partial_selection=True, old_D8_known_idle_quiesce_still_allowed=True,
        legacy_C2_guards_unchanged=True, PL_accessed=False, whole_goal_completed=False)
    (hardware / 'session_derivation.json').write_text(json.dumps(value, indent=2) + '\n')
    source = dict(status='D9_complete_XRT_bridge_and_original_control_memory_tests_derived_not_compiled',
        derivations=records, source_SHA256=sha(Path(__file__)),
        original_control_and_memory_test_bodies_preserved_except_identity_and_labels=True,
        extra_old_D8_identity_rejection_case_added=True, algorithm_source_not_linked_in_XRT_bridge=True,
        no_firmware_or_release_created=True, production_promoted=False, whole_goal_completed=False)
    (HERE / 'derivation.json').write_text(json.dumps(source, indent=2) + '\n')
    files = {Path(__file__), HERE / 'derivation.json', hardware / 'session_derivation.json', HERE.parent / 'mesh_smooth.hpp'}
    files.update(ROOT / row[key] for row in records for key in ('parent', 'generated'))
    (hardware / 'build_inputs_r1.json').write_text(json.dumps(
        {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(files)}, indent=2) + '\n')
    print('PASS D9 complete XRT sources derived; identity217; original drain, guards, lock and pre-hardware root checks preserved')


if __name__ == '__main__':
    main()
