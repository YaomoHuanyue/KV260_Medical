"""Validate and copy complete original analysis, never recompute medical results."""
from pathlib import Path
import csv,hashlib,json,shutil,subprocess,time
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
NAV_NAMES=('whole_instrument_profiles.json','whole_alternative_routes.json','whole_comparison_arrays.npz',
    'centerline.json','centerline.npz','route.json','route.npz','route.csv','camera.npz',
    'selected_output.json','branches.json','instrument_profiles.json','alternative_routes.json',
    'anatomical_generations.json','anatomical_generations.npz','anatomical_generation_nodes.csv','dfx_report.json')


def validate(source,input_sha):
    source=Path(source).resolve();pipeline=read(source/'pipeline.json')
    if pipeline.get('status')!='passed' or pipeline.get('input_sha256')!=input_sha:
        raise ValueError('Reports require a completed result for the selected CT')
    files={'pipeline.json':sha(source/'pipeline.json')};nav=source/'navigation'
    if nav.exists() and (nav.is_symlink() or not nav.is_dir()):
        raise ValueError('Navigation report stage must be a regular owned directory')
    for name in NAV_NAMES:
        path=nav/name
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.resolve().parent!=nav.resolve():
                raise ValueError('Report input must be a regular owned file')
            files['navigation/'+name]=sha(path)
    if (source/'selected_pipeline.json').exists():files['selected_pipeline.json']=sha(source/'selected_pipeline.json')
    present=[(nav/n).is_file() for n in NAV_NAMES[:3]]
    if any(present) and not all(present):raise ValueError('Incomplete whole-profile report/array set')
    whole=alternatives=selected=None
    if all(present):
        whole=read(nav/NAV_NAMES[0]);alternatives=read(nav/NAV_NAMES[1]);center=read(nav/'centerline.json')
        common=('schema','input_sha256','centerline_id','target_kind','target_metadata','safety_margin_mm',
                'minimum_bend_radius_mm','scope_diameter_mm','radius_weight','source_sha256')
        if any(whole[k]!=alternatives[k] for k in common) or whole['schema']!='kv260.navigation.raw_comparison.v1':
            raise ValueError('Whole report pair differs')
        if whole['centerline_id']!=center['centerline_id'] or whole['input_sha256']!=center['input_sha256']:
            raise ValueError('Reports belong to a different centerline')
        mask=source/'segmentation/airway_mask.nii.gz'
        if sha(mask)!=whole['input_sha256']:raise ValueError('Reports belong to a different airway mask')
        files['segmentation/airway_mask.nii.gz']=sha(mask)
        if whole['target_kind']=='lesion_candidate':
            lesion=source/'segmentation/nodule_mask.nii.gz'
            if sha(lesion)!=whole['target_metadata']['mask_sha256']:raise ValueError('Reports belong to a different target mask')
            files['segmentation/nodule_mask.nii.gz']=sha(lesion)
        for name,digest in whole['source_sha256'].items():
            producer=(ROOT/'modules/navigation_comparison'/name).resolve()
            if producer.parent!=ROOT/'modules/navigation_comparison' or sha(producer)!=digest:
                raise ValueError('Comparison producer source differs')
        with np.load(nav/'centerline.npz',allow_pickle=False) as z:
            raw=z['indices_zyx']-z['offset_zyx'];root=int(z['root'])
        rows=whole['profiles'];groups=alternatives['groups'];n=int(whole['raw_nodes'])
        if not 1<=len(rows)<=64 or len(rows)!=len(groups) or raw.shape!=(n,3):raise ValueError('Incomplete instrument groups')
        with np.load(nav/NAV_NAMES[2],allow_pickle=False) as a:
            if (not np.array_equal(a['raw_coordinates_zyx'],raw) or
                not np.array_equal(a['diameters_mm'],[v['scope_diameter_mm'] for v in rows]) or
                not np.array_equal(a['diameters_mm'],[v['scope_diameter_mm'] for v in groups]) or
                a['distances'].dtype!=np.float64 or a['distances'].shape!=(len(rows),n) or
                a['parents'].shape!=(len(rows),n) or np.isnan(a['distances']).any()):
                raise ValueError('Complete comparison arrays differ from report groups')
            lookup={tuple(v):i for i,v in enumerate(raw)}
            for i,group in enumerate(groups):
                candidates=group['candidates'];ids=[v['candidate_id'] for v in candidates]
                if len(set(ids))!=len(ids) or len(ids)!=group['candidate_count'] or any(v['candidate_id'] not in ids for v in group['pareto']):
                    raise ValueError('Ambiguous Pareto candidate identity')
                for candidate in candidates:
                    prefix=f'profile_{i}_candidate_{candidate["candidate_id"]}_'
                    if (not np.array_equal(a[prefix+'path_xyz'],candidate['points_lps_mm']) or
                        not np.array_equal(a[prefix+'radii'],candidate['radius_mm'])):
                        raise ValueError('Candidate report differs from full arrays')
                    chain=np.asarray([lookup[tuple(v)] for v in a[prefix+'path_zyx']],np.int32)
                    if (not len(chain) or chain[0]!=root or len(set(chain))!=len(chain) or
                        not np.array_equal(a['parents'][i,chain[1:]],chain[:-1]) or
                        not np.isfinite(a['distances'][i,chain]).all() or
                        not np.array_equal(raw[chain[-1]],candidate['end_zyx'])):
                        raise ValueError('Candidate parent chain differs')
    if (nav/'selected_output.json').exists():
        selected=read(nav/'selected_output.json')
        if not whole or selected['schema']!='kv260.navigation.selected_output.v1':raise ValueError('Selected route requires complete comparison')
        binding=selected['selection']
        if binding['centerline_id']!=whole['centerline_id'] or binding['input_sha256']!=whole['input_sha256']:
            raise ValueError('Selected route anatomy differs')
        for name,digest in binding['comparison_files_sha256'].items():
            if name not in NAV_NAMES[:3] or sha(nav/name)!=digest:raise ValueError('Selected comparison snapshot differs')
        if set(binding['comparison_files_sha256'])!=set(NAV_NAMES[:3]):raise ValueError('Incomplete selected comparison binding')
        if set(selected['files_sha256'])!={'route.npz','route.json','route.csv','camera.npz'}:raise ValueError('Incomplete selected route')
        for name,digest in selected['files_sha256'].items():
            if sha(nav/name)!=digest:raise ValueError('Selected route audit files differ')
    for name,digest in files.items():
        if sha(source/name)!=digest:raise ValueError('Source changed during report preflight')
    return dict(source=source,files=files,whole=whole,alternatives=alternatives,selected=selected,input_sha256=input_sha)


