"""Explicit small successors of sealed scene publisher and action CLI."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]

def derive(old,new,replacements):
    text=(ROOT/old).read_text(encoding='utf-8')
    for a,b in replacements:
        if text.count(a)!=1:raise ValueError((old,a,text.count(a)))
        text=text.replace(a,b)
    with (ROOT/new).open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    return dict(parent=old,successor=new,parent_sha256=hashlib.sha256((ROOT/old).read_bytes()).hexdigest(),
        successor_sha256=hashlib.sha256((ROOT/new).read_bytes()).hexdigest(),replacements=replacements)

def main():
    rows=[]
    rows.append(derive('modules/surface_route/ui_bridge_r9.py','modules/surface_route/quality_publish_r16.py',[
        ('from modules.surface_route.bundle_r8 import arrays, sha, write_json\nfrom modules.surface_route.bundle_reader_r9 import verify_bundle',
         'from modules.surface_route.bundle_r8 import arrays,write_json\nfrom modules.surface_route.verification_session_r15 import sha,verify_bundle'),
        ('def prepare(base_path, bundle_path, output, expected_revision=None, root=ROOT):',
         'def prepare(base_path, bundle_path, output, expected_revision=None, root=ROOT,quality_path=None):'),
        ("    if base['navigation']['report']['target'] != report['target']:\n        raise ValueError('Selected target and complete route differ')",
         "    from modules.navigation.navigation.pipeline import load_prepared,choose_target\n    c=load_prepared(result/'navigation')\n    target=choose_target(c,lesion_path=result/'segmentation/nodule_mask.nii.gz',lesion_index=report['target']['index'])\n    if target.metadata!=report['target']:raise ValueError('Changed actual target in complete route')\n    from modules.surface_route.quality_validation_r16 import validate_base_assets\n    validate_base_assets(base_path,base,image_path,result,root)\n    quality_path=Path(quality_path).resolve()\n    quality=json.loads(quality_path.read_text(encoding='utf-8'))\n    quality_entry=dict(receipt=str(quality_path),receipt_sha256=sha(quality_path),source=quality['source'],tier=quality['tier'])\n    for relative,digest in quality['case_files_sha256'].items():\n        if sha(root/relative)!=digest:raise ValueError('Changed quality source: '+relative)\n        bindings[relative]=digest"),
        ("        write_json(stage/'scene.json', scene)",
         "        from modules.surface_route.capabilities_r14c import capabilities\n        scene['available_structures'],scene['structure_foreground_voxels']=capabilities(np.fromfile(scene['masks'],np.uint8))\n        scene['complete_surface']['quality']=quality_entry\n        scene['complete_surface']['pending_operations']=['active_batch_video_recovery_dispatch']\n        write_json(stage/'scene.json', scene)"),
        ("            new_bitstream=False, PL_access=False, production_promoted=False)",
         "            new_bitstream=False, PL_access=False, production_promoted=False,active_quality=quality_entry)"),
    ]))
    rows.append(derive('modules/surface_route/active_backend_r15.py','modules/surface_route/active_backend_r16.py',[
        ('"""Async native action adapter; it never initializes XRT or loads a bitstream."""',
         '"""Async native actions; quality explicitly uses accepted C1 PL extraction."""'),
        ('from modules.surface_route.active_actions_r15 import verify_active_scene,compare_action,selected_action',
         'from modules.surface_route.active_actions_r15 import compare_action,selected_action\nfrom modules.surface_route.quality_validation_r16 import verify_active_scene\nfrom modules.surface_route.quality_action_r16 import produce'),
        ("choices=['prepare','comparison','selected-path']","choices=['prepare','comparison','selected-path','quality']"),
        ("    a=p.parse_args();scene=verify_active_scene(a.active_scene)",
         "    p.add_argument('--source',choices=['accepted_binary','network_probability'])\n    p.add_argument('--quality',choices=['high','ultra'])\n    a=p.parse_args()\n    if a.action=='quality':\n        scene=json.loads(a.active_scene.read_text(encoding='utf-8'))\n        if scene.get('complete_surface'):scene=verify_active_scene(a.active_scene)\n    else:scene=verify_active_scene(a.active_scene)"),
        ("        if a.action=='comparison':", "        if a.action=='quality':\n            if a.source is None or a.quality is None or a.lesion is None:raise ValueError('Explicit source, quality and target required')\n            produce(a.active_scene,output,a.source,a.quality,dict(lesion=a.lesion,diameter=a.diameter,margin=a.margin,minimum_bend=a.minimum_bend),event)\n        elif a.action=='comparison':"),
        ("PL_access=False)","PL_access=('--source' in sys.argv))"),
    ]))
    with (ROOT/'modules/surface_route/derivations_r16.json').open('x',encoding='utf-8') as f:json.dump(rows,f,indent=2,ensure_ascii=False)

if __name__=='__main__':main()
