"""Reject stale comparison files, another target and cross-field parent bundles."""
from pathlib import Path
from types import SimpleNamespace
import argparse,copy,json,shutil,sys,tempfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.surface_actions_r13 import Comparison,verify_comparison,prepare_selected,COMPARISON_FILES
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists()
    platform='Windows' if sys.platform=='win32' else 'ARM'
    label='network_probability_high_ported';base=ROOT/f'modules/surface_route/results/complete_bundles_{platform}_r8'
    parent=base/(label+'_bend_1p0')
    comp=Comparison.from_bundle(parent,ROOT/'ui/runs/20261004_151324_f601e259',ROOT/'fixtures/own_ct/CT-chest.nrrd',native=platform=='ARM')
    source=ROOT/f'modules/surface_route/results/selected_own_CT_{platform}_r13'/label/'comparison'
    tests=[]
    def refused(name,operation):
        try:operation()
        except ValueError:tests.append(name)
        else:raise AssertionError('Accepted '+name)
    verify_comparison(source,comp);tests.append('complete_source_bound_own_CT_comparison_accepted')
    with tempfile.TemporaryDirectory(prefix='selected-negative-r13-',dir=ROOT/'modules/surface_route/results') as tmp:
        folder=Path(tmp)/'comparison';shutil.copytree(source,folder)
        original={name:(folder/name).read_bytes() for name in (*COMPARISON_FILES,'comparison.json')}
        for name in COMPARISON_FILES:
            (folder/name).write_bytes(original[name]+b'changed')
            refused('modified_payload_'+name,lambda:verify_comparison(folder,comp))
            (folder/name).write_bytes(original[name])
        bad=copy.deepcopy(comp.binding);bad['target']=dict(bad['target'],index=-1)
        refused('comparison_for_another_target',lambda:verify_comparison(folder,SimpleNamespace(binding=bad)))
        bad=copy.deepcopy(comp.binding);bad['scalar_sha256']='another-field'
        refused('comparison_for_another_scalar',lambda:verify_comparison(folder,SimpleNamespace(binding=bad)))
        for option in ('complete','source_closure_sha256'):
            receipt=json.loads(original['comparison.json']);receipt[option]=False if option=='complete' else 'another-source'
            (folder/'comparison.json').write_text(json.dumps(receipt),encoding='utf-8')
            refused('wrong_comparison_'+option,lambda:verify_comparison(folder,comp))
            (folder/'comparison.json').write_bytes(original['comparison.json'])
        whole=json.loads(original[COMPARISON_FILES[0]]);whole['binding']['route_id']='mixed-report'
        (folder/COMPARISON_FILES[0]).write_text(json.dumps(whole),encoding='utf-8')
        receipt=json.loads(original['comparison.json']);receipt['files_sha256'][COMPARISON_FILES[0]]=sha(folder/COMPARISON_FILES[0])
        (folder/'comparison.json').write_text(json.dumps(receipt),encoding='utf-8')
        refused('mixed_pair_even_when_payload_hash_is_updated',lambda:verify_comparison(folder,comp))
        for name,raw in original.items():(folder/name).write_bytes(raw)
        out=Path(tmp)/'must-not-publish'
        refused('selected_bundle_from_another_C1_mesh',lambda:prepare_selected(comp,
            base/'accepted_binary_high_ported_bend_1p0',folder,2,5,out))
        assert not out.exists();tests.append('invalid_selected_action_does_not_publish_scene')
    write_json(a.output,dict(status='own_CT_comparison_integrity_target_scalar_parent_and_no_publication_negative_tests_passed',
        platform=platform,tests=tests,test_source_sha256=sha(Path(__file__)),source_comparison_sha256=sha(source/'comparison.json'),
        PL_access=False,production_promoted=False))
    print('passed',len(tests),flush=True)


if __name__=='__main__':main()
