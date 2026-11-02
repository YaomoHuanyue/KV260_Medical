"""CPU-only policy and derived-contract qualification; bounded owned fixtures."""
from pathlib import Path
import argparse,hashlib,importlib,importlib.util,json,os,platform,sys,tempfile,time,unittest

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--system-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--candidate-dir',type=Path);a=p.parse_args()
    root=a.system_root.resolve(strict=True);out=a.output.resolve();assert not out.exists() and out.is_relative_to(root/'results')
    sys.path.insert(0,str(root));os.environ.update(ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='2',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
    source=(a.candidate_dir or root/'modules/image_import/positive_labels_r1').resolve(strict=True)
    assert source.is_relative_to(root)
    paths=[*source.glob('*.py'),*source.glob('*.json'),*source.glob('reference/*'),
           root/'modules/image_import/partial_r1/importer.py',root/'modules/image_import/partial_r1/contracts.py',
           root/'modules/image_import/partial_r1/test_full_contract.py',root/'modules/image_import/partial_r1/test_partial_contract.py',
           root/'modules/segmentation/airway/ct_geometry.py',Path(__file__).resolve()]
    def logical(q):
        if q.is_relative_to(source):return 'modules/image_import/positive_labels_r1/'+q.relative_to(source).as_posix()
        if q==Path(__file__).resolve():return 'tools/test_positive_policy_r32.py'
        return q.relative_to(root).as_posix()
    actual={logical(q):q for q in paths if q.is_file()};assert len(actual)==len([q for q in paths if q.is_file()])
    bindings={n:sha(q) for n,q in actual.items()}
    out.mkdir(parents=True);scratch=out/'scratch';scratch.mkdir();tempfile.tempdir=str(scratch);forbidden=[];bootstrap=[];phase='bootstrap'
    def audit(event,args):
        denied=event in ('subprocess.Popen','os.system','os.kill')
        if event=='subprocess.Popen' and phase=='bootstrap' and args[0] in (None,'lscpu') and args[1] in ('lscpu',['lscpu']):
            bootstrap.append(dict(event=event,executable=args[0],arguments=args[1]));denied=False
        if event=='open' and isinstance(args[0],str):
            denied=denied or args[0].startswith(('/dev/mem','/dev/dri/','/sys/class/fpga_manager/')) or args[0]=='/tmp/kv260-ct-pl.lock'
        if denied:forbidden.append(event);raise RuntimeError('Policy tests must remain CPU/file-only')
    sys.addaudithook(audit)
    # NumPy lazily imports a read-only lscpu/SVE probe. Initialize that exact
    # dependency under its separate recorded allowance, before testing images.
    import numpy.testing
    phase='tests'
    os.environ['KV260_TEST_SYSTEM_ROOT']=str(root)
    # Test a private candidate package without replacing any accepted source.
    parent=importlib.import_module('modules.image_import');name='modules.image_import.positive_labels_r1'
    spec=importlib.util.spec_from_file_location(name,source/'__init__.py',submodule_search_locations=[str(source)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;setattr(parent,'positive_labels_r1',module);spec.loader.exec_module(module)
    tests=importlib.import_module('modules.image_import.positive_labels_r1.test_policy_contracts_r32')
    groups={};suite=unittest.TestSuite()
    for name in ['FullPolicy','PartialPolicy','PositivePolicy','ProbabilityPolicy','DerivedContracts']:
        group=unittest.defaultTestLoader.loadTestsFromTestCase(getattr(tests,name));groups[name]=group.countTestCases();suite.addTest(group)
    start=time.perf_counter()
    with (out/'unittest.log').open('x',encoding='utf8',newline='\n') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    scratch_empty=not list(scratch.iterdir())
    assert all(sha(actual[n])==h for n,h in bindings.items())
    report=dict(schema='kv260.positive_policy.contracts.r32',passed=result.wasSuccessful() and not forbidden and scratch_empty,tests_run=result.testsRun,groups=groups,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),elapsed_seconds=time.perf_counter()-start,
        host=platform.system(),machine=platform.machine(),Python=sys.version,NumPy=tests.np.__version__,SimpleITK=tests.sitk.Version_VersionString(),
        source_SHA256=bindings,sources_unchanged=True,owned_scratch_empty=scratch_empty,forbidden_process_and_hardware_events=forbidden,
        candidate_root=str(source),private_candidate_package_selected_before_import=True,
        dependency_initialization_cpu_probe_events=bootstrap,process_denial_applies_to_entire_image_test_phase=True,
        PL_accessed=False,production_changed=False,new_FPGA_build=False,GUI_verified=False)
    with (out/'verified.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print(json.dumps({k:report[k] for k in ['passed','tests_run','groups','failures','errors','elapsed_seconds','host','machine']}))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
