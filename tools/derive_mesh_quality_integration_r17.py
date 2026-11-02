"""Bind the measured exact indexer into a versioned quality/UI successor."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def create(parent_name,child_name,replacements):
    parent=ROOT/parent_name;child=ROOT/child_name;source=parent.read_text(encoding='utf-8')
    for old,new,count in replacements:
        assert source.count(old)==count,(parent_name,old,source.count(old))
        source=source.replace(old,new)
    if child.exists():assert child.read_text(encoding='utf-8')==source,child_name
    else:
        with child.open('x',encoding='utf-8',newline='\n') as f:f.write(source)
    return dict(parent=parent_name,parent_sha256=sha(parent),child=child_name,child_sha256=sha(child),
        replacements=[dict(old=o,new=n,count=c) for o,n,c in replacements])
def main():
    edits=[]
    edits.append(create('modules/surface_route/quality_action_r16.py','modules/surface_route/quality_action_r17.py',[
        ('from modules.surface_quality.scalar_mesh_r7 import from_pl_words','from modules.surface_quality.scalar_mesh_r17 import from_pl_words',1),
        ('    points,faces,mesh_proof=from_pl_words(', '    mesh_start=perf_counter()\n    points,faces,mesh_proof=from_pl_words(',1),
        ('    del words,binary','    mesh_seconds=perf_counter()-mesh_start\n    del words,binary',1),
        ('        route_guidance_seconds=route_seconds,total_before_UI_seconds=perf_counter()-begin,',
         "        mesh_preparation_seconds=mesh_seconds,mesh_indexing_backend='PS_native_exact_R17_two_pass',\n        mesh_indexing_source_sha256={n:sha(ROOT/n) for n in (\n            'modules/surface_quality/scalar_mesh_r17.py','modules/surface_quality/scalar_mesh_indexing_r17.py',\n            'modules/surface_quality/indexing_r17/native.py','modules/surface_quality/indexing_r17/split_links.cpp',\n            'modules/surface_quality/indexing_r17/build_ARM/build.json','modules/surface_quality/indexing_r17/build_ARM/libindexing.so')},\n        route_guidance_seconds=route_seconds,total_before_UI_seconds=perf_counter()-begin,",1)]))
    edits.append(create('modules/surface_route/active_backend_r16.py','modules/surface_route/active_backend_r17.py',[
        ('from modules.surface_route.quality_action_r16 import produce','from modules.surface_route.quality_action_r17 import produce',1)]))
    prefix='ui/releases/feature_completion_r6/src/'
    edits.append(create(prefix+'main_complete_scene_r16.cpp',prefix+'main_complete_scene_r17.cpp',[
        ('active_backend_r16.py','active_backend_r17.py',1),('active_surface_UI_r16.inc','active_surface_UI_r17.inc',1)]))
    edits.append(create(prefix+'active_surface_UI_r16.inc',prefix+'active_surface_UI_r17.inc',[
        ('active_backend_r16.py','active_backend_r17.py',1)]))
    edits.append(create('modules/surface_route/board_native_build_r16.py','modules/surface_route/board_native_build_r17.py',[
        ('build_complete_scene_r16','build_complete_scene_r17',1),('build_complete_scene_r15','build_complete_scene_r16',1),
        ('native_UI_source_closure_r16.json','native_UI_source_closure_r17.json',1),
        ('main_complete_scene_r16','main_complete_scene_r17',3),('R16 native adapter','R17 native adapter',1)]))
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r16.json'
    old=json.loads(parent.read_text());bound=old['files_sha256'].copy()
    for n,h in bound.items():assert sha(ROOT/n)==h,n
    paths=[e['child'] for e in edits]+[
        'modules/surface_quality/scalar_mesh_r17.py','modules/surface_quality/scalar_mesh_indexing_r17.py',
        'modules/surface_quality/indexing_r17/native.py','modules/surface_quality/indexing_r17/split_links.cpp',
        'modules/surface_quality/indexing_r17/build_ARM/build.json','modules/surface_quality/indexing_r17/build_ARM/libindexing.so',
        'tools/derive_mesh_quality_integration_r17.py']
    bound.update({n:sha(ROOT/n) for n in paths})
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r17.json'
    with closure.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(dict(files_sha256=bound,parent=str(parent.relative_to(ROOT)),parent_sha256=sha(parent),
            change='exact native PS vertex-link indexing; unchanged PL extraction/render and UI controls',production_promoted=False),f,indent=2);f.write('\n')
    proof=ROOT/'modules/surface_quality/indexing_r17/integration_derivation.json'
    with proof.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(dict(edits=edits,source_closure_sha256=sha(closure),new_bitstream=False),f,indent=2);f.write('\n')
    print(json.dumps({'edits':len(edits),'source_closure_sha256':sha(closure)}))
if __name__=='__main__':main()
