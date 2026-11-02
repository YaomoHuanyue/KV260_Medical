"""Derive D9 physical/collection recipes without changing numerical or timing gates."""
from pathlib import Path
import ast
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORE = ROOT / 'modules/reconstruction/smooth_pipeline_r2/axis_tile1024_r1'
OLD_CORE = CORE.parent / 'axis_load4_r1'
sys.path.insert(0, str(ROOT / 'tools'))
import project_storage


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def derive(parent, target, edits):
    source = parent.read_text()
    records = []
    for before, after in edits:
        count = source.count(before)
        assert count > 0, (parent, before)
        source = source.replace(before, after)
        records.append(dict(before=before, after=after, count=count))
    reverse = source
    for edit in reversed(records):
        assert reverse.count(edit['after']) == edit['count']
        reverse = reverse.replace(edit['after'], edit['before'])
    assert reverse == parent.read_text()
    if target.suffix == '.py':
        ast.parse(source)
    if target.exists():
        assert target.read_bytes() == source.encode('utf-8'), 'Refuse changed partial derivation: ' + str(target)
    else:
        target.write_text(source, encoding='utf-8', newline='\n')
    return dict(parent=parent.relative_to(ROOT).as_posix(), parent_SHA256=sha(parent),
                candidate=target.relative_to(ROOT).as_posix(), candidate_SHA256=sha(target),
                literal_edits=records, reverse_byte_exact=True)


def main():
    project_storage.check(1_000_000)
    assert not (HERE / 'derivation.json').exists()
    records = []
    old = ROOT / 'dfx/smooth_speed/route_D8_r1'
    for name in ('check_reports.py', 'implement_D8_r1.tcl', 'run.py'):
        records.append(derive(old / name, HERE / name.replace('D8', 'D9'), [('D8', 'D9')]))
    records.append(derive(old / 'private.py', HERE / 'private.py', [
        ('D8', 'D9'),
        ('results/smooth_AXIS_DFX_area_r2/smooth_area/current_candidate.zip',
         'results/smooth_AXIS_D9_tile1024_area_r2/smooth_area/current_candidate_dedup_r1.zip')]))
    parent_collector = ROOT / 'tools/collect_D8_route_r1.py'
    before = '''    for name in list(selected):
        if names[name] in direct:
            path = direct[names[name]]
            selected.remove(name)
            parent.COLLECTED_ALIASES['logical_aliases'][name] = dict(kind='canonical_file',
                path=path.relative_to(ROOT).as_posix(), SHA256=names[name])
    return selected'''
    after = '''    from canonical_alias_promotion_r1 import promote_files
    return promote_files(selected, parent.COLLECTED_ALIASES, names, direct, ROOT)'''
    records.append(derive(parent_collector, ROOT / 'tools/collect_D9_route_r1.py', [
        ('D8', 'D9'),
        ('results/smooth_AXIS_DFX_area_r2/smooth_area/current_candidate.zip',
         'results/smooth_AXIS_D9_tile1024_area_r2/smooth_area/current_candidate_dedup_r1.zip'),
        (before, after)]))
    records.append(derive(OLD_CORE / 'flow_RTL_r1/verify_collected.py',
        CORE / 'flow_RTL_r1/verify_collected.py',
        [('D8', 'D9'),
         ('results/smooth_AXIS_flow_RTL_r1/axis_rtl', 'results/smooth_AXIS_D9_flow_RTL_r1/axis_rtl')]))
    records.append(derive(OLD_CORE / 'full_RTL_monitored_r3/verify_collected.py',
        CORE / 'full_RTL_monitored_r1/verify_collected.py',
        [('D8', 'D9'),
         ('results/smooth_AXIS_monitored_full_RTL_r3/axis_rtl', 'results/smooth_AXIS_D9_monitored_full_RTL_r2/axis_rtl'),
         ("HERE.parent/'flow_RTL_r1/verify_collected.py'", "ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_load4_r1/flow_RTL_r1/verify_collected.py'"),
         ("HERE.parent/'full_RTL_r2/fixtures.py'", "ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_load4_r1/full_RTL_r2/fixtures.py'"),
         ('results/smooth_AXIS_official_setup_r1/axis_setup/current_candidate.zip', 'results/smooth_AXIS_D9_official_setup_r1/axis_setup/current_candidate.zip'),
         ('official=view_module.View(stack,official_path)', "official=load('exact_D9_plain_setup_view',HERE.parent/'official_setup_r1/archive_view.py').View(stack,official_path)"),
         ('workspace/d8_setup/component/', 'workspace/d9_setup/component/')]))
    result = dict(status='D9_exact_original_physical_and_numeric_validator_recipes_derived_not_executed',
        records=records, source_SHA256=sha(Path(__file__)),
        original14_and6422850_words_and_both_C_posts_and4_monitors_unchanged=True,
        original40_and18351000_words_and_fault_reset_guards_unchanged=True,
        original100MHz_setup_hold_DRC_capacity_five_full_PR_and_five_artifacts_unchanged=True,
        plain_fresh_D9_setup_reader_checks_manifest_and_member_SHA256=True,
        corrected_prepublication_derivation_order_collision=True,
        actual_RTL_route_and_board_gates_not_claimed=True, production_promoted=False, whole_goal_completed=False)
    (HERE / 'derivation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PASS reversible D9 source recipes; actual RTL and route gates remain')


if __name__ == '__main__':
    main()
