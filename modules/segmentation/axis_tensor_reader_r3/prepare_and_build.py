"""Keep the original frame generator exactly; build native arithmetic checks only."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'));import project_storage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    project_storage.check(3_000_000)
    parent=ROOT/'dfx/medical/algorithms/segmentation/conv.cpp'
    assert sha(parent)=='3437204a471fccfc3c3c9232daa7c7da4f1d44c52c5adde7f6ef3c393369db18'
    source=parent.read_text();framing=source[source.index('static void read_words'):source.index('extern "C" void ct_reader')]
    header=HERE/'legacy_framing.hpp'
    if header.exists():assert header.read_text()==framing
    else:header.write_text(framing,encoding='utf8',newline='\n')
    out=HERE/'build_native'
    protected=json.loads((ROOT/'results/storage_cleanup_20261015/current_dependencies.json').read_text())
    assert not any('kv260_system/'+p.relative_to(ROOT).as_posix() in protected for p in out.glob('*')),'Preserve a sealed build'
    assert not (HERE/'native_verified.json').exists(),'Preserve a tested build'
    out.mkdir(exist_ok=True);binary=out/'candidate_new.dll';assert not binary.exists()
    prior=json.loads((ROOT/'modules/segmentation/ct_pool_fusion_r1/integration_r1/build_native/compiled.json').read_text())
    compiler=Path(prior['compiler_argv'][0]);assert compiler.is_file()
    argv=[str(compiler),'-std=c++17','-O3','-shared','-DCT_NATIVE','-static-libgcc','-static-libstdc++','-Wno-unknown-pragmas',
        str(HERE/'kernel.cpp'),str(HERE/'native_bridge.cpp'),'-o',str(binary)]
    env=dict(os.environ,PATH=str(compiler.parent)+os.pathsep+os.environ['PATH'])
    with (out/'compile.log').open('wb') as f:r=subprocess.run(argv,cwd=HERE,env=env,stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0,(out/'compile.log').read_text()
    os.replace(binary,out/'candidate.dll')
    names=['kernel.hpp','kernel.cpp','native_bridge.cpp','legacy_framing.hpp','prepare_and_build.py']
    proof=dict(native_library_SHA256=sha(out/'candidate.dll'),compiler_argv=argv,
        original_framing_parent_SHA256=sha(parent),original_frame_code_byte_preserved_after_text_normalization=True,
        source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [HERE/n for n in names]+[parent]},
        HLS_RTL_DFX_physical_and_board_tests_still_required=True,PL_accessed=False,whole_goal_completed=False)
    with (out/'compiled.json').open('w') as f:json.dump(proof,f,indent=2)
    print('PASS native tensor-reader built; no hardware qualification claimed')
if __name__=='__main__':main()
