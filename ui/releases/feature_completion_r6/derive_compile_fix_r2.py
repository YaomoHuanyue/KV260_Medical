"""Keep failed first compilation intact; change only the shadowed QWidget call."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    prior=HERE/'source_closure_r6.json';r=json.loads(prior.read_text(encoding='utf-8'))
    for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in r[key].items():assert sha(ROOT/n)==d,n
    source=HERE/'src/main_r6.cpp';s=source.read_text(encoding='utf-8')
    old='if(!failed)showComparisons();close();if(failed)QApplication::exit(1);'
    assert s.count(old)==1
    new=HERE/'src/main_r6_2.cpp';assert not new.exists()
    new.write_text(s.replace(old,'if(!failed)showComparisons();this->close();if(failed)QApplication::exit(1);'),encoding='utf-8',newline='\n')
    build=(HERE/'build_r6.sh').read_text(encoding='utf-8')
    build=build.replace('build_r6','build_r6_2').replace('source_closure_r6','source_closure_r6_2').replace('main_r6.cpp','main_r6_2.cpp')
    p=HERE/'build_r6_2.sh';assert not p.exists();p.write_text(build,encoding='utf-8',newline='\n')
    run=(HERE/'run_r6.sh').read_text(encoding='utf-8').replace('build_r6','build_r6_2')
    p=HERE/'run_r6_2.sh';assert not p.exists();p.write_text(run,encoding='utf-8',newline='\n')
    new_names=['ui/releases/feature_completion_r6/'+n for n in ('src/main_r6_2.cpp','build_r6_2.sh','run_r6_2.sh','derive_compile_fix_r2.py')]
    r['source_sha256'].update({n:sha(ROOT/n) for n in new_names})
    r.update(previous_source_closure_sha256=sha(prior),first_compile_failure_retained=True,
             compile_fix='Explicit this->close() avoids local QPushButton* close shadowing QWidget::close',
             algorithms_or_parameters_changed=False)
    p=HERE/'source_closure_r6_2.json';assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print('New immutable R6 compile-fix sources:',len(new_names))


if __name__=='__main__':main()
