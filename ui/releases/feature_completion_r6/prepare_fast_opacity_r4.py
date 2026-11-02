"""Keep the corrected surface while removing repeated transparent geometry."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n;assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
def main():
    closure=json.loads((HERE/'source_closure_fast_opacity_r3.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in closure[group].items():assert sha(ROOT/n)==d,n
    h=(HERE/'src/views_fast_opacity_r1.hpp').read_text(encoding='utf-8')
    h=h.replace(' void drawMeshes(', ' std::unique_ptr<QOpenGLFramebufferObject> normalBackground,normalNearest;QOpenGLShaderProgram normalShellShader;QByteArray normalShellKey;int normalShellGeometryBuilds=0,normalShellCompositions=0;\n void drawNormalOverview(const QMatrix4x4&,const QMatrix4x4&,int,int);\n void drawMeshes(')
    save('src/views_fast_opacity_r4.hpp',h)
    s=(HERE/'src/views_fast_opacity_r3.cpp').read_text(encoding='utf-8').replace('views_fast_opacity_r1.hpp','views_fast_opacity_r4.hpp')
    s=s.replace('makeCurrent();scopeColor.reset();','makeCurrent();normalBackground.reset();normalNearest.reset();normalShellShader.removeAllShaders();scopeColor.reset();')
    s=s.replace(' compositeFrame={};compositeInfo={};compositeDirty=true;', ' normalShellKey.clear();compositeFrame={};compositeInfo={};compositeDirty=true;')
    s=s.replace('void MeshView::paintGL(){','#include "fast_shell_cache_r1.inc"\nvoid MeshView::paintGL(){')
    s=s.replace('if(error.isEmpty())drawMeshes(lastMvp,view);','if(error.isEmpty())drawNormalOverview(lastMvp,view,viewportWidth,viewportHeight);')
    s=s.replace('fast_opacity_regression_r3.inc','fast_opacity_regression_r4.inc')
    save('src/views_fast_opacity_r4.cpp',s)
    s=(HERE/'src/main_fast_opacity_r1.cpp').read_text(encoding='utf-8').replace('views_fast_opacity_r1.hpp','views_fast_opacity_r4.hpp')
    save('src/main_fast_opacity_r4.cpp',s)
    s=(HERE/'src/fast_opacity_regression_r3.inc').read_text(encoding='utf-8')
    s=s.replace('}else drawMeshes(p*v,v);','}else{normalShellKey.clear();drawNormalOverview(p*v,v,512,384);}')
    marker=' // Original disk meshes are never edited; release temporary VBOs and restore UI.'
    assert s.count(marker)==1
    checks=''' // Opacity changes reuse geometry; a changed camera must invalidate it.
 normalShellKey.clear();clipEnabled=false;lungOpacity=.2f;render();int firstBuild=normalShellGeometryBuilds;
 QJsonArray cachedOpacity;bool cachePassed=true;
 for(float alpha:{.4f,.9f,.99f,.2f}){
  lungOpacity=alpha;target.bind();glViewport(0,0,512,384);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
  QMatrix4x4 v,p;v.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));v.translate(center);v.rotate(pitch,1,0,0);v.rotate(yaw,0,0,1);v.translate(-center);p.perspective(42,512.f/384,.1f,radius*12.f);
  auto start=std::chrono::steady_clock::now();drawNormalOverview(p*v,v,512,384);glFinish();auto cached=target.toImage().convertToFormat(QImage::Format_RGBA8888);double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  bool reused=normalShellGeometryBuilds==firstBuild;auto cold=render().first;auto diff=difference(cached,cold,0);
  bool good=reused&&diff.first==0;cachePassed=cachePassed&&good;firstBuild=normalShellGeometryBuilds;
  cachedOpacity.append(QJsonObject{{"alpha",alpha},{"geometry_reused",reused},{"cached_vs_cold_pixel_difference",diff.first},{"GPU_completed_seconds",seconds},{"passed",good}});
 }
 int beforePose=normalShellGeometryBuilds;yaw+=1;target.bind();glViewport(0,0,512,384);
 QMatrix4x4 changedView,changedProjection;changedView.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));changedView.translate(center);changedView.rotate(pitch,1,0,0);changedView.rotate(yaw,0,0,1);changedView.translate(-center);changedProjection.perspective(42,512.f/384,.1f,radius*12.f);
 drawNormalOverview(changedProjection*changedView,changedView,512,384);glFinish();bool cameraInvalidates=normalShellGeometryBuilds>beforePose;passed=passed&&cachePassed&&cameraInvalidates;
'''
    s=s.replace(marker,checks+marker)
    s=s.replace('{"cases",cases}', '{"cases",cases},{"opacity_cache_checks",cachedOpacity},{"opacity_cache_passed",cachePassed},{"camera_invalidates_cache",cameraInvalidates},{"nearest_shell_geometry_builds",normalShellGeometryBuilds}')
    save('src/fast_opacity_regression_r4.inc',s)
    b=(HERE/'build_fast_opacity_r3.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r3','build_fast_opacity_r4').replace('source_closure_fast_opacity_r3','source_closure_fast_opacity_r4').replace('src/views_fast_opacity_r3.cpp','src/views_fast_opacity_r4.cpp').replace('src/main_fast_opacity_r1.cpp','src/main_fast_opacity_r4.cpp')
    save('build_fast_opacity_r4.sh',b)
    save('run_fast_opacity_r4.sh',(HERE/'run_fast_opacity_r3.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r3','build_fast_opacity_r4'))
    closure['source_sha256']=dict(closure['source_sha256'])
    for n in ('prepare_fast_opacity_r4.py','src/views_fast_opacity_r4.hpp','src/views_fast_opacity_r4.cpp','src/main_fast_opacity_r4.cpp','src/fast_opacity_regression_r4.inc','src/fast_shell_cache_r1.inc','build_fast_opacity_r4.sh','run_fast_opacity_r4.sh'):
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='nearest_shell_cached_GPU_color_with_opaque_canvas_candidate',maximum_lung_geometry_draws_per_changed_transparent_frame=1,opacity_only_requires_geometry_draw=False)
    save('source_closure_fast_opacity_r4.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
