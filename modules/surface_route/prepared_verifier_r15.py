"""Sealed R9 prepared-scene checks with action-scoped SHA/bundle reuse."""
from pathlib import Path
import json
from modules.surface_route.ui_bridge_r9 import asset_path,ROOT
from modules.surface_route.verification_session_r15 import sha,verify_bundle

def verify_prepared(path, root=ROOT):
    path = Path(path).resolve()
    receipt = json.loads((path.parent/'prepared.json').read_text(encoding='utf-8'))
    for name, expected in receipt['output_sha256'].items():
        if name not in ('scene.json', 'airway.attributes') or sha(path.parent/name) != expected:
            raise ValueError('Changed prepared Qt payload')
    scene = json.loads(path.read_text(encoding='utf-8'))
    complete = scene['complete_surface']
    if (receipt['revision'] != complete['revision'] or receipt['input_sha256'] != scene['input_sha256']
            or sha(Path(complete['bundle'])/'scene.json') != receipt['bundle_sha256']
            or complete['source_result'] != scene['result']):
        raise ValueError('Mixed complete Qt scene')
    verify_bundle(complete['bundle'], complete['revision'])
    for file, expected in receipt['case_files_sha256'].items():
        if sha(root/file) != expected:
            raise ValueError('Changed original case: '+file)
    for file, expected in receipt['retained_assets_sha256'].items():
        if sha(asset_path(path.parent, file, root)) != expected:
            raise ValueError('Changed retained CT/overview asset')
    if sha(Path(complete['bundle'])/'airway.vertices') != receipt['airway_vertices_sha256']:
        raise ValueError('Changed complete airway stream')
    return scene

