"""Reopen every saved R11/R12 output and prove optimization equivalence."""
from pathlib import Path
import argparse,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json,arrays
from modules.surface_route.test_comparison_r12 import without_reuse


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--platform',choices=['Windows','ARM'],required=True);a=ap.parse_args()
    name='comparison_own_CT_Windows_all_r11' if a.platform=='Windows' else 'comparison_own_CT_ARM_r11'
    old=ROOT/'modules/surface_route/results'/name
    new=ROOT/'modules/surface_route/results'/f'comparison_own_CT_{a.platform}_r12'
    output=ROOT/'modules/surface_route/results'/f'comparison_equivalence_{a.platform}_r12.json'
    assert not output.exists()
    before=json.loads((old/'acceptance.json').read_text());after=json.loads((new/'acceptance.json').read_text())
    assert len(before['cases'])==len(after['cases'])==4
    expected={r['label']:r for r in before['cases']};rows=[]
    for current in after['cases']:
        label=current['label'];previous=expected[label]
        for base,record in ((old,previous),(new,current)):
            for name,digest in record['files_sha256'].items():assert sha(base/label/name)==digest,name
            assert json.loads((base/label/'report.json').read_text())==record
        for name in ('whole_instrument_profiles.json','whole_alternative_routes.json'):
            lhs=json.loads((old/label/name).read_text());rhs=json.loads((new/label/name).read_text())
            assert without_reuse(lhs)==without_reuse(rhs),name
        lhs=arrays(old/label/'whole_comparison_arrays.npz');rhs=arrays(new/label/'whole_comparison_arrays.npz')
        assert set(lhs)==set(rhs)
        for name in lhs:np.testing.assert_array_equal(lhs[name],rhs[name],err_msg=label+'/'+name)
        improved={p:previous['medians'][p]['full_report_API_seconds']/current['medians'][p]['full_report_API_seconds'] for p in previous['medians']}
        rows.append(dict(label=label,all_report_fields_and_saved_arrays_exact=True,
            baseline_medians=previous['medians'],optimized_medians=current['medians'],
            same_provider_complete_API_speedup=improved,
            actual_PL_tested=after['PL_access'],
            PL_over_strongest_PS_full_API_speedup=current.get('PL_over_strongest_PS_full_API_speedup'),
            PL_over_strongest_PS_solve_API_speedup=current.get('PL_over_strongest_PS_solve_API_speedup')))
    evidence=[old/'acceptance.json',new/'acceptance.json']
    write_json(output,dict(status='four_actual_surface_full_R11_R12_reports_and_arrays_exact',platform=a.platform,cases=rows,
        evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in evidence},source_sha256=sha(Path(__file__)),
        optimized_only_same_immutable_root_winding_reuse=True,
        no_candidate_wall_check_or_mask_interval_or_weight_rule_removed=True,
        production_promoted=False,UI_integration_pending=True))
    print('four scenes exact; complete API speedups',[(r['label'],r['same_provider_complete_API_speedup']) for r in rows],flush=True)


if __name__=='__main__':main()
