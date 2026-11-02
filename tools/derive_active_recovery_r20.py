"""Version current-scene recovery, export and media adapters without old edits."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    edits=[]
    def change(parent,child,changes):
        source=(ROOT/parent).read_text(encoding='utf-8')
        for before,after in changes:
            assert source.count(before)==1,(parent,before,source.count(before));source=source.replace(before,after)
        with (ROOT/child).open('x',encoding='utf-8',newline='\n') as f:f.write(source)
        if child.endswith('.py'):compile(source,child,'exec')
        edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
    change('modules/surface_route/active_backend_r17.py','modules/surface_route/active_backend_r20.py',[
        ('from modules.surface_route.quality_validation_r16 import verify_active_scene','from modules.airway_detail.active_scene_r20 import verify_active_scene,produce as recover'),
        ("choices=['prepare','comparison','selected-path','quality']","choices=['prepare','comparison','selected-path','quality','airway-detail']"),
        ("        elif a.action=='comparison':","        elif a.action=='airway-detail':\n            path=recover(a.active_scene,output,a.lesion,event)\n        elif a.action=='comparison':")])
    change('modules/navigation_media/active_binding_r18b.hpp','modules/navigation_media/active_binding_r20.hpp',[
        (' pin(root+"/dfx/surface_quality/release/manifest.json");',''' auto recovery=scene["distal_recovery_binding"].toObject();
 if(!recovery.isEmpty()){
  pin(recovery["report"].toString(),recovery["report_sha256"].toString());
  auto outputs=recovery["outputs_sha256"].toObject();if(outputs.size()!=4)throw std::runtime_error("Invalid recovery review outputs");
  for(auto it=outputs.begin();it!=outputs.end();++it)pin(it.key(),it.value().toString());
  auto review=scene["distal_recovery"].toObject();auto inputs=review["inputs_sha256"].toObject();
  for(auto it=inputs.begin();it!=inputs.end();++it)pin(it.key(),it.value().toString());
 }
 pin(root+"/dfx/surface_quality/release/manifest.json");''')])
    change('modules/batch_images/heatmap_current_r19.py','modules/batch_images/heatmap_current_r20.py',[
        ('from modules.surface_route.quality_validation_r16 import verify_active_scene','from modules.airway_detail.active_scene_r20 import verify_active_scene'),
        ("    eligible=(g==eligibility['geometry'] and mask_hash==eligibility['masks_sha256'])",'''    # The accepted original context used bits 0..4. New recovery layers occupy
    # bits 5..7 and cannot change lung/lesion EDT eligibility.
    context=hashlib.sha256()
    for z in range(len(masks)):context.update(np.ascontiguousarray(masks[z]&31).tobytes())
    context_hash=context.hexdigest()
    eligible=(g==eligibility['geometry'] and context_hash==eligibility['masks_sha256'])'''),
        ('active_revision=complete[\'revision\'],active_field_sha256=SHA(field),','active_revision=complete[\'revision\'],active_field_sha256=SHA(field),eligibility_context_low5_sha256=context_hash,')])
    change('modules/batch_images/finish_current_r19.py','modules/batch_images/finish_current_r20.py',[
        ('from heatmap_current_r19 import work_heatmap','from heatmap_current_r20 import work_heatmap')])
    change('modules/batch_images/UI_feature_current_r19.inc','modules/batch_images/UI_feature_current_r20.inc',[
        ('modules/batch_images/finish_current_r19.py','modules/batch_images/finish_current_r20.py')])
    change('modules/surface_route/export_scene_r10.py','modules/surface_route/export_scene_r20.py',[
        ('from modules.surface_route.ui_bridge_r9 import verify_prepared, asset_path','''from modules.surface_route.ui_bridge_r9 import asset_path
from modules.airway_detail.active_scene_r20 import verify_active_scene
from modules.airway_detail.export_review_r20 import append_export
def verify_prepared(path,root=ROOT):
    if Path(root).resolve()!=ROOT:raise ValueError('Current project root required')
    return verify_active_scene(path)'''),
        ('        reference_start = perf_counter()','        recovery_export=append_export(scene,payload)\n        reference_start = perf_counter()'),
        ('            masks=inherited[\'masks\'], original_source_files_sha256=source_files,','            masks=inherited[\'masks\'], original_source_files_sha256=source_files,recovery_review=recovery_export,')])
    change('modules/surface_route/export_backend_r10.py','modules/surface_route/export_backend_r20.py',[
        ('modules.surface_route.export_scene_r10','modules.surface_route.export_scene_r20'),
        ('from modules.surface_route.ui_bridge_r9 import verify_prepared','from modules.airway_detail.active_scene_r20 import verify_active_scene as verify_prepared')])
    change('ui/releases/feature_completion_r6/src/active_surface_UI_r17.inc','ui/releases/feature_completion_r6/src/active_surface_UI_r20.inc',[
        ('  play.stop();playing=false;','  if(action=="airway-detail")saveRecoveryView();\n  play.stop();playing=false;'),
        ('modules/surface_route/active_backend_r17.py','modules/surface_route/active_backend_r20.py'),
        ('   loadScene(pendingResult);record(', '   loadScene(pendingResult);if(activeSurfaceAction=="airway-detail")restoreRecoveryView();record('),
        ('  if(qualityTesting)QTimer::singleShot','  if(activeRecoveryTesting)QTimer::singleShot(300,this,[this]{recoveryAdvance();});\n  else if(qualityTesting)QTimer::singleShot'),
        ('  message(action=="quality"?', '  message(action=="airway-detail"?u("正在审核当前目标的细支气管；模型和导航保持原样"):action=="quality"?')])
    change('ui/releases/feature_completion_r6/src/main_complete_scene_r19.cpp','ui/releases/feature_completion_r6/src/main_complete_scene_r20.cpp',[
        ('active_binding_r18b.hpp','active_binding_r20.hpp'),
        ('modules/batch_images/UI_feature_current_r19.inc','modules/batch_images/UI_feature_current_r20.inc'),
        ('#include "active_surface_UI_r17.inc"','#include "active_recovery_UI_r20.inc"\n#include "active_surface_UI_r20.inc"'),
        ('modules/surface_route/active_backend_r17.py','modules/surface_route/active_backend_r20.py'),
        ('modules/surface_route/export_backend_r10.py','modules/surface_route/export_backend_r20.py'),
        ('for(auto*b:{navButton,recoveryButton})','for(auto*b:{navButton})'),
        ('  if(scene.contains("complete_surface")&&mode=="reconstruction")','  if(scene.contains("complete_surface")&&mode=="airway-detail"){startSurfaceAction(mode);return;}\n  if(scene.contains("complete_surface")&&mode=="reconstruction")'),
        ('if(qualityTesting){QTimer::singleShot(300,this,[this]{qualityTestAdvance();});}else if(activeSurfaceTesting)',
         'if(activeRecoveryTesting){QTimer::singleShot(300,this,[this]{recoveryAdvance();});}else if(qualityTesting){QTimer::singleShot(300,this,[this]{qualityTestAdvance();});}else if(activeSurfaceTesting)'),
        ('message(u("已导出至 ")+result["path"].toString());','message(u("已导出至 ")+result["path"].toString());if(activeRecoveryTesting){recoveryExported(result);return;}')])
    # Compile only this changed main; preserve the accepted O2 render objects.
    parent='modules/surface_route/board_native_build_r19.py';child='modules/surface_route/board_native_build_r20.py'
    source=(ROOT/parent).read_text().replace("parent=folder/'build_complete_scene_r18b'","parent=folder/'build_complete_scene_r19'")
    source=source.replace("out=folder/'build_complete_scene_r19'","out=folder/'build_complete_scene_r20'")
    source=source.replace('native_UI_source_closure_r19','native_UI_source_closure_r20').replace('main_complete_scene_r19','main_complete_scene_r20').replace('R19 native adapter','R20 native adapter')
    with (ROOT/child).open('x',encoding='utf-8',newline='\n') as f:f.write(source)
    edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child)))
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r19.json';files=json.loads(parent.read_text())['files_sha256']
    for n,h in files.items():assert sha(ROOT/n)==h,n
    names=[e['child'] for e in edits]+['tools/derive_active_recovery_r20.py','modules/airway_detail/active_scene_r20.py',
        'modules/airway_detail/export_review_r20.py','ui/releases/feature_completion_r6/src/active_recovery_UI_r20.inc']
    files.update({n:sha(ROOT/n) for n in names})
    for n in names:
        if n.endswith('.py'):compile((ROOT/n).read_text(encoding='utf-8'),n,'exec')
    with (ROOT/'modules/surface_route/native_UI_source_closure_r20.json').open('x',encoding='utf-8') as f:
        json.dump(dict(files_sha256=files,parent_sha256=sha(parent),change='current CT recovery review and associated export/media identities',production_promoted=False),f,indent=2);f.write('\n')
    with (ROOT/'modules/airway_detail/active_derivation_r20.json').open('x',encoding='utf-8') as f:json.dump(dict(edits=edits,new_bitstream=False),f,indent=2);f.write('\n')
    print('R20 native recovery adapters derived')

if __name__=='__main__':main()
