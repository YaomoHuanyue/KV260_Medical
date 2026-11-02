"""Derive a separate FMA2 host and preserve the complete BRAM trial API."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'dfx/smooth_speed'
HOST=BASE/'host_FMA2_r1'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def emit(source,target,pairs):
    text=source.read_text();rows=[]
    for before,after,count in pairs:
        assert text.count(before)==count,(target.name,before,text.count(before))
        text=text.replace(before,after);rows.append(dict(before=before,after=after,occurrences=count))
    assert not target.exists()
    with target.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    return dict(parent=source.relative_to(ROOT).as_posix(),parent_SHA256=sha(source),
        candidate=target.relative_to(ROOT).as_posix(),candidate_SHA256=sha(target),literal_edits=rows)


def main():
    assert not HOST.exists();HOST.mkdir();rows=[]
    parent=BASE/'host_BRAM_r2634'
    rows.append(emit(parent/'bridge.cpp',HOST/'bridge.cpp',[
        ('../manual_bram_apply_r2585/mesh_smooth.hpp','../shared_fma2_r1/mesh_smooth.hpp',1),
        ('    try{auto& s=static_cast<Context*>(handle)->session;',
         '    try{require(handle,"Null smoothing context");auto& s=static_cast<Context*>(handle)->session;',1)]))
    old='''  auto path=project_root?std::filesystem::path(project_root)/"dfx"/"medical":std::filesystem::current_path();
  require(path.is_absolute()&&std::filesystem::is_directory(path),"Absolute medical project root required");
  return path;'''
    new='''  require(project_root&&*project_root,"Explicit FMA2 project root required before hardware access");
  std::filesystem::path project(project_root);
  require(project.is_absolute()&&project.lexically_normal()==project&&std::filesystem::is_directory(project)&&std::filesystem::canonical(project)==project,"Canonical absolute FMA2 root required before hardware access");
  auto release=project/"dfx/smooth_speed/release_FMA2_r1";
  require(std::filesystem::is_regular_file(release/"manifest.json")&&std::filesystem::is_regular_file(release/"native_guard.txt"),"Qualified FMA2 release required before hardware access");
  require(readfile(release/"native_guard.txt")=="KV260_FMA2_100MHZ_FULLPR_PAIRED_MANUAL_RELEASE\\n","Qualified FMA2 marker required before hardware access");
  require(same_file(release/"medical_smooth_speed_FMA2_r1_partial.bin","/lib/firmware/medical_smooth_speed_FMA2_r1_partial.bin"),"Qualified FMA2 partial identity required before hardware access");
  auto path=project/"dfx"/"medical";
  require(std::filesystem::is_directory(path),"Absolute medical project root required before hardware access");
  return path;'''
    rows.append(emit(parent/'runtime.hpp',HOST/'runtime.hpp',[
        ('BRAM_r2634','FMA2_r1',6),(old,new,1)]))
    rows.append(emit(parent/'file_io.hpp',HOST/'file_io.hpp',[]))
    oldbuild=ROOT/'tools/build_BRAM_smoothing_host_r2634.py'
    rows.append(emit(oldbuild,ROOT/'tools/build_FMA2_smoothing_host_r1.py',[
        ('BRAM_r2634','FMA2_r1',2),
        ('    started=time.perf_counter()', '    os.nice(10);os.sched_setaffinity(0,{2})\n    started=time.perf_counter()',1)]))
    for oldname,newname in [('runtime_BRAM_r2634.py','runtime_FMA2_r1.py'),
        ('trial_backend_BRAM_r2634.py','trial_backend_FMA2_r1.py'),('test_board_BRAM_r2634.py','test_board_FMA2_r1.py')]:
        source=BASE/oldname;text=source.read_text();pairs=[]
        for before,after in [('BRAM_r2634','FMA2_r1'),('seal_BRAM_smoothing_release_r2634','seal_FMA2_smoothing_release_r1')]:
            if before in text:pairs.append((before,after,text.count(before)))
        rows.append(emit(source,BASE/newname,pairs))
    binding={}
    for row in rows:
        binding[row['parent']]=row['parent_SHA256'];binding[row['candidate']]=row['candidate_SHA256']
    for p in [BASE/'shared_fma2_r1/mesh_smooth.hpp',BASE/'axi_profile_r312/host_snapshot_r354.hpp',Path(__file__)]:
        binding[p.relative_to(ROOT).as_posix()]=sha(p)
    value=dict(schema='kv260.FMA2.host.derivation.v1',derivations=rows,source_sha256=binding,
        original_speed_run_body_and22_DMA_guards_and17_register_fields_unchanged=True,
        explicit_pre_FileLock_MMIO_XRT_release_gate_added=True,null_restore_refused=True,
        original_three_structure_SciPy5e5_strongestPS1_PS4_trial_preserved=True,
        original_queue2_single_background_XRT_owner_preserved=True,
        source_full_RTL_and100MHz_PR_proofs_already_available=True,
        native_compilation_and_actual_board_speed_still_required=True,PL_accessed=False,production_promoted=False)
    (HOST/'derivation.json').write_text(json.dumps(value,indent=2)+'\n')
    print('PREPARED FMA2 same-ABI driver and complete three-structure trial; release/firmware unchanged')


if __name__=='__main__':main()