def native_chart(input_path,output_path):
    build=read(HERE/'build/build.json');binary=HERE/'build/report_chart'
    if build['status']!='compiled_headless_native_Qt_chart' or sha(binary)!=build['binary_sha256']:
        raise ValueError('Unverified report chart helper')
    for name,digest in build['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Changed chart source')
    result=subprocess.run([str(binary),str(input_path),str(output_path)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    record=json.loads(result.stdout)
    if record['input_sha256']!=sha(input_path):raise ValueError('Chart input changed')
    wanted=[r for r in read(input_path)['profiles'] if r.get('reachable')]
    if record['reachable_rows']!=wanted:raise ValueError('Chart data differs from original reachability rows')
    record.update(binary_sha256=build['binary_sha256'],chart_sha256=sha(output_path),Qt_chart_source_sha256=sha(ROOT/'ui/releases/feature_completion_r6/reachability_chart.hpp'))
    return record


def write_reports(snapshot,destination,chart=native_chart):
    start=time.perf_counter();source=snapshot['source'];destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for name,digest in snapshot['files'].items():
        if sha(source/name)!=digest:raise ValueError('Source changed before export')
        if not name.startswith('navigation/') and name!='selected_pipeline.json':continue
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
        if sha(target)!=digest:raise ValueError('Copied report differs')
    whole=snapshot['whole'];alternatives=snapshot['alternatives'];selection=snapshot['selected']
    chart_record=None
    if whole:
        profile_keys=('scope_diameter_mm','reachable','closest_lesion_gap_mm','reachable_skeleton_voxels',
            'reachable_centerline_length_mm','path_length_to_closest_point_mm','maximum_geodesic_cost_mm')
        with (destination/'instrument_reachability.csv').open('x',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=profile_keys,extrasaction='ignore');writer.writeheader();writer.writerows(whole['profiles'])
        keys=('scope_diameter_mm','candidate_id','pareto','current_navigation_selected','gap_mm','path_length_mm',
              'minimum_diameter_mm','minimum_bend_radius_mm','bend_radians','score','original_diameter_bend_eligible')
        with (destination/'pareto_paths.csv').open('x',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader()
            for i,group in enumerate(alternatives['groups']):
                front={r['candidate_id'] for r in group['pareto']}
                for row in group['candidates']:
                    chosen=bool(selection and selection['selection']['group_index']==i and selection['selection']['candidate_id']==row['candidate_id'])
                    writer.writerow(dict(row,scope_diameter_mm=group['scope_diameter_mm'],pareto=row['candidate_id'] in front,current_navigation_selected=chosen))
        chart_record=chart(destination/'navigation/whole_instrument_profiles.json',destination/'reachability_chart.png')
    for name,digest in snapshot['files'].items():
        if sha(source/name)!=digest:raise ValueError('Source changed during report export')
    report=dict(schema='kv260.export.complete_reports.v1',status='completed',CT_input_sha256=snapshot['input_sha256'],
        source_result_files_sha256=snapshot['files'],coordinates='LPS',units='mm',
        full_profile_state='exported' if whole else 'not_provided',
        selected_route_state='exported_with_original_audit' if selection else 'not_provided',
        profile_query_count=len(whole['profiles']) if whole else 0,
        candidate_count=sum(len(g['candidates']) for g in alternatives['groups']) if alternatives else 0,
        comparison_is_navigation_safety_certificate=False,chart=chart_record,
        original_anatomical_generation_report_copied='navigation/anatomical_generations.json' in snapshot['files'],
        source_sha256={Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))},
        files={p.relative_to(destination).as_posix():sha(p) for p in destination.rglob('*') if p.is_file()},
        elapsed_seconds=time.perf_counter()-start,medical_results_recomputed=False,PL_bitstream_changed=False)
    (destination/'index.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    return report
