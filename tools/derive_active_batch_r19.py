"""Bind native batch captures and diagnostic to the active complete surface."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def emit(name,data):
    with (ROOT/name).open('x',encoding='utf-8',newline='\n') as f:f.write(data)
def main():
    edits=[]
    def change(parent,child,changes):
        source=(ROOT/parent).read_text(encoding='utf-8')
        for item in changes:
            before,after=item[:2];count=item[2] if len(item)>2 else 1
            assert source.count(before)==count,(parent,before,source.count(before));source=source.replace(before,after)
        emit(child,source);edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
    change('modules/batch_images/finish_r3.py','modules/batch_images/finish_current_r19.py',[
        ('from heatmap_C8_r2 import work_heatmap','from heatmap_current_r19 import work_heatmap'),
        ("['C6_endoscope_trace_target_outline_normals']","['C9_current_scalar_endoscope_trace_target_outline_normals']"),
        ("helper_source_sha256=SHA(Path(__file__)),diagnostic=diagnostic,","helper_source_sha256=SHA(Path(__file__)),diagnostic=diagnostic,active_scene_binding=request['active_scene_binding'],"),
        ("['C8_exact_verified_input_EDT']","['C8_verified_lung_lesion_EDT']"),
        ('original_adaptive_multivolume_debug_heatmap','original_adaptive_multivolume_steps_current_airway_field')])
    changes=[
        ('if(batchTestKind=="no_route"){','if(batchTestKind=="no_route"&&!scene.contains("complete_surface")){'),
        (' QJsonObject batchSources;',' QJsonObject batchActiveBinding;\n QJsonObject batchSources;'),
        ('  batchHasNavigation=scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json");',
         '  batchHasNavigation=scene.contains("complete_surface")?(scope->cameraCount()>1&&scope->totalDistance()>0&&QFileInfo::exists(scene["complete_surface"].toObject()["bundle"].toString()+"/route.json")):(scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json"));batchActiveBinding={};'),
        ('batchProgressClock.elapsed()>10000','batchProgressClock.elapsed()>60000'),
        ('等待 PL 完成帧超过 10 秒','等待 PL 完成帧超过 60 秒'),
        ('  batchThread=std::thread([this,paths]{QJsonObject hashes;QString error;try{for(auto p:paths)hashes[p]=videoHash(p);}catch(const std::exception&e){error=QString::fromUtf8(e.what());}',
         '''  auto savedScene=scene;QString savedScenePath=scenePath,savedRoot=root;
  batchThread=std::thread([this,paths,savedScene,savedScenePath,savedRoot]{QJsonObject hashes,binding;QString error;
   try{if(savedScene.contains("complete_surface"))binding=navigation_media::activeVideoBinding(savedRoot,savedScenePath,savedScene,hashes,[this](QString path){return videoHash(path);});
    else for(auto p:paths)hashes[p]=videoHash(p);}catch(const std::exception&e){error=QString::fromUtf8(e.what());}'''),
        ('[this,hashes,error]{batchThread.join();batchSources=hashes;',
         '[this,hashes,binding,error]{batchThread.join();batchSources=hashes;batchActiveBinding=binding;'),
        ('plScope->start(source,req);',
         'if(!batchActiveBinding.isEmpty())plScope->startScene(batchActiveBinding["bundle"].toString(),batchActiveBinding["revision"].toString(),req);else plScope->start(source,req);'),
        ('if(batchRunning&&batchAwaiting){batchFrame=meta;',
         'if(batchRunning&&batchAwaiting){if(!batchActiveBinding.isEmpty()&&!navigation_media::activeVideoFrame(batchActiveBinding,meta)){batchAwaiting=false;plScope->stop([this]{batchFinish(u("批量截图收到其他场景的帧"));});return;}batchFrame=meta;'),
        ('Invalid C6 reference planes','Invalid complete endoscope reference planes'),
        ('QString("C6_depth_outline.rgba")','QString(batchActiveBinding.isEmpty()?"C6_depth_outline.rgba":"C9_depth_outline.rgba")'),
        ('QString("C6_normals.rgba")','QString(batchActiveBinding.isEmpty()?"C6_normals.rgba":"C9_normals.rgba")'),
        ('  QJsonObject request{{"scene",scenePath}', '  QJsonObject request{{"active_scene_binding",batchActiveBinding},{"scene",scenePath}'),
        ('root+"/modules/batch_images/finish_r3.py"',
         '(batchActiveBinding.isEmpty()?root+"/modules/batch_images/finish_r3.py":root+"/modules/batch_images/finish_current_r19.py")'),
        ('{"one_writer_image_in_flight",true}', '{"one_writer_image_in_flight",true},{"active_scene_binding",batchActiveBinding}'),
    ]
    change('modules/batch_images/UI_feature_r4.inc','modules/batch_images/UI_feature_current_r19.inc',changes)
    change('ui/releases/feature_completion_r6/src/main_complete_scene_r18b.cpp',
        'ui/releases/feature_completion_r6/src/main_complete_scene_r19.cpp',[
            ('modules/batch_images/UI_feature_r4.inc','modules/batch_images/UI_feature_current_r19.inc'),
            ('for(auto*b:{navButton,batchButton,recoveryButton})','for(auto*b:{navButton,recoveryButton})')])
    # All rendering/transport objects remain O2 and byte-identical to R18b.
    parent='modules/surface_route/board_native_build_r18b.py';child=parent.replace('r18b.py','r19.py')
    source=(ROOT/parent).read_text(encoding='utf-8')
    source=source.replace("parent=folder/'build_complete_scene_r18'","parent=folder/'build_complete_scene_r18b'")
    source=source.replace("out=folder/'build_complete_scene_r18b'","out=folder/'build_complete_scene_r19'")
    source=source.replace('native_UI_source_closure_r18b','native_UI_source_closure_r19').replace('main_complete_scene_r18b','main_complete_scene_r19').replace('R18b native adapter','R19 native adapter')
    emit(child,source);edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child)))
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r18b.json';files=json.loads(parent.read_text())['files_sha256']
    for n,h in files.items():assert sha(ROOT/n)==h,n
    names=[e['child'] for e in edits]+['tools/derive_active_batch_r19.py','modules/batch_images/step_volume_r19.py','modules/batch_images/heatmap_current_r19.py']
    files.update({n:sha(ROOT/n) for n in names})
    emit('modules/surface_route/native_UI_source_closure_r19.json',json.dumps(dict(files_sha256=files,parent_sha256=sha(parent),
        change='current C9 batch captures and current signed-field adaptive diagnostic',production_promoted=False),indent=2)+'\n')
    emit('modules/batch_images/active_derivation_r19.json',json.dumps(dict(edits=edits,new_bitstream=False),indent=2)+'\n')
    print('R19 current surface batch derived')
if __name__=='__main__':main()
