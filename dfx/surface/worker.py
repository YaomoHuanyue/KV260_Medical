"""One task-scoped PL renderer. No daemon/autostart; one request in flight."""
from pathlib import Path
import argparse,json,sys,time,hashlib,re
import numpy as np
from prepare import prepare_case,frame_parameters,sha,ROOT
from runtime import Session
def emit(event,**kw):print(json.dumps(dict(event=event,**kw),ensure_ascii=False),flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',type=Path,required=True);parser.add_argument('--frame',type=Path,required=True);args=parser.parse_args()
    result=args.result.resolve();frame=args.frame.resolve()
    if not (frame.is_relative_to(ROOT.parents[1]/'ui/cache') or (frame.parent==Path('/run/kv260-ui-runtime') and re.fullmatch(r'pl_scope_[0-9]+\.rgba',frame.name))):raise ValueError('Frame outside allowed UI runtime/cache')
    identity=sha(result/'segmentation/airway_mask.nii.gz')+sha(result/'navigation/route.json')+sha(ROOT/'prepare.py')
    cache=ROOT/'cache'/hashlib.sha256(identity.encode()).hexdigest()[:24]
    if not (cache/'scene.json').exists():
        emit('preparing');prepare_case(result,cache)
    meta=json.loads((cache/'scene.json').read_text())
    for info in meta['scenes'].values():
        if sha(cache/info['file'])!=info['sha256']:raise ValueError('Scene cache mismatch')
    if meta['schema']!='kv260.surface.scene.v2':raise ValueError('Obsolete surface cache')
    normal_frame=Path(str(frame)+'.normal.rgba')
    frame.parent.mkdir(parents=True,exist_ok=True)
    loaded=None;frames=0;start=time.monotonic()
    with Session() as session:
        emit('ready',scene=str(cache/'scene.json'))
        for line in sys.stdin:
            req=json.loads(line)
            if req['command']=='stop':break
            if req['command']!='frame':raise ValueError('Unknown command')
            begin=time.monotonic();event=-1
            for cue in meta['events']:
                if cue['show_from_mm']<=req['arc_mm']<=cue['hide_after_mm']:event=cue['id'];break
            key=str(event);info=meta['scenes'][key];upload={}
            if key!=loaded:
                ack,upload=session.transfer((cache/info['file']).read_bytes(),0,1)
                if ack[1]!=info['token'] or ack[2]!=info['token']:raise RuntimeError('Wrong scene token')
                loaded=key
            p,view=frame_parameters(req['camera'],req['forward'],req['up'],meta['geometry'],np.asarray(meta['offset_xyz']),int(req['width']),int(req['height']),int(req['sequence']))
            output,timing=session.transfer(p,1,1+int(p[0])*int(p[1])//8)
            if int(output[1])!=req['sequence'] or int(output[2])!=info['token']:raise RuntimeError('Frame identity mismatch')
            pixels=output[16:].reshape(-1,2)
            np.ascontiguousarray(pixels[:,0]).tofile(frame)
            np.ascontiguousarray(pixels[:,1]).tofile(normal_frame);frames+=1
            emit('frame',**view,path=str(frame),normal_frame_path=str(normal_frame),normal_computation='PL',normal_filter='depth_aware_3x3',branch_event=event,interactive=bool(req.get('interactive',False)),auto_align=bool(req.get('auto_align',False)),manual_yaw_degrees=req.get('manual_yaw_degrees',0),manual_pitch_degrees=req.get('manual_pitch_degrees',0),hardware_seconds=timing['hardware_seconds'],host_seconds=timing['host_seconds'],upload=upload,total_seconds=time.monotonic()-begin)
    emit('stopped',frames=frames,seconds=time.monotonic()-start)
if __name__=='__main__':
    try:main()
    except Exception as e:emit('error',text=str(e));raise
