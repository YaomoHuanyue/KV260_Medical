"""Mark depth-prepass winners and match the opaque oracle's object priority."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    closure=json.loads((HERE/'source_closure_fast_opacity_r2.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[group].items():assert sha(ROOT/n)==d,n
    s=(HERE/'src/views_fast_opacity_r2.cpp').read_text(encoding='utf-8')
    a='''   glDisable(GL_BLEND);glDepthMask(GL_TRUE);glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
   glDrawArrays(GL_TRIANGLES,0,m.count);
   glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
   // Quantized equal depths and shared triangle edges must blend only once.
   glStencilMask(0xff);glClearStencil(0);glClear(GL_STENCIL_BUFFER_BIT);
   glEnable(GL_STENCIL_TEST);glStencilFunc(GL_EQUAL,0,0xff);glStencilOp(GL_KEEP,GL_KEEP,GL_INCR);'''
    b='''   glDisable(GL_BLEND);glDepthMask(GL_TRUE);glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
   glStencilMask(0xff);glClearStencil(0);glClear(GL_STENCIL_BUFFER_BIT);
   glEnable(GL_STENCIL_TEST);glStencilFunc(GL_ALWAYS,1,0xff);glStencilOp(GL_KEEP,GL_KEEP,GL_REPLACE);
   glDrawArrays(GL_TRIANGLES,0,m.count);
   glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
   // Only pixels won by lung depth may blend; consume each winner once.
   // A lung fragment tied with a closer opaque structure cannot cover it.
   glStencilFunc(GL_EQUAL,1,0xff);glStencilOp(GL_KEEP,GL_KEEP,GL_ZERO);'''
    assert s.count(a)==1;s=s.replace(a,b).replace('fast_opacity_regression_r2.inc','fast_opacity_regression_r3.inc')
    save('src/views_fast_opacity_r3.cpp',s)
    s=(HERE/'src/fast_opacity_regression_r2.inc').read_text(encoding='utf-8')
    a='''   meshes[1]=saved[0];meshes[1].attributes.clear();meshes[1].attributeVbo=0;
   meshes[0].visible=meshes[2].visible=false;drawMeshes(p*v,v);
   for(int k=0;k<3;++k)meshes[k]=saved[k];meshes[0].visible=false;drawMeshes(p*v,v);meshes[0]=saved[0];'''
    b='''   // Match the application's airway/lesion-before-lung tie priority.
   meshes[0].visible=false;drawMeshes(p*v,v);
   for(int k=0;k<3;++k)meshes[k]=saved[k];
   meshes[1]=saved[0];meshes[1].attributes.clear();meshes[1].attributeVbo=0;
   meshes[0].visible=meshes[2].visible=false;drawMeshes(p*v,v);
   for(int k=0;k<3;++k)meshes[k]=saved[k];'''
    assert s.count(a)==1;s=s.replace(a,b)
    s=s.replace('// then draw airway/lesions against that depth. No transparency fix is used.','// after airway/lesions. No transparency fix is used.')
    save('src/fast_opacity_regression_r3.inc',s)
    save('build_fast_opacity_r3.sh',(HERE/'build_fast_opacity_r2.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r2','build_fast_opacity_r3').replace('source_closure_fast_opacity_r2','source_closure_fast_opacity_r3').replace('src/views_fast_opacity_r2.cpp','src/views_fast_opacity_r3.cpp'))
    save('run_fast_opacity_r3.sh',(HERE/'run_fast_opacity_r2.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r2','build_fast_opacity_r3'))
    closure['source_sha256']=dict(closure['source_sha256'])
    for n in ('prepare_fast_opacity_r3.py','src/views_fast_opacity_r3.cpp','src/fast_opacity_regression_r3.inc','build_fast_opacity_r3.sh','run_fast_opacity_r3.sh'):
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='nearest_shell_depth_winner_and_opaque_canvas_alpha_fix_candidate',opaque_object_tie_priority_preserved=True)
    save('source_closure_fast_opacity_r3.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
