"""Stream-check every owned HLS byte; retain the current reusable HLS component."""
from pathlib import Path,PureWindowsPath
import stat,sys
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import collect_AXIS_DFX_area_dedup_r2 as helper
import collect_server2_four_register_HLS_r2450 as legacy
parent=helper.parent
OUT=ROOT/'results/topology_rank_cache_URAM_HLS_20261020_r9/axis_hls'
parent.OUT=OUT;parent.legacy=legacy;helper.CANONICAL=[]
def check_owner(owner):
 path=PureWindowsPath(owner['windows_root'])
 assert path.parent==PureWindowsPath('D:/') and path.name==owner['name']
 assert path.name.startswith('k26-r2450-') and len(path.name)==26
 assert all(c in '0123456789abcdef' for c in path.name[10:])
 assert owner['remote_root']=='/'+path.as_posix() and owner['job']=='axis_hls'==OUT.name
 return path,owner['remote_root']
def select(names,archive,plan):
 selected=set(parent.read(OUT/'upload_plan.json')['payload_sha256'])|set(plan['input_manifest'])
 selected.update(n for n in names if n in ('terminal.json','state.json','worker_started.json','own_worker_affinity.json',
  'task_started.json','raw_task_receipt.json','task.log','release.json'))
 prefix='workspace/'+(CORE/'HLS_probe_r1').relative_to(ROOT).as_posix()+'/'
 # Keep only this current HLS component, source bindings, reports and receipts.
 # This is reusable compiler state for the active candidate, not other jobs.
 selected.update(n for n in names if n.startswith(prefix))
 for n in selected:
  parent.safe_name(n);assert n in names and not stat.S_ISLNK(archive.getinfo(n).external_attr>>16)
 return selected
parent.check_owner=check_owner;helper.ORIGINAL_SELECT=select
def main():
 from owned_windows_closed_collection import install
 owner=parent.read(OUT/'owner.json');check_owner(owner)
 connect=parent.legacy.connect
 def alive_connect():
  transport=connect();transport.set_keepalive(20);return transport
 parent.legacy.connect=alive_connect
 install(sys.modules[__name__],Path(__file__))
 helper.main()
 receipt=parent.read(OUT/'stream_collection_verified.json');cleanup=parent.read(OUT/'cleanup_verified_stream.json')
 assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
 parent.save(OUT/'direct_stream_verified.json',dict(status='all_owned_HLS_bytes_and_closed_logs_verified_current_component_retained_exact_root_absent',
  archive_SHA256=receipt['compact_archive_SHA256'],original_metadata=receipt['original_archive_metadata'],
  no_complete_raw_archive_or_unpacked_compiler_workspace_written_locally=True,
  source_and_evidence_SHA256={Path(__file__).relative_to(ROOT).as_posix():parent.sha(Path(__file__))},
  PL_accessed=False,production_promoted=False,whole_goal_completed=False))
 print('PASS every owned HLS byte verified; exact terminal task root removed; current component retained',flush=True)
if __name__=='__main__':main()
