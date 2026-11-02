"""Also keep the opaque Qt canvas alpha intact during nearest-shell blending."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    closure=json.loads((HERE/'source_closure_fast_opacity_r1.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[group].items():assert sha(ROOT/n)==d,n
    s=(HERE/'src/views_fast_opacity_r1.cpp').read_text(encoding='utf-8')
    a='glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);';assert s.count(a)==1
    s=s.replace(a,'// RGB uses source-over; alpha stays opaque for the Qt canvas.\n   glEnable(GL_BLEND);glBlendFuncSeparate(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_ONE,GL_ONE_MINUS_SRC_ALPHA);')
    s=s.replace('fast_opacity_regression_r1.inc','fast_opacity_regression_r2.inc')
    save('src/views_fast_opacity_r2.cpp',s)
    s=(HERE/'src/fast_opacity_regression_r1.inc').read_text(encoding='utf-8')
    a='bool good=stencil>=8&&widgetStencil>=8&&order.first<=total*.002&&formula.first<=total*.002;';assert s.count(a)==1
    s=s.replace(a,'bool opaqueCanvas=true;for(int y=0;y<a.first.height();++y){auto p=a.first.constScanLine(y);for(int x=0;x<a.first.width();++x)opaqueCanvas=opaqueCanvas&&p[4*x+3]==255;}\n    bool good=opaqueCanvas&&stencil>=8&&widgetStencil>=8&&order.first<=total*.002&&formula.first<=total*.002;')
    s=s.replace('{"passed",good}','{"framebuffer_alpha_preserved",opaqueCanvas},{"passed",good}')
    save('src/fast_opacity_regression_r2.inc',s)
    s=(HERE/'build_fast_opacity_r1.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r1','build_fast_opacity_r2').replace('source_closure_fast_opacity_r1','source_closure_fast_opacity_r2').replace('src/views_fast_opacity_r1.cpp','src/views_fast_opacity_r2.cpp')
    save('build_fast_opacity_r2.sh',s)
    save('run_fast_opacity_r2.sh',(HERE/'run_fast_opacity_r1.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r1','build_fast_opacity_r2'))
    closure['source_sha256']=dict(closure['source_sha256'])
    for n in ('prepare_fast_opacity_r2.py','src/views_fast_opacity_r2.cpp','src/fast_opacity_regression_r2.inc','build_fast_opacity_r2.sh','run_fast_opacity_r2.sh'):
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='nearest_shell_depth_and_opaque_canvas_alpha_fix_candidate')
    save('source_closure_fast_opacity_r2.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
