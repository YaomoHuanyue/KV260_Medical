"""Reuse verified immutable display buffers after navigation-only replanning.

Every destination has its own directory entries. Removing the old cache cannot
remove a linked buffer from the new cache. Route data, HUD and airway attributes
are always generated again by the original accepted functions.
"""
from pathlib import Path
import ast
import copy
import hashlib
import json
import os
import shutil
import stat
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


class Geometry:
    def __init__(self,metadata):self.value=metadata
    def GetSize(self):return tuple(self.value['size_xyz'])
    def GetSpacing(self):return tuple(self.value['spacing_xyz'])
    def GetOrigin(self):return tuple(self.value['origin_lps_mm'])
    def GetDirection(self):return tuple(self.value['direction'])
    def GetDimension(self):return 3
    def GetNumberOfComponentsPerPixel(self):return 1


class Reuse:
    def __init__(self,state,*,index=None,target=None):
        self.state=state;self.original=state['prepare']
        self.index=Path(index) if index else HERE/'cache_index'
        self.target=Path(target) if target else None
        # Reconstruct the exact already-checked source used by the accepted
        # adapter, then retain its complete source-manifest prefix unchanged.
        source=Path(state['__file__']).read_text()
        for before,after in state['_exact_derivation'].items():
            assert source.count(before)==1
            source=source.replace(before,after)
        parsed=ast.parse(source)
        function=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='prepare')
        stop=next(i for i,n in enumerate(function.body) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='key' for x in n.targets))
        function=copy.deepcopy(function);function.name='_manifest';function.body=function.body[:stop]+[ast.Return(value=ast.Tuple(elts=[ast.Name(id=n,ctx=ast.Load()) for n in ['input_path','digest','results','result','sources']],ctx=ast.Load()))]
        module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
        namespace=dict(state);exec(compile(module,str(Path(__file__))+'::original_manifest','exec'),namespace)
        self.manifest=namespace['_manifest']

    def _index_path(self,result):
        return self.index/(hashlib.sha256(str(result).encode()).hexdigest()+'.json')

    def _static(self,result,sources):
        canonical={k.replace('\\','/'):v for k,v in sources.items()}
        if len(canonical)!=len(sources):raise ValueError('Ambiguous source manifest separators')
        values={k:v for k,v in canonical.items() if k not in ('result','pipeline.json') and not k.startswith('navigation/')}
        values['navigation_reuse_adapter']=sha(Path(__file__))
        # Include all copied metadata, probabilities and optional evidence, not
        # just the three files needed for basic surface geometry.
        for name in ['segmentation','reconstruction','airway_detail']:
            directory=result/name
            if directory.exists():
                for p in sorted(directory.iterdir()):
                    if p.is_file():values[p.relative_to(result).as_posix()]=sha(p)
        return values

    def _regular(self,path):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode):raise ValueError('Display reuse requires a regular file: '+str(path))
        return info

    def seal(self,scene):
        scene=Path(scene);meta=self.state['read'](scene)
        if not meta.get('result'):return
        _,_,_,result,sources=self.manifest(meta['input'],meta['result'])
        cache=self.state['read'](scene.parent/'cache.json')
        if sources!=cache['sources']:raise ValueError('Display sources changed before sealing')
        names={meta['volume']}
        if meta.get('masks'):names.add(meta['masks'])
        names.update(m['file'] for m in meta['meshes'].values())
        assets={}
        for name in sorted(names):
            if Path(name).name!=name:raise ValueError('Nonlocal display buffer')
            p=scene.parent/name;before=self._regular(p);digest=sha(p);after=self._regular(p)
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Display buffer changed while sealing')
            assets[name]=dict(bytes=after.st_size,sha256=digest)
        self.index.mkdir(parents=True,exist_ok=True)
        self.state['write'](self._index_path(result),dict(schema='kv260.navigation.display_reuse.v1',
            scene=str(scene),scene_sha256=sha(scene),static_sources=self._static(result,sources),assets=assets))

    def _materialize(self,source,destination,expected):
        before=self._regular(source)
        if before.st_size!=expected['bytes'] or sha(source)!=expected['sha256']:raise ValueError('Changed sealed display buffer: '+str(source))
        linked=True
        try:os.link(source,destination)
        except OSError:
            linked=False;shutil.copyfile(source,destination)
        after=self._regular(source);created=self._regular(destination)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Source changed during display materialization')
        if created.st_size!=expected['bytes']:raise ValueError('Display materialization size mismatch')
        if linked:
            if (created.st_dev,created.st_ino)!=(after.st_dev,after.st_ino):raise ValueError('Display link identity mismatch')
        elif sha(destination)!=expected['sha256']:raise ValueError('Display materialization content mismatch')

    def prepare(self,input_path,result=None):
        began=time.monotonic()
        input_path,digest,results,result,sources=self.manifest(input_path,result)
        pipeline=self.state['read'](result/'pipeline.json') if result else {}
        parent=pipeline.get('source_result') if pipeline.get('mode')=='navigation' else None
        index=self._index_path(Path(parent).resolve()) if parent else None
        if index is None or not index.exists():
            scene=self.original(input_path,result);self.seal(scene);return scene
        seal=self.state['read'](index)
        if seal.get('schema')!='kv260.navigation.display_reuse.v1':raise ValueError('Unsupported display seal')
        if self._static(result,sources)!=seal['static_sources']:
            scene=self.original(input_path,result);self.seal(scene);return scene
        old=Path(seal['scene'])
        if not (old.resolve().is_relative_to(ROOT/'ui/cache') or old.resolve().is_relative_to(HERE.parent/'results')):raise ValueError('Sealed scene outside display cache')
        if not old.exists():
            scene=self.original(input_path,result);self.seal(scene);return scene
        if sha(old)!=seal['scene_sha256']:raise ValueError('Changed sealed display metadata')
        parent_meta=self.state['read'](old)
        required={parent_meta['volume']}
        if parent_meta.get('masks'):required.add(parent_meta['masks'])
        required.update(m['file'] for m in parent_meta['meshes'].values())
        if set(seal['assets'])!=required:raise ValueError('Sealed display asset set changed')
        for name in required:
            if not isinstance(name,str) or not name or name in ('.','..') or any(c in name for c in ('/',chr(92),':')):raise ValueError('Nonlocal sealed display asset')
        sources=dict(sources,navigation_reuse_adapter=sha(Path(__file__)))
        key=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()[:24]
        target=self.target or ROOT/'ui/cache'/('nav_reuse_'+key)
        if not (target.resolve().is_relative_to(ROOT/'ui/cache') or target.resolve().is_relative_to(HERE.parent/'results')):raise ValueError('Display target outside cache')
        if target.exists():
            cache=self.state['read'](target/'cache.json')
            if cache['sources']!=sources:raise ValueError('Existing incremental display sources changed')
            if set(cache['generated_sha256'])!=set(cache['sizes']) or not required.issubset(cache['sizes']):raise ValueError('Existing display file set changed')
            for name,digest in cache['generated_sha256'].items():
                if Path(name).name!=name or sha(target/name)!=digest:raise ValueError('Existing incremental display buffer changed')
            meta=self.state['read'](target/'scene.json')
            current=self.state['read'](self._index_path(result))
            if sha(target/'scene.json')!=current['scene_sha256']:raise ValueError('Existing incremental display metadata changed')
            meta['results']=results;self.state['write'](target/'scene.json',meta)
            current['scene_sha256']=sha(target/'scene.json');self.state['write'](self._index_path(result),current)
            self.state['emit']('prepared',scene=str(target/'scene.json'),seconds=time.monotonic()-began,reused=True,reused_geometry=True)
            return target/'scene.json'
        temp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.new');temp.mkdir(parents=True)
        try:
            meta=copy.deepcopy(self.state['read'](old))
            meta.update(result=str(result),results=results,navigation=None)
            self.state['emit']('progress',text='复用已校验的 CT、掩膜和网格；更新导航数据')
            for name,expected in seal['assets'].items():self._materialize(old.parent/name,temp/name,expected)
            import numpy as np
            with np.load(result/'navigation/route.npz',allow_pickle=False) as route,np.load(result/'navigation/camera.npz',allow_pickle=False) as camera:
                meta['navigation']=dict(points=route['points_lps_mm'].tolist(),arc=route['arc_mm'].tolist(),radius=route['radius_mm'].tolist(),
                    positions=camera['position_lps_mm'].tolist(),forward=camera['forward_lps'].tolist(),up=camera['up_lps'].tolist(),
                    report=self.state['read'](result/'navigation/route.json'))
            from analysis_partial import enrich_scene
            enrich_scene(result,Geometry(meta['geometry']),meta,temp,digest)
            self.state['write'](temp/'scene.json',meta)
            generated={p.name:p for p in temp.iterdir() if p.is_file() and p.name not in ['cache.json','scene.json']}
            digests={n:seal['assets'][n]['sha256'] if n in seal['assets'] else sha(p) for n,p in generated.items()}
            self.state['write'](temp/'cache.json',dict(sources=sources,sizes={n:p.stat().st_size for n,p in generated.items()},generated_sha256=digests))
            temp.rename(target)
        except BaseException:
            # Only this invocation's exact newly-created staging directory.
            if temp.exists() and temp.parent==target.parent and temp.name.endswith('.new'):shutil.rmtree(temp)
            raise
        # No seeding through the original manifest here: this target also binds
        # the new reuse adapter. Keep a separately verified seal for its child.
        next_seal=dict(seal,scene=str(target/'scene.json'),scene_sha256=sha(target/'scene.json'),static_sources=self._static(result,sources))
        self.index.mkdir(parents=True,exist_ok=True);self.state['write'](self._index_path(result),next_seal)
        self.state['emit']('prepared',scene=str(target/'scene.json'),seconds=time.monotonic()-began,reused_geometry=True)
        return target/'scene.json'
