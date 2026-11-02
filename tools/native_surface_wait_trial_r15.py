"""After full A/B success, build and cooperatively replace only review UI."""
from pathlib import Path
from time import sleep,monotonic
import json,os,signal,subprocess,sys,traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    out=ROOT/'modules/surface_route/results/native_wait_trial_ARM_r15';out.mkdir(exist_ok=False)
    try:
        benchmark=ROOT/'modules/surface_route/results/wait_benchmark_ARM_r15/acceptance.json'
        assert json.loads(benchmark.read_text())['status']=='full_original_and_scoped_CLI_same_input_semantics_and_packets_passed'
        subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'modules/surface_route/board_native_build_r15.py')],cwd=ROOT,check=True)
        # Close the exact manual review candidate, using its supported Qt drain.
        receipt=ROOT/'modules/surface_route/results/native_active_surface_review_ARM_r14d/started.json'
        old=json.loads(receipt.read_text());pid=old['PID'];cmd=Path('/proc')/str(pid)/'cmdline'
        if cmd.exists():
            assert cmd.read_bytes().rstrip(b'\0').split(b'\0')==[n.encode() for n in old['argv']]
            children=Path('/proc')/str(pid)/'task'/str(pid)/'children'
            assert not children.read_text().strip(),'Review UI has an active child; leave it running'
            write_json(out/'graceful_close_requested.json',dict(PID=pid,argv=old['argv'],signal='SIGTERM',forced=False))
            os.kill(pid,signal.SIGTERM);deadline=monotonic()+45
            while cmd.exists() and monotonic()<deadline:sleep(.25)
            if cmd.exists():raise RuntimeError('Supported UI drain not finished; never force kill')
        subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/active_surface_GUI_trial_r15.py')],cwd=ROOT,check=True)
        proof=ROOT/'modules/surface_route/results/native_active_surface_GUI_ARM_r15/acceptance.json'
        assert json.loads(proof.read_text())['status']=='actual_HDMI_current_surface_comparison_target_change_selected_C9_and_PS_PL_replay_passed'
        write_json(out/'acceptance.json',dict(status='native_R15_controls_selected_navigation_and_same_input_PS_PL_passed',
            benchmark_sha256=sha(benchmark),actual_GUI_sha256=sha(proof),supervisor_sha256=sha(Path(__file__)),
            production_promoted=False,new_bitstream=False))
        print('Native R15 trial passed',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
