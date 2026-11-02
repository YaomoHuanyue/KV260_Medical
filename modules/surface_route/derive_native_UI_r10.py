"""Derive active-scene export controls; retain accepted R9 and production R17."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import sha, write_json
from modules.surface_route.derive_scene_r9 import replace_once


def main():
    source = ROOT/'ui/releases/feature_completion_r6/src/main_complete_scene_r9b.cpp'
    text = source.read_text(encoding='utf-8')
    text = replace_once(text,
        'for(auto*b:{exportButton,compareButton,comparisonResults,rebuildButton,navButton,batchButton,videoButton,recoveryButton})',
        'for(auto*b:{compareButton,comparisonResults,rebuildButton,navButton,batchButton,videoButton,recoveryButton})')
    text = replace_once(text,
        '  if(action=="export"&&scene.contains("complete_surface")){message(u("当前新表面的完整导出尚未接入，已保留当前场景。"));return;}',
        '  bool activeExport=action=="export"&&scene.contains("complete_surface");')
    text = replace_once(text,
        'utilityProcess.start(root+"/.venv/bin/python",QStringList{root+"/modules/report_export/backend.py",action}+args);',
        'QString adapter=activeExport?root+"/modules/surface_route/export_backend_r10.py":root+"/modules/report_export/backend.py";'
        'if(activeExport)args<<"--active-scene"<<scenePath;'
        'utilityProcess.start(root+"/.venv/bin/python",QStringList{adapter,action}+args);')
    text = replace_once(text, 'auto complete=readJson(folder+"/reports/index.json");',
        'bool activeExport=scene.contains("complete_surface");'
        'auto complete=readJson(folder+(activeExport?"/original_analysis/index.json":"/reports/index.json"));')
    text = replace_once(text, 'bool good=result["schema"]=="kv260.export.v5"&&',
        'bool bound=!activeExport||(result["active_revision"]==scene["complete_surface"].toObject()["revision"]&&'
        'result["active_route_id"]==scene["complete_surface"].toObject()["route_id"]&&'
        'report["active_revision"]==scene["complete_surface"].toObject()["revision"]&&'
        'QFileInfo::exists(folder+"/active_scene/bundle/scene.json"));'
        'bool good=bound&&result["schema"]==(activeExport?"kv260.export.v6":"kv260.export.v5")&&')
    destination = source.with_name('main_complete_scene_r10.cpp')
    with destination.open('x', encoding='utf-8', newline='\n') as target:
        target.write(text)
    write_json(ROOT/'modules/surface_route/native_UI_derivation_r10.json', dict(
        parent_sha256=sha(source), output_sha256=sha(destination), production_sources_unchanged=True,
        changes=['enable current-scene export after cooperative graphics drain',
                 'bind export adapter to selected CT/result and exact scene revision',
                 'verify actual Qt export event and active airway VTP identity']))
    previous = ROOT/'modules/surface_route/board_native_build_r9b.py'
    build = previous.read_text(encoding='utf-8').replace('r9b', 'r10')
    with previous.with_name('board_native_build_r10.py').open('x', encoding='utf-8', newline='\n') as target:
        target.write(build)
    closure_path = ROOT/'modules/surface_route/native_UI_source_closure_r9b.json'
    bound = json.loads(closure_path.read_text())['files_sha256']
    for name, expected in bound.items():
        assert sha(ROOT/name) == expected, name
    additions = [destination, Path(__file__), previous.with_name('board_native_build_r10.py'),
                 ROOT/'modules/surface_route/export_scene_r10.py', ROOT/'modules/surface_route/export_backend_r10.py',
                 ROOT/'modules/surface_route/native_UI_derivation_r10.json',
                 ROOT/'modules/surface_route/test_export_scene_r10.py']
    for package in ('report_export', 'surface_export', 'lesion_catalogue'):
        additions += list((ROOT/'modules'/package).glob('*.py'))
    additions += list((ROOT/'ui/features').glob('*.py'))
    bound.update({p.relative_to(ROOT).as_posix():sha(p) for p in additions})
    write_json(ROOT/'modules/surface_route/native_UI_source_closure_r10.json', dict(
        schema='kv260.surface_route.native_UI_closure.v1', files_sha256=bound,
        parent_closure_sha256=sha(closure_path), production_promoted=False))


if __name__ == '__main__':
    main()
