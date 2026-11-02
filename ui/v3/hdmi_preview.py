"""在 HDMI 上临时运行 V3 候选供人工查看；正式 V2 服务先停止，stop 时恢复。
   sudo python3 ui/v3/hdmi_preview.py start [demo|process] | stop | status
   start         ：默认虚拟病例（04_distal_multi_wall）
   start demo    ：真实 CT 及其完整 PL 流程结果，按 F5 录制一键演示
   start process ：只载入真实 CT，按 F6 录制现场完整处理"""
import importlib.util,json,os,signal,subprocess,sys,time
R='/home/ubuntu/jupyter_notebooks/KV260_System';H=R+'/ui/v3';SERVICE='kv260-medical-ui.service';PID=H+'/hdmi_preview.pid'
INPUT=R+'/datasets/virtual_wall_lesions/04_distal_multi_wall/CT-synthetic.nrrd'
RESULT=R+'/ui/releases/streaming_reader_r2/runs/20261031_064542_671f06a4'
DEMO_CT=R+'/fixtures/own_ct/CT-chest.nrrd'
DEMO_RESULT=R+'/ui/runs/20261031_153830_dbfd0345'
spec=importlib.util.spec_from_file_location('runtime',R+'/ui/v2/runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
def alive(pid):
    try:os.kill(pid,0);return open(f'/proc/{pid}/cmdline','rb').read().startswith((H+'/build/medical_ui').encode())
    except OSError:return False
def current():
    try:pid=int(open(PID).read());return pid if alive(pid) else None
    except (OSError,ValueError):return None
def start(kind='default'):
    assert os.geteuid()==0 and current() is None
    subprocess.run(['systemctl','stop',SERVICE],check=True,timeout=120);time.sleep(2);assert not rt.running()
    log=open(H+'/hdmi_preview.log','wb')
    args={'default':['--input',INPUT,'--result',RESULT],'demo':['--input',DEMO_CT,'--result',DEMO_RESULT],'process':['--input',DEMO_CT]}[kind]
    p=subprocess.Popen([H+'/build/medical_ui','--root',R]+args,cwd=R,env=rt.environment(),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    open(PID,'w').write(str(p.pid));print(json.dumps({'preview':'running','kind':kind,'pid':p.pid,'formal_service':'stopped'}))
def stop():
    assert os.geteuid()==0;pid=current()
    if pid:
        os.kill(pid,signal.SIGTERM)
        for _ in range(60):
            if not alive(pid):break
            time.sleep(1)
    if os.path.exists(PID):os.remove(PID)
    subprocess.run(['systemctl','start',SERVICE],check=True,timeout=180)
    print(json.dumps({'preview':'stopped','formal_service':subprocess.check_output(['systemctl','is-active',SERVICE],text=True).strip()}))
if __name__=='__main__':
    if sys.argv[1]=='start':start(sys.argv[2] if len(sys.argv)>2 else 'default')
    else:{'stop':stop,'status':lambda:print(json.dumps({'preview_pid':current()}))}[sys.argv[1]]()
