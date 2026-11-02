"""Retain the same complete-scene source graph that the actual video UI pins."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

BOARD_ROOT='/home/ubuntu/jupyter_notebooks/KV260_System'


def dependencies(system):
    system=Path(system).resolve();runtime=system/'tools/storage_runtime_identity.json'
    if not runtime.exists():return {}
    protected={}
    def path(name):
        assert isinstance(name,str) and name,'Invalid active video dependency name'
        name=name.replace('\\','/')
        for prefix in [system.as_posix(),BOARD_ROOT]:
            if name.startswith(prefix+'/'):
                name=name[len(prefix)+1:];break
        rel=PurePosixPath(name)
        assert not rel.is_absolute() and ':' not in name
        assert all(p not in ('','.','..') for p in name.split('/'))
        result=system.joinpath(*rel.parts)
        assert result.resolve().is_relative_to(system),'Escaping active video dependency'
        for item in [result,*result.parents]:
            if item==system:break
            assert not item.is_symlink(),'Symbolic active video dependency'
        return result
    def keep(name,expected=None):
        p=path(name);assert p.is_file(),'Missing active video dependency: '+str(p)
        if expected is not None:
            assert isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected)
        with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        assert expected is None or actual==expected,'Changed active video dependency: '+str(p)
        key=p.relative_to(system).as_posix()
        assert key not in protected or protected[key]==actual,'Conflicting active video dependency'
        protected[key]=actual;return p
    state=json.loads(runtime.read_text());scene_path=path(state['scene'])
    rel=scene_path.relative_to(system).as_posix()
    keep(rel,state['files_sha256'][rel]);scene=json.loads(scene_path.read_text())
    complete=scene.get('complete_surface')
    if not complete:return protected
    keep(runtime.as_posix())
    prepared_path=keep((scene_path.parent/'prepared.json').as_posix())
    prepared=json.loads(prepared_path.read_text());bundle=path(complete['bundle'])
    meta_path=keep((bundle/'scene.json').as_posix(),prepared['bundle_sha256'])
    meta=json.loads(meta_path.read_text())
    assert scene['schema']=='kv260.ui.scene.v1'
    assert prepared['schema']=='kv260.ui.complete_surface.prepared.v1'
    assert meta['schema']=='kv260.surface_route.complete_scene.v1' and meta['complete']
    assert complete['revision']==prepared['revision']==meta['revision']
    assert complete['route_id']==meta['route_id']
    assert complete['scalar_sha256']==meta['renderer_scalar_sha256']
    assert complete['bundle']==prepared['bundle'] and scene['input_sha256']==prepared['input_sha256']
    for name,expected in prepared['output_sha256'].items():
        assert name in ['scene.json','airway.attributes']
        keep((scene_path.parent/name).as_posix(),expected)
    assert set(prepared['output_sha256'])=={'scene.json','airway.attributes'}
    keep(scene['input'],scene['input_sha256'])
    keep((bundle/'airway.vertices').as_posix(),prepared['airway_vertices_sha256'])
    for name,expected in meta['identity']['files_sha256'].items():
        assert not PurePosixPath(name).is_absolute()
        keep((bundle/name).as_posix(),expected)
    for group in ['case_files_sha256','retained_assets_sha256']:
        assert prepared[group]
        for name,expected in prepared[group].items():keep(name,expected)
    provenance=meta['identity']['provenance']['input_sha256'];assert provenance
    for name,expected in provenance.items():keep(name,expected)
    quality=complete.get('quality',{})
    if quality:
        assert quality==prepared['active_quality']
        receipt=json.loads(keep(quality['receipt'],quality['receipt_sha256']).read_text())
        assert receipt['input_sha256']==scene['input_sha256']
        assert receipt['source']==quality['source'] and receipt['tier']==quality['tier']
        keep(receipt['field'],receipt['field_sha256'])
    recovery=scene.get('distal_recovery_binding',{})
    if recovery:
        keep(recovery['report'],recovery['report_sha256'])
        assert len(recovery['outputs_sha256'])==4
        for name,expected in recovery['outputs_sha256'].items():keep(name,expected)
        for name,expected in scene['distal_recovery']['inputs_sha256'].items():keep(name,expected)
    keep('dfx/surface_quality/release/manifest.json')
    return protected
