"""Bind added real-button/backend test coverage without changing algorithms."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    prior=HERE/'source_closure_r6_2.json';r=json.loads(prior.read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in r[key].items():assert sha(ROOT/n)==d,n
    for name in ('build','run'):
        expected=(HERE/(name+'_r6_2.sh')).read_text(encoding='utf-8').replace('build_r6_2','build_r6_3').replace('source_closure_r6_2','source_closure_r6_3').replace('main_r6_2.cpp','main_r6_3.cpp')
        assert (HERE/(name+'_r6_3.sh')).read_text(encoding='utf-8')==expected
    main=(HERE/'src/main_r6_3.cpp').read_text(encoding='utf-8')
    assert 'wholeComparisonTestStarted=true;QTest::mouseClick(compareButton,Qt::LeftButton)' in main
    names=('src/main_r6_3.cpp','build_r6_3.sh','run_r6_3.sh','record_comparison_trial_r3.py')
    r['source_sha256'].update({(HERE/n).relative_to(ROOT).as_posix():sha(HERE/n) for n in names})
    r.update(test_mode='Actual Qt comparison button starts async PL EDT/audit/camera task before original whole profile chart and all full-path previews',
        previous_source_closure_sha256=sha(prior),production_UI_unchanged=True,
        report_producer_or_PL_algorithms_changed=False)
    p=HERE/'source_closure_r6_3.json';assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print('R6 real-button comparison trial bound',len(r['source_sha256']))

if __name__=='__main__':main()
