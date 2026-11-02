"""Derive a native transparency fix without changing accepted source or PL binaries."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,s):
    p=HERE/n
    assert not p.exists(),n
    p.write_text(s,encoding='utf-8',newline='\n')
def main():
    old=json.loads((HERE/'source_closure_exact_speed_r8.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256','old_source_sha256'):
        for n,d in old[group].items():assert sha(ROOT/n)==d,n
    header=(HERE/'src/views_interactive_r1.hpp').read_text(encoding='utf-8')
    header=header.replace(' QJsonObject featureMetrics()const;', ' QJsonObject featureMetrics()const;\n QJsonObject fastOpacityRegression(const QString&directory);')
    save('src/views_fast_opacity_r1.hpp',header)
    source=(HERE/'src/views_interactive_r1.cpp').read_text(encoding='utf-8').replace('views_interactive_r1.hpp','views_fast_opacity_r1.hpp')
    source+='\n#include "fast_opacity_regression_r1.inc"\n'
    save('src/views_fast_opacity_before_r1.cpp',source)
    before='''  if(order==0){glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);}else{glDisable(GL_BLEND);glDepthMask(GL_TRUE);}
  glDrawArrays(GL_TRIANGLES,0,m.count);'''
    after='''  if(order==0&&alpha<=0.f)continue;
  if(order==0&&alpha<1.f){
   // Fast transparency shows the nearest lung shell over opaque structures.
   // Establish its depth before blending: distant or unordered faces cannot
   // overwrite the near wall. Full multi-layer transmission remains C7's job.
   glDisable(GL_BLEND);glDepthMask(GL_TRUE);glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
   glDrawArrays(GL_TRIANGLES,0,m.count);
   glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
   // Quantized equal depths and shared triangle edges must blend only once.
   glStencilMask(0xff);glClearStencil(0);glClear(GL_STENCIL_BUFFER_BIT);
   glEnable(GL_STENCIL_TEST);glStencilFunc(GL_EQUAL,0,0xff);glStencilOp(GL_KEEP,GL_KEEP,GL_INCR);
   glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
   glDrawArrays(GL_TRIANGLES,0,m.count);
   glDisable(GL_STENCIL_TEST);glDepthFunc(GL_LESS);
  }else{
   // At opacity one this is an ordinary opaque surface, including near faces.
   glDisable(GL_BLEND);glDepthMask(GL_TRUE);glDrawArrays(GL_TRIANGLES,0,m.count);
  }'''
    assert source.count(before)==1
    save('src/views_fast_opacity_r1.cpp',source.replace(before,after))
    main_source=(HERE/'src/main_interactive_r1.cpp').read_text(encoding='utf-8').replace('views_interactive_r1.hpp','views_fast_opacity_r1.hpp')
    marker='if(transparentInteractionTesting){QTimer::singleShot(400'
    assert main_source.count(marker)==1
    entry='''if(qEnvironmentVariableIntValue("KV260_FAST_OPACITY_TEST")==1){QTimer::singleShot(400,this,[this]{
      if(failed){QApplication::exit(1);return;}
      tabs->setCurrentIndex(1);preciseBlend->setChecked(false);clipCheck->setChecked(false);opacity->setValue(100);
      QApplication::processEvents();QDir().mkpath(evidence);
      auto proof=overview->fastOpacityRegression(evidence);proof["slider_right_endpoint_opacity"]=overview->featureMetrics()["lung_opacity"];
      proof["precise_checkbox_unchecked"]=!preciseBlend->isChecked();proof["scene"]=scenePath;
      writeJson(evidence+"/fast_opacity_UI.json",proof);
      bool good=proof["status"]=="passed"&&proof["slider_right_endpoint_opacity"].toDouble()==1&&proof["precise_checkbox_unchecked"].toBool();
      releaseGraphics([good]{QApplication::exit(good?0:1);});
    });}else if(transparentInteractionTesting){QTimer::singleShot(400'''
    main_source=main_source.replace(marker,entry)
    # The existing control has always mapped right to alpha=1; say so explicitly.
    main_source=main_source.replace('new QLabel(u("肺透明度"))','new QLabel(u("肺不透明度"))')
    main_source=main_source.replace('opacity->setRange(0,100);','opacity->setRange(0,100);opacity->setToolTip(u("左端完全透明，右端完全不透明。快速模式显示最近一层肺表面；精确透明显示多层表面。"));')
    save('src/main_fast_opacity_r1.cpp',main_source)
    for mode,views in [('r1','views_fast_opacity_r1.cpp'),('before_r1','views_fast_opacity_before_r1.cpp')]:
        build=(HERE/'build_exact_speed_r8.sh').read_text(encoding='utf-8')
        build=build.replace('build_exact_speed_r8','build_fast_opacity_'+mode).replace('source_closure_exact_speed_r8.json','source_closure_fast_opacity_r1.json')
        build=build.replace('src/main_interactive_r1.cpp src/views_interactive_r1.cpp','src/main_fast_opacity_r1.cpp src/'+views)
        build=build.replace("status='exact_transparency_speed_UI_compiled_actual_ARM'", "status='fast_opacity_UI_compiled_actual_ARM'")
        save('build_fast_opacity_'+mode+'.sh',build)
        save('run_fast_opacity_'+mode+'.sh',(HERE/'run_exact_speed_r8.sh').read_text(encoding='utf-8').replace('build_exact_speed_r8','build_fast_opacity_'+mode))
    closure=dict(old)
    closure['source_sha256']=dict(old['source_sha256'])
    for n in ['prepare_fast_opacity_r1.py','src/views_fast_opacity_r1.hpp','src/views_fast_opacity_r1.cpp','src/views_fast_opacity_before_r1.cpp',
              'src/main_fast_opacity_r1.cpp','src/fast_opacity_regression_r1.inc','build_fast_opacity_r1.sh','build_fast_opacity_before_r1.sh','run_fast_opacity_r1.sh','run_fast_opacity_before_r1.sh']:
        closure['source_sha256'][(HERE/n).relative_to(ROOT).as_posix()]=sha(HERE/n)
    closure.update(status='native_nearest_lung_shell_depth_fix_candidate',previous_closure_sha256=sha(HERE/'source_closure_exact_speed_r8.json'),
                   only_worker_binding_changed=False,exact_worker_changed=False,PL_bitstream_changed=False)
    save('source_closure_fast_opacity_r1.json',json.dumps(closure,indent=2)+'\n')
if __name__=='__main__':main()
