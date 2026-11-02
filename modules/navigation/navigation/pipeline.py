from pathlib import Path
import json
import time
import platform
import sys
import hashlib
import numpy as np
from .geometry import read_mask, sha256
from .centerline import extract, branch_tree, Centerline
from .planner import lesion_targets, endpoint_target, Target, plan
from .camera import poses
from .guidance import branch_guidance


def write_json(path, data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")


def peak_rss_mib():
    if sys.platform == "linux":
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    return None


def prepare(airway_path, output, root_lps_mm=None, backend='ps',session=None):
    if backend not in ('ps','pl'):raise ValueError('Choose ps or pl backend')
    distance_fn=None
    if backend=='pl':
        volume_distance=getattr(session,'distance_transform',None)
        if callable(volume_distance):distance_fn=volume_distance
        else:
            from pl.runtime import distance_transform
            distance_fn=lambda mask,spacing:distance_transform(mask,spacing,session)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();mask,geometry=read_mask(airway_path);read_seconds=time.perf_counter()-start
    begin=time.perf_counter();c=extract(mask,geometry,root_lps_mm,distance_fn=distance_fn);del mask
    extract_seconds=time.perf_counter()-begin
    begin=time.perf_counter();tree=branch_tree(c);tree_seconds=time.perf_counter()-begin
    c.metadata.update(input_sha256=sha256(airway_path),input_name=Path(airway_path).name,
        timing=dict(read_seconds=read_seconds,extract_seconds=extract_seconds,branch_seconds=tree_seconds),
        host=dict(machine=platform.machine(),python=platform.python_version()),peak_process_rss_mib=peak_rss_mib())
    identity=hashlib.sha256(c.points_lps_mm.tobytes()+c.edges.tobytes()+str(c.root).encode()).hexdigest()
    c.metadata["centerline_id"]=identity
    begin=time.perf_counter();c.save(output/"centerline.npz");write_json(output/"centerline.json",c.metadata)
    write_json(output/"branches.json",tree)
    c.metadata["timing"]["save_seconds"]=time.perf_counter()-begin
    c.metadata["timing"]["prepare_total_seconds"]=time.perf_counter()-start
    write_json(output/"centerline.json",c.metadata)
    return c,tree


def load_prepared(output):
    output=Path(output);meta=json.loads((output/"centerline.json").read_text(encoding="utf-8"))
    if meta.get("schema")!="kv260.navigation.centerline.v1":raise ValueError("Unsupported centerline schema")
    return Centerline.load(output/"centerline.npz",meta)


def choose_target(c, lesion_path=None, lesion_index=0, endpoint_id=None, target_lps_mm=None):
    if sum(x is not None for x in (lesion_path,endpoint_id,target_lps_mm))!=1:
        raise ValueError("Choose exactly one lesion, endpoint or LPS point target")
    if endpoint_id is not None:return endpoint_target(c,int(endpoint_id))
    if target_lps_mm is not None:return Target("manual_point",np.asarray(target_lps_mm,dtype=float).reshape(1,3),{})
    lesion,geometry=read_mask(lesion_path)
    if not c.geometry.matches(geometry):raise ValueError("Airway/lesion geometry mismatch; explicitly resample before navigation")
    targets=lesion_targets(lesion,geometry)
    if not targets:raise ValueError("Lesion candidate mask is empty; select an airway endpoint")
    if lesion_index<0 or lesion_index>=len(targets):raise ValueError("Lesion candidate index outside available components")
    target=targets[lesion_index];target.metadata["mask_sha256"]=sha256(lesion_path)
    return target


def run_route(c, target, output, planner=None, **options):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    if planner is None:
        report,route=plan(c,target,**options);compute=time.perf_counter()-start
        camera=poses(route["points_lps_mm"],route["arc_mm"])
    else:
        if planner.c is not c:raise ValueError('PL planner cache belongs to another centerline scene')
        report,route,camera=planner.plan(target,**options);compute=time.perf_counter()-start
        report['pl_scene']=planner.scene_info
    plan_camera=time.perf_counter()-start
    report["branch_guidance"]=branch_guidance(c,route)
    np.savez_compressed(output/"route.npz",**route)
    np.savez_compressed(output/"camera.npz",**camera)
    matrix=np.column_stack((route["arc_mm"],route["points_lps_mm"],route["radius_mm"]))
    np.savetxt(output/"route.csv",matrix,delimiter=",",header="arc_mm,lps_x_mm,lps_y_mm,lps_z_mm,edt_radius_mm",comments="")
    report.update(centerline_input_sha256=c.metadata["input_sha256"],
        centerline_id=c.metadata["centerline_id"],
        timing=dict(plan_seconds=compute,plan_and_camera_seconds=plan_camera,route_total_seconds=time.perf_counter()-start),
        peak_process_rss_mib=peak_rss_mib(),renderer="not_rendered_by_navigation_data_producer")
    write_json(output/"route.json",report)
    return report
