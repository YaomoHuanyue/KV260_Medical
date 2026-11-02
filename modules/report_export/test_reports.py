"""Complete report bytes, array/target bindings and corruption rejection."""
from pathlib import Path
import argparse,csv,hashlib,json,platform,shutil,sys,tempfile,time
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from modules.report_export.reports import validate,write_reports,native_chart,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--run-id',required=True);a=p.parse_args()
    assert a.run_id.replace('_','').isalnum()
    source=a.source.resolve();out=HERE/'results'/a.run_id
    assert not out.exists();out.mkdir(parents=True)
    input_sha=json.loads((source/'pipeline.json').read_text())['input_sha256']
    snapshot=validate(source,input_sha);assert snapshot['whole'] and snapshot['selected']
    work=HERE/'test_work';work.mkdir(exist_ok=True)
    originals={n:sha(source/n) for n in snapshot['files']}
    host='ARM' if platform.machine()=='aarch64' else 'Windows'
    def no_chart(inp,dest):
        return dict(status='not_rendered_on_Windows',original_reachable_row_filter=True,
            reachable_rows=[v for v in json.loads(inp.read_text())['profiles'] if v.get('reachable')])
    chart=native_chart if host=='ARM' else no_chart
    with tempfile.TemporaryDirectory(prefix='report_checks_',dir=work) as temporary:
        temporary=Path(temporary).resolve();assert temporary.is_relative_to(work.resolve())
        start=time.perf_counter();result=write_reports(snapshot,temporary/'normal',chart=chart)
        elapsed=time.perf_counter()-start
        for n,d in result['files'].items():assert sha(temporary/'normal'/n)==d
        for n,d in snapshot['files'].items():
            if n.startswith('navigation/') or n=='selected_pipeline.json':assert sha(temporary/'normal'/n)==d
        with (temporary/'normal/instrument_reachability.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        assert len(rows)==len(snapshot['whole']['profiles'])
        for row,wanted in zip(rows,snapshot['whole']['profiles']):
            for key,value in row.items():
                if isinstance(wanted.get(key),bool):assert value==str(wanted[key])
                elif wanted.get(key) is None:assert value==''
                else:assert float(value)==wanted[key]
        with (temporary/'normal/pareto_paths.csv').open(encoding='utf-8',newline='') as f:paths=list(csv.DictReader(f))
        assert len(paths)==sum(len(g['candidates']) for g in snapshot['alternatives']['groups'])
        selected=[r for r in paths if r['current_navigation_selected']=='True'];assert len(selected)==1
        assert int(selected[0]['candidate_id'])==snapshot['selected']['selection']['candidate_id']
        for row in paths:
            groups=snapshot['alternatives']['groups'];g=next(g for g in groups if g['scope_diameter_mm']==float(row['scope_diameter_mm']))
            candidate=next(c for c in g['candidates'] if c['candidate_id']==int(row['candidate_id']))
            for key in ('gap_mm','path_length_mm','minimum_diameter_mm','score'):
                assert float(row[key])==candidate[key]
        if host=='ARM':
            from PIL import Image
            with Image.open(temporary/'normal/reachability_chart.png') as image:
                assert image.size==(result['chart']['width'],result['chart']['height']) and min(image.size)>1000
                rgb=np.asarray(image.convert('RGB'));assert len(np.unique(rgb.reshape(-1,3),axis=0))>100
            shutil.copyfile(temporary/'normal/reachability_chart.png',out/'reachability_chart.png')
        # Small owned copies keep intentional corruptions away from source results.
        bad=temporary/'source';bad.mkdir()
        for n in snapshot['files']:
            target=bad/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,target)
        rejected=[]
        def expect(name):
            try:validate(bad,input_sha)
            except (ValueError,KeyError,OSError):rejected.append(name)
            else:raise AssertionError('Corruption accepted: '+name)
        def change(name,path,edit):
            path=bad/path;original=path.read_bytes();record=json.loads(original);edit(record)
            path.write_text(json.dumps(record));expect(name);path.write_bytes(original)
        change('wrong_CT','pipeline.json',lambda d:d.update(input_sha256='0'*64))
        change('different_centerline','navigation/whole_instrument_profiles.json',lambda d:d.update(centerline_id='0'*64))
        change('different_target','navigation/whole_alternative_routes.json',lambda d:d['target_metadata'].update(index=999))
        change('different_full_path','navigation/whole_alternative_routes.json',lambda d:d['groups'][0]['candidates'][0]['points_lps_mm'][0].__setitem__(0,1.e9))
        change('selected_audit_file_changed','navigation/selected_output.json',lambda d:d['files_sha256'].update({'route.npz':'0'*64}))
        missing=bad/'navigation/whole_comparison_arrays.npz';saved=missing.read_bytes();missing.unlink();expect('partial_report_array_set');missing.write_bytes(saved)
        with np.load(missing,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
        group=snapshot['alternatives']['groups'][0];candidate=group['candidates'][0]
        raw=arrays['raw_coordinates_zyx'];lookup={tuple(v):i for i,v in enumerate(raw)}
        chain=arrays[f'profile_0_candidate_{candidate["candidate_id"]}_path_zyx']
        assert len(chain)>1;arrays['parents'][0,lookup[tuple(chain[1])]]=-1
        np.savez_compressed(missing,**arrays);expect('wrong_parent_chain');missing.write_bytes(saved)
        # A genuine missing-analysis result publishes explicit not-provided states.
        partial=temporary/'partial';partial.mkdir()
        shutil.copyfile(source/'pipeline.json',partial/'pipeline.json')
        empty=write_reports(validate(partial,input_sha),temporary/'partial_export',chart=chart)
        assert empty['full_profile_state']=='not_provided' and empty['selected_route_state']=='not_provided'
        assert not (temporary/'partial_export/reachability_chart.png').exists()
    assert originals=={n:sha(source/n) for n in originals}
    report=dict(status='complete_original_report_bytes_CSV_arrays_target_selected_audit_and_corruption_checks_passed',
        host=host,normal_report=result,report_export_seconds=elapsed,corruptions_rejected=rejected,
        no_analysis_state_explicit=True,source_result_files_unchanged=True,
        native_chart_rendered=host=='ARM',full_legacy_colored_bundle_not_tested_by_this_unit=True,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'reports.py',HERE/'chart.cpp',HERE/'bundle.py',HERE/'backend.py']},
        source_result_sha256=originals,additional_PL_resources=0,medical_results_recomputed=False,
        GUI_export_button_not_tested_by_this_unit=True,production_promoted=False)
    (out/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],host=host,queries=result['profile_query_count'],candidates=result['candidate_count'],seconds=elapsed,corruptions=len(rejected),chart=host=='ARM')),flush=True)
if __name__=='__main__':main()
