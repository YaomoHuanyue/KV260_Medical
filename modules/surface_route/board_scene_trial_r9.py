"""Durable ARM preparation and real Qt API tests, no MMIO/XRT initialization."""
from pathlib import Path
import json
import os
import subprocess
import sys
from time import perf_counter
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.ui_bridge_r9 import prepare,verify_prepared,case_binding
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.scene_runtime_r9 import SceneSnapshot


def run(argv,log,env=None):
    with log.open('xb') as stream:
        subprocess.run(argv,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)


def main():
    output=ROOT/'modules/surface_route/results/native_scene_ARM_r9'
    output.mkdir(exist_ok=False)
    closure=json.loads((ROOT/'modules/surface_route/source_closure_r9.json').read_text())
    for name,expected in closure['files_sha256'].items():
        assert sha(ROOT/name)==expected,name
    base=ROOT/'ui/cache/772c198b7916e79f609fcb85/scene.json'
    bundle_root=ROOT/'modules/surface_route/results/complete_bundles_ARM_r8'
    cases=[]
    try:
        run([sys.executable,str(ROOT/'modules/surface_route/test_scene_r9.py'),
            '--bundle',str(bundle_root/'network_probability_high_ported_bend_1p0'),
            '--platform','ARM','--output',str(output/'protocol.json')],output/'protocol.log')
        for folder in sorted(p for p in bundle_root.iterdir() if p.is_dir()):
            start=perf_counter()
            receipt=prepare(base,folder,output/folder.name)
            scene=verify_prepared(output/folder.name/'scene.json')
            nav=scene['navigation'];attr=scene['meshes']['airway']['attributes']
            assert len(nav['points'])==len(nav['arc'])==len(nav['hud']['samples'])
            assert attr['vertices']==scene['meshes']['airway']['vertices']
            assert attr['confidence_available']
            assert not {'instrument_profiles','alternative_routes'}&set(nav)
            assert scene['complete_surface']['revision']==receipt['revision']
            assert scene['meshes']['lung']['file']==str(base.parent/'lung.mesh')
            cases.append(dict(label=folder.name,scene=str(output/folder.name/'scene.json'),
                revision=receipt['revision'],camera_count=len(nav['positions']),route_count=len(nav['points']),
                mesh_vertices=attr['vertices'],generation_kind=attr['generation_kind'],
                preparation_seconds=receipt['total_seconds'],preparation_and_verification_seconds=perf_counter()-start))
            print(folder.name,len(nav['positions']),'Qt camera points',flush=True)
        write_json(output/'index.json',dict(cases=cases))
        # Wrong CT, target and result bindings are checked before publishing.
        base_meta=json.loads(base.read_text());sample=json.loads((bundle_root/'network_probability_high_ported_bend_1p0/scene.json').read_text())
        bad=dict(base_meta,input_sha256='0'*64)
        try:case_binding(base,bad,sample)
        except ValueError:pass
        else:raise AssertionError('Wrong CT accepted')
        src=ROOT/'ui/releases/feature_completion_r6/src'
        flags=subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        common=['g++','-std=c++17','-O2','-fPIC','-pthread','-mcpu=cortex-a53','-I',str(src)]
        run(common+[str(ROOT/'modules/surface_route/test_native_scene_r9.cpp'),str(src/'views_batch_r3.cpp'),
                    *flags,'-o',str(output/'test_native_scene')],output/'compile_native.log')
        run(common+['-c',str(src/'pl_scope_complete_r9.cpp'),*flags,'-o',str(output/'pl_scope_complete_r9.o')],output/'compile_transport.log')
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen');env.pop('LD_PRELOAD',None)
        run([str(output/'test_native_scene'),str(output/'index.json'),str(output/'protocol.json'),
             str(output/'native_Qt.json')],output/'native_Qt.log',env)
        native=json.loads((output/'native_Qt.json').read_text())
        snapshots={}
        latency=[]
        for entry in native['native_requests']:
            bundle=entry['bundle']
            if bundle not in snapshots:snapshots[bundle]=SceneSnapshot(bundle)
            start=perf_counter();plan=snapshots[bundle].frame_plan(entry['request']);latency.append(perf_counter()-start)
            assert plan['revision']==entry['request']['revision']
        # Reference scene and live boot are unchanged: no test imports QualitySession.
        for name,expected in closure['files_sha256'].items():assert sha(ROOT/name)==expected,name
        proof=dict(status='eight_complete_native_Qt_scene_assets_and_actual_camera_protocol_verified',cases=cases,
            protocol_checks=13,wrong_CT_rejected=True,native_Qt_requests_accepted=len(latency),
            native_Qt_pose_validation_ms=[min(latency)*1000,float(np.median(latency))*1000,max(latency)*1000],
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            source_closure_sha256=sha(ROOT/'modules/surface_route/source_closure_r9.json'),
            retained_default_descriptor_sha256=sha(ROOT/'ui/active_release.json'),
            retained_default_entry_sha256=sha(ROOT/'ui/run.sh'),
            compiled_binary_sha256=sha(output/'test_native_scene'),
            compiled_transport_object_sha256=sha(output/'pl_scope_complete_r9.o'),
            PL_access=False,new_bitstream=False,production_promoted=False,physical_UI_review=False,
            remaining=['full native UI selection and active-scene export/profile dispatch',
                       'actual C9 same-input full output benchmark and physical HDMI review'])
        write_json(output/'acceptance.json',proof)
        print(proof['status'],flush=True)
    except BaseException as error:
        write_json(output/'failure.json',dict(status='failed_no_PL_access',error=str(error),traceback=traceback.format_exc(),completed_cases=cases))
        raise


if __name__=='__main__':main()
