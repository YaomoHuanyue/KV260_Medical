"""Fresh same-mesh distance and continuous-route review; never modifies the UI."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import statistics
import sys
from time import perf_counter
import numpy as np

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parents[1]
sys.path.insert(0, str(SYSTEM))
from modules.surface_route.audit import MeshRegion, audit_polyline
from modules.surface_quality.mesh_clearance import MeshClearance
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance

SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
KEYS = ['32d5bd2ff1ce91e03adc67e0', '3efb66ee45e6a0196caef062']
BOARD_ROOT = PurePosixPath('/home/ubuntu/jupyter_notebooks/KV260_System')


def bound_input(path):
    relative = PurePosixPath(path).relative_to(BOARD_ROOT)
    if '..' in relative.parts:
        raise ValueError('Source outside bound project')
    local = (SYSTEM/Path(*relative.parts)).resolve()
    if not local.is_relative_to(SYSTEM):
        raise ValueError('Invalid source path')
    return local


def scene_binding(cache):
    scene = json.loads((cache/'scene.json').read_text(encoding='utf-8'))
    assert scene['schema'] == 'kv260.surface_quality.UI.scene.v1' and scene['complete']
    identity = scene['identity']
    assert hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest() == scene['key']
    assert scene['key'].startswith(cache.name)
    assert SHA(SYSTEM/'dfx/surface_quality/release/manifest.json') == identity['C9_release_sha256']
    binding = {SYSTEM/'dfx/surface_quality/release/manifest.json':identity['C9_release_sha256'],
               cache/'scene.json':SHA(cache/'scene.json'),cache/'mesh.npz':scene['files_sha256']['mesh.npz']}
    for name, digest in identity['inputs_sha256'].items():
        binding[bound_input(name)] = digest
    for name, digest in identity['sources_sha256'].items():
        path = (SYSTEM/name).resolve()
        assert path.is_relative_to(SYSTEM)
        binding[path] = digest
    for path, digest in binding.items():
        assert SHA(path) == digest, str(path)
    return scene, binding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    output.mkdir(parents=True)
    records = []
    closure = {}
    for key in KEYS:
        begin = perf_counter()
        cache = SYSTEM/'dfx/surface_quality/ui_cache_r1'/key
        scene, binding = scene_binding(cache)
        closure.update(binding)
        source_result = bound_input(scene['identity']['result'])
        route_file = source_result/'navigation/route.npz'
        route_json = json.loads((source_result/'navigation/route.json').read_text(encoding='utf-8'))
        route = dict(np.load(route_file,allow_pickle=False))
        mesh = dict(np.load(cache/'mesh.npz',allow_pickle=False))
        p = route['points_lps_mm']
        region = MeshRegion(mesh['points'],mesh['faces'],scene['geometry'])
        reference = MeshClearance(mesh['points'],mesh['faces'])
        distance, closest, _, reference_stats = reference.distance(p)
        engines = {'bounded_NumPy_PS':BatchedMeshClearance(mesh['points'],mesh['faces'])}
        if args.native:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            native = NativeMeshClearance(mesh['points'],mesh['faces'])
            engines.update(native_PS1=native,native_PS4=native)
        samples = {name:[] for name in engines}
        stats = {}
        for repetition in range(3):
            order = list(engines)
            if repetition % 2:order.reverse()
            for name in order:
                kwargs = {'threads':int(name[-1])} if name.startswith('native') else {}
                actual, position, _, profile = engines[name].distance(p,**kwargs)
                np.testing.assert_allclose(actual,distance,rtol=0,atol=1e-11)
                np.testing.assert_allclose(position,closest,rtol=0,atol=1e-11)
                samples[name].append(profile['query_seconds'])
                stats[name] = profile
        report, arrays = audit_polyline(region,p,distance,
            required_radius_mm=route_json['required_radius_mm'],
            resolution_margin_mm=route_json['resolution_margin_mm'])
        np.testing.assert_allclose(arrays['arc_mm'],route['arc_mm'],rtol=0,atol=1e-10)
        tier = 'Q'+str(scene['identity']['bits'])
        target = output/(tier+'_audit.npz')
        np.savez_compressed(target,**arrays)
        count = report['reviewed_prefix_points']
        prefix = output/(tier+'_reviewed_prefix.npz')
        np.savez_compressed(prefix,points_lps_mm=p[:count],arc_mm=arrays['arc_mm'][:count],
                            actual_wall_distance_mm=distance[:count])
        medians = {name:statistics.median(value) for name,value in samples.items()}
        records.append(dict(tier=tier,field_revision=scene['key'],surface_rule=scene['identity']['surface_rule'],
            audit=report,source_route_status=route_json['status'],source_route_reason=route_json['reason'],
            source_route_requested_endpoint_id=route_json['requested_endpoint_id'],
            source_route_selected_endpoint_id=route_json['selected_endpoint_id'],
            instrument_parameters={k:route_json[k] for k in ('required_radius_mm','resolution_margin_mm',
                'minimum_bend_radius_mm','forward_window_mm','scope_diameter_mm','safety_margin_mm')},
            source_binding_sha256={path.relative_to(SYSTEM).as_posix():digest for path,digest in binding.items()},
            distance_query_samples_seconds=samples,distance_query_medians_seconds=medians,
            strongest_measured_PS=min(medians,key=medians.get),reference_distance_profile=reference_stats,
            optimized_distance_profiles=stats,arrays_file=target.name,arrays_sha256=SHA(target),
            prefix_file=prefix.name,prefix_sha256=SHA(prefix),
            full_trial_seconds=perf_counter()-begin,PL_distance_comparison_completed=False,
            prefix_is_new_separate_review_artifact_not_original_route=True))
        print(tier,report['status'],'prefix',count,'/',len(p),flush=True)
    for path, digest in closure.items():assert SHA(path) == digest, str(path)
    sources = ['modules/surface_route/audit.py','modules/surface_route/own_ct_trial.py',
        'modules/surface_quality/mesh_clearance.py','modules/surface_quality/mesh_clearance_batch.py']
    if args.native:
        sources += ['modules/surface_quality/mesh_clearance_native.py','modules/surface_quality/host/build/build.json']
    record = dict(status='own_CT_Q5_Q6_continuous_surface_route_review_passed_limited_prefix_requires_replan',
        platform=sys.platform,cases=records,source_sha256={n:SHA(SYSTEM/n) for n in sources},
        input_hashes_checked_before_and_after=True,PL_access=False,production_changed=False,
        PS_Marching_Cubes_used=False,new_graph_replanning_pending=True,
        clinical_safety_certified=False)
    (output/'acceptance.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(record['status'],flush=True)


if __name__ == '__main__':main()
