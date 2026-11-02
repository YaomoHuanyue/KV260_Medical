"""Keep actual per-export cancellation separate from cumulative test coverage."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;UI=ROOT/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf-8',newline='\n')
def replace(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)
def main():
    old=json.loads((UI/'source_closure_media_r2.json').read_text())
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in old[group].items():assert sha(ROOT/n)==d,n
    feature=(HERE/'UI_feature_r2.inc').read_text(encoding='utf-8')
    feature=replace(feature,'bool videoSavedPlaying=false,videoSavedDual=false;',
        'bool videoSavedPlaying=false,videoSavedDual=false,videoCancelledAtPL=false;')
    feature=replace(feature,'videoIndex=videoRendered=0;', 'videoCancelledAtPL=false;videoIndex=videoRendered=0;')
    feature=replace(feature,'return;videoCancelled=true;', 'return;videoCancelledAtPL=videoAwaiting;videoCancelled=true;')
    feature=feature.replace('{"cancel_requested_while_awaiting_PL",videoTestCancelAwaiting}',
        '{"cancel_requested_while_awaiting_PL",videoCancelledAtPL}')
    feature=replace(feature,'{"UI_ticks",ticks},', '{"UI_ticks",ticks},{"error",videoError},')
    save(HERE/'UI_feature_r3.inc',feature)
    for part in ('main','views'):
        for extension in (('cpp',) if part=='main' else ('cpp','hpp')):
            p=UI/('src/'+part+'_media_r3.'+extension)
            s=(UI/('src/'+part+'_media_r2.'+extension)).read_text(encoding='utf-8')
            s=s.replace('views_media_r2.hpp','views_media_r3.hpp').replace('UI_feature_r2.inc','UI_feature_r3.inc')
            save(p,s)
    for name in ('build_media_r3.sh','run_media_r3.sh'):
        save(UI/name,(UI/name.replace('r3','r2')).read_text(encoding='utf-8').replace('media_r2','media_r3'))
    new=dict(old,status='accepted_R4_UI_plus_native_video_with_per_session_cancel_report',source_sha256=dict(old['source_sha256']))
    files=[HERE/'UI_feature_r3.inc',HERE/'prepare_UI_r3.py']+[UI/n for n in ('src/main_media_r3.cpp','src/views_media_r3.cpp','src/views_media_r3.hpp','build_media_r3.sh','run_media_r3.sh')]
    for p in files:new['source_sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
    save(UI/'source_closure_media_r3.json',json.dumps(new,indent=2)+'\n')
    test=(HERE/'test_native_UI_r2.py').read_text(encoding='utf-8').replace('_r2','_r3')
    test=replace(test,"PRODUCTION/'results/fast_opacity_promoted_r4.json'","HERE/'results/native_UI_restored_r2.json'")
    test=replace(test,"assert entries[2]['cancel_requested_while_awaiting_PL']", "assert entries[2]['cancel_requested_while_awaiting_PL']\n                assert not entries[1]['cancel_requested_while_awaiting_PL'] and not entries[3]['cancel_requested_while_awaiting_PL']")
    save(HERE/'test_native_UI_r3.py',test)
    verifier=(HERE/'verify_native_export_r2.py').read_text(encoding='utf-8')
    save(HERE/'verify_native_export_r3.py',verifier)
    p=ROOT/'ui/production_r1'
    prepare=(p/'prepare_media_release_r2.py').read_text().replace('_r2','_r3')
    save(p/'prepare_media_release_r3.py',prepare)
    promote=(p/'promote_media_r2.py').read_text().replace('_r2','_r3')
    save(p/'promote_media_r3.py',promote)
    print('Per-export cancellation is independent of prior test sessions')
if __name__=='__main__':main()
