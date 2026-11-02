"""Serialize a fresh selected-path audit for the actual navigation scene reader."""
from pathlib import Path
import hashlib,json,time
import numpy as np
from selected_path_r2 import audit_selection
from selected_guidance_r2 import attach
from protocol import validate_stored_audit,route_digest

HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def produce(context,target,selection,session,output):
    output=Path(output)
    if output.exists():raise FileExistsError('A new navigation destination is required')
    start=time.perf_counter()
    report,route,camera=audit_selection(context,target,selection,session)
    report,route=attach(context,selection,report,route)
    validate_stored_audit(route,report)
    if not np.array_equal(camera['position_lps_mm'],route['points_lps_mm'] if len(route['arc_mm'])>1 else np.empty((0,3))):
        raise ValueError('Camera does not follow the checked selected route')
    report.update(centerline_input_sha256=context.metadata['input_sha256'],
        centerline_id=context.metadata['centerline_id'],
        timing=dict(plan_and_camera_seconds=time.perf_counter()-start),
        renderer='not_rendered_by_navigation_data_producer',
        selected_output_source_sha256=sha(Path(__file__)),
        actual_UI_route_replaced=False,
        branch_guidance_application_pending=False)
    output.mkdir(parents=True)
    np.savez_compressed(output/'route.npz',**route)
    np.savez_compressed(output/'camera.npz',**camera)
    matrix=np.column_stack((route['arc_mm'],route['points_lps_mm'],route['radius_mm']))
    np.savetxt(output/'route.csv',matrix,delimiter=',',header='arc_mm,lps_x_mm,lps_y_mm,lps_z_mm,edt_radius_mm',comments='')
    (output/'route.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    # Validate the exact files consumed by backend_core_r6.prepare, not just
    # the objects before serialization. Audit infinities stay in NPZ arrays.
    saved=json.loads((output/'route.json').read_text(encoding='utf-8'))
    with np.load(output/'route.npz',allow_pickle=False) as z:
        loaded={k:z[k] for k in z.files};validate_stored_audit(loaded,saved)
        for name,wanted in route.items():np.testing.assert_array_equal(loaded[name],wanted)
    with np.load(output/'camera.npz',allow_pickle=False) as z:
        for name,wanted in camera.items():np.testing.assert_array_equal(z[name],wanted)
    receipt=dict(schema='kv260.navigation.selected_output.v1',
        status='fresh_selected_path_audit_guidance_and_serialized_scene_inputs_passed',
        selection=selection.binding,route_sha256=route_digest(route),
        point_count=len(route['arc_mm']),branch_cues=len(report['branch_guidance']['events']),
        planning_and_serialization_seconds=time.perf_counter()-start,
        files_sha256={n:sha(output/n) for n in ('route.npz','camera.npz','route.csv','route.json')},
        source_sha256={n:sha(HERE/n) for n in ('selected_output_r1.py','selected_path_r1.py',
            'selected_path_r2.py','selected_guidance_r1.py','selected_guidance_r2.py','selected_guidance_rules_r2.py')},
        result_cached=False,actual_UI_application_verified=False)
    (output/'selected_output.json').write_text(json.dumps(receipt,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    return receipt
