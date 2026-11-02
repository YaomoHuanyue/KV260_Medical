"""One-off clean-boot static initialization with resident ZOCL retained.

Only the untouched starter shell, zero CU/client state and accepted installed
artifacts are allowed. Never unload ZOCL, reset the board or add a service.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import pwd
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
SHA_PLATFORM='392c9016006b1c7584faf98d932c489cf858819d7edfa14ed416c335bc74ce17'
SHA_STATIC='a70ae87c8551b07ab4a586bbd04b0a22ed5f13a84931111bed1ad2d10b92a192'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def state():
    clients=[]
    for p in Path('/proc').glob('[0-9]*/fd/*'):
        try:
            target=str(p.readlink())
            if 'renderD' in target:clients.append(str(p))
        except (FileNotFoundError,PermissionError,OSError):pass
    ui=[]
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try:
                if p.joinpath('comm').read_text().strip()=='medical_ui':ui.append(p.name)
            except FileNotFoundError:pass
    return dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0').decode(),
        CUs=[p.name for p in Path('/sys/bus/platform/devices').glob('CU.*')],render_clients=clients,UI=ui,
        xclbin=Path('/sys/class/drm/renderD128/device/xclbinid').read_text().strip(),
        overlays=[p.name for p in Path('/sys/kernel/config/device-tree/overlays').iterdir()],
        medical_marker=Path('/run/kv260-dfx-medical-loaded.sha256').exists())


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--initialize',action='store_true');a=p.parse_args()
    assert os.geteuid()==0
    before=state()
    assert before['firmware']=='k26-starter-kits.bit.bin'
    assert before['overlays']==['kv260-xrt-zocl','k26-starter-kits_image_1'] or set(before['overlays'])=={'kv260-xrt-zocl','k26-starter-kits_image_1'}
    assert not any(before[k] for k in ['CUs','render_clients','UI','xclbin','medical_marker'])
    assert any(v.startswith('zocl ') for v in Path('/proc/modules').read_text().splitlines())
    source=Path('/usr/src/kv260-mc-platform-1.0/kv260_mc_platform.c');assert sha(source)==SHA_PLATFORM
    release=ROOT/'dfx/medical/release';manifest=json.loads((release/'manifest.json').read_text())
    assert manifest['offline_verified'] is True and manifest['bit_bin_sha256']==SHA_STATIC
    for name,expected in manifest['files'].items():
        assert Path(name).name==name and sha(release/name)==expected,name
    for name in ['dfx_medical.bin','dfx_medical.dtbo','dfx_medical.xclbin','shell.json']:
        assert sha(Path('/lib/firmware/xilinx/kv260-dfx-medical')/name)==sha(release/name),name
    assert sha(release/'dfx_medical.bin')==SHA_STATIC
    for name in ['mc','smooth','ct','edt','route']:
        assert sha(release/f'medical_{name}_partial.bin')==sha(Path('/lib/firmware')/f'medical_{name}_partial.bin')
    proof=ROOT/'results/medical_clean_boot_init_r10.json'
    if not a.initialize:
        print(json.dumps(dict(status='clean_boot_manual_initialization_preflight_passed',before=before)));return
    assert not proof.exists()
    # First-boot control-lock setup only; existing locks are never truncated.
    lock=Path('/tmp/kv260-ct-pl.lock');created=False
    if not lock.exists():
        fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o660);os.close(fd)
        account=pwd.getpwnam('ubuntu');os.chown(lock,account.pw_uid,account.pw_gid);os.chmod(lock,0o660);created=True
    with lock.open('rb') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert state()==before,'Hardware/client state changed after preflight'
        commands=[]
        preflight=ROOT/'results/medical_clean_boot_init_preflight_r10.json'
        write(preflight,dict(status='all_preconditions_passed_before_static_mutation',before=before,
            platform_source_sha256=SHA_PLATFORM,static_sha256=SHA_STATIC,lock_created_for_fresh_boot=created,
            loader_sha256=sha(Path(__file__))))
        try:
            for argv in [['modprobe','kv260_mc_platform'],['xmutil','unloadapp']]:
                done=subprocess.run(argv,capture_output=True,text=True,check=True);commands.append(dict(argv=argv,stdout=done.stdout,stderr=done.stderr))
            assert not (Path('/sys/kernel/config/device-tree/overlays')/'k26-starter-kits_image_1').exists()
            Path('/sys/class/fpga_manager/fpga0/flags').write_text('0\n')
            argv=['xmutil','loadapp','kv260-dfx-medical']
            done=subprocess.run(argv,capture_output=True,text=True,check=True);commands.append(dict(argv=argv,stdout=done.stdout,stderr=done.stderr))
            after=state()
            assert after['boot_id']==before['boot_id'] and after['firmware']=='dfx_medical.bin'
            assert not any(after[k] for k in ['CUs','render_clients','UI','xclbin'])
            assert 'kv260-xrt-zocl' in after['overlays']
            assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
            driver=list(Path('/sys/bus/platform/drivers/kv260-mc-platform').glob('*:dfx_medical_platform'))
            assert len(driver)==1,'Medical clock/reset platform driver not bound'
            lines=[line.split() for line in Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()]
            clock=next(v for v in lines if v and v[0]=='pl0_ref')
            assert int(clock[1])>0 and int(clock[2])>0 and abs(int(clock[4])-100000000)<=100
            marker=Path('/run/kv260-dfx-medical-loaded.sha256');assert not marker.exists()
            marker.write_text(SHA_STATIC+'\n')
            write(proof,dict(status='accepted_medical_static_initialized_from_clean_starter_without_ZOCL_unload',
                before=before,after=state(),commands=commands,PL0_clock=clock,
                static_sha256=SHA_STATIC,driver_source_sha256=SHA_PLATFORM,
                PL_register_access=False,CU_created=False,ZOCL_unloaded=False,auto_start_changed=False))
            print('medical static initialized; PL0 enabled at',clock[4],'Hz; ZOCL retained',flush=True)
        except BaseException as error:
            write(ROOT/'results/medical_clean_boot_init_failure_r10.json',dict(status='initialization_failed_no_automatic_retry',
                error=str(error),commands=commands,boot_id=before['boot_id'],ZOCL_unloaded=False))
            raise


if __name__=='__main__':main()
