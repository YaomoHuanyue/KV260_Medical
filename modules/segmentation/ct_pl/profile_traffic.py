"""Measure existing transfer counters and sampled handshake states without new PL.

Transfer counts are exact modulo 32 bits. Handshake histograms are observations
at Linux-scheduled sample times, never exact stall-cycle or MAC busy counters.
"""
import sys,os,json,time,ctypes,hashlib,resource,argparse,mmap,pwd
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.run import ROOT,backend
from ct_pl.runtime import XRTInteger
from ct_pl.fused_graph import FusedGraph
from ct_pl.stream_graph import ContextPreparer
from ct_pl.read_status import NAMES
from airway.ct_geometry import prepare_grid
from airway.ct_segmentation import write_json

CHANNELS=[NAMES[i*2].removesuffix('valid') for i in range(16)]
COUNTERS=['clock_cycles']+[n+'transfers' for n in CHANNELS]
PHASES=['input_copy','input_sync','control','pl_wait','output_sync','output_copy','output_prepare_sync']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def expected(h,w,ci,co,k,fused):
    count=h*w;ig=(ci+7)//8;og=(co+7)//8
    return {'reader_rtransfers':(count*ig+3)//4,
            'conv_rtransfers':((ci+3)//4)*og*k*k,
            'writer_wtransfers':(count*og+3)//4,
            'reader_ttransfers':(count*ig+3)//4 if k==1 else (h+2)*(w+2)*ig,
            'conv_input_ttransfers':(count*ig+3)//4 if k==1 else (h+2)*(w+2)*ig,
            'conv_output_ttransfers':count*og,'writer_ttransfers':count*og}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ['CT_PL_STATUS_PATH']=str(out/'status.json')
    write_json(out/'status.json',dict(status='running',pid=os.getpid()))
    manifest=json.loads((ROOT/'ct_pl/package/debug_monitor.json').read_text())
    info=json.loads((ROOT/'ct_pl/package/build_info.json').read_text())
    prepared=json.loads((ROOT/'ct_pl/build/bottleneck_profile/sources.json').read_text())
    loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
    assert loaded==manifest['bit_bin_sha256']==sha(ROOT/'ct_pl/package/ct_segmentation.bit.bin')
    assert loaded==sha('/lib/firmware/xilinx/kv260-ct-segmentation/ct_segmentation.bit.bin')
    assert manifest['traffic_history'] and not manifest['pending_clean_boot']
    assert prepared['original_driver_sha256']==info['host_sources']['ct_pl/xrt_bridge.cpp']==sha(ROOT/'ct_pl/xrt_bridge.cpp')
    assert prepared['diagnostic_driver_sha256']==sha(ROOT/'ct_pl/build/bottleneck_profile/traffic_xrt.cpp')
    assert prepared['monitor_header_sha256']==sha(ROOT/'ct_pl/traffic_monitor.hpp')
    for name in ['ct_pl/run.py','ct_pl/runtime.py','ct_pl/stream_graph.py','ct_pl/fused_graph.py','ct_pl/graph_ops.cpp','ct_pl/build/libct_xrt.so','ct_pl/build/libct_graph_ops.so']:
        assert info['host_sources'][name]==sha(ROOT/name),name
    # Map only the passive monitor while privileged, then run XRT as ubuntu.
    # Ubuntu's protected_regular policy blocks root O_CREAT on its /tmp lock.
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
    mapping=mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x80030000)
    storage=(ctypes.c_uint32*1024).from_buffer(mapping)
    assert storage[1]==0xffffffff
    diagnostic=ctypes.CDLL(str(ROOT/'ct_pl/build/bottleneck_profile/libct_traffic.so'))
    diagnostic._ct_monitor_mapping=mapping;diagnostic._ct_monitor_storage=storage
    diagnostic.ct_profile_set_gpio.argtypes=[ctypes.c_void_p];diagnostic.ct_profile_set_gpio.restype=None
    diagnostic.ct_profile_set_gpio(ctypes.addressof(storage))
    if os.geteuid()==0:
        user=pwd.getpwnam('ubuntu');os.chown(out,user.pw_uid,user.pw_gid)
        os.chown(out/'status.json',user.pw_uid,user.pw_gid)
        os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    image=prepare_grid(sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd')));ct=sitk.GetArrayFromImage(image)
    folder=ROOT/'outputs/ct_accuracy_v2/pl_model'
    previous=json.loads((ROOT/'outputs/ct_accuracy_v2/board_pl_profile_tripixel768/profile.json').read_text())
    input_reference={r['slice']:[v['input_sha256'] for v in r['layers']] for r in previous['rows'] if r.get('model')=='outputs/ct_accuracy_v2/pl_model' and r.get('scheduler')=='fused' and 'slice' in r}
    references={};rows=[];timings=[];ops=[];b=None
    try:
        for mode,period in [('production',None),('counter',0),('sample50',50)]:
            os.environ.update(CT_PL_WAIT_MODE='adaptive',CT_PL_POLL_US='10',CT_PL_CLEAN_BO='1',CT_PS_POOL_FUSION='1')
            if period is None:b=backend(output_pool=True)
            else:
                os.environ.update(CT_PROFILE_COUNTERS='1',CT_PROFILE_SAMPLE_US=str(period))
                b=XRTInteger(ROOT/'ct_pl/build/bottleneck_profile/libct_traffic.so',ROOT/'ct_pl/package/ct_segmentation.xclbin',pl_quantization=True,output_pool=True)
                # Leases retain their CDLL object, which in turn retains this
                # mapping even if an exception keeps an output/traceback alive.
                b.lib._ct_monitor_mapping=mapping;b.lib._ct_monitor_storage=storage
                b.pl_activation_lut=True;b.pointwise_streaming=True;b.spatial_streaming=True
                b.lib.ct_profile_read.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint];b.lib.ct_profile_read.restype=ctypes.c_uint
            graph=FusedGraph(folder,b);prep=ContextPreparer(graph,ct,image.GetSpacing()[2]);graph(prep(90))
            actual=b.conv_quantized;calls=[];op_calls=[];validate=True
            def measured(id,x,w,*params):
                digest=hashlib.sha256(x.tobytes()).hexdigest() if validate else None
                h,width=x.shape[2:];co,ci,k,_=w.shape
                floor=(h*width*((co+7)//8)*((ci+31)//32) if k==1 else ((h*width+2)//3)*((co+15)//16)*9*((ci+15)//16))
                tick=time.perf_counter();got=actual(id,x,w,*params);elapsed=time.perf_counter()-tick
                phases={n:b.lib.ct_last_phase(b.handle,i) for i,n in enumerate(PHASES)}
                row=dict(layer=id,input_shape=list(x.shape),weights_shape=list(w.shape),input_sha256=digest,host_and_pl_seconds=elapsed,phases=phases,compute_loop_floor_cycles=floor,compute_loop_floor_seconds=floor/1e8,nominal_useful_macs=h*width*ci*co*k*k)
                if period is not None:
                    metrics=np.zeros(84,np.uint64);assert b.lib.ct_profile_read(b.handle,metrics.ctypes.data,84)==84
                    counts={n:int(v) for n,v in zip(COUNTERS,metrics[:17])}
                    for name,value in expected(h,width,ci,co,k,id in graph.fused_layers).items():
                        assert counts[name]==value,(id,name,counts[name],value)
                    assert counts['writer_awtransfers']==counts['writer_btransfers']
                    assert counts['ps_wtransfers']==counts['writer_wtransfers']*2
                    row['counters']=counts
                    row['sample_count']=int(metrics[17]);row['first_sample_ns']=int(metrics[18]);row['last_sample_ns']=int(metrics[19])
                    row['sampled_states']={n:[int(v) for v in metrics[20+i*4:24+i*4]] for i,n in enumerate(CHANNELS)}
                    assert all(sum(v)==row['sample_count'] for v in row['sampled_states'].values())
                calls.append(row);return got
            b.conv_quantized=measured
            for name in ['ct_pool_transform','ct_join_transform','ct_transform','ct_context5','ct_hu_lut']:
                fn=getattr(graph.ops,name)
                def wrapped(*args,_fn=fn,_name=name):
                    tick=time.perf_counter();_fn(*args)
                    shape=([int(v) for v in args[3:9]] if _name=='ct_join_transform' else [int(v) for v in args[2:6]] if _name=='ct_transform' else [int(v) for v in args[2:5]] if _name=='ct_pool_transform' else [int(v) for v in args[6:10]] if _name=='ct_context5' else [int(args[2])])
                    op_calls.append(dict(op=_name,seconds=time.perf_counter()-tick,shape=shape))
                setattr(graph.ops,name,wrapped)
            for z in [0,90,len(ct)-1]:
                calls.clear();op_calls.clear();got=graph(prep(z))
                assert [r['input_sha256'] for r in calls]==input_reference[z]
                if period is None:references[z]=got.copy()
                else:np.testing.assert_array_equal(got,references[z])
                rows.append(dict(mode=mode,slice=z,layers=list(calls),all_inputs_exact=True,logits_exact=True))
                print(mode,'slice',z,'all 18 inputs and logits exact',flush=True)
            validate=False;graph.return_quantized=True
            for repeat in range(7):
                calls.clear();op_calls.clear();prep.planes.clear()
                t=time.perf_counter();x=prep(90);input_time=time.perf_counter()-t
                hw=b.hardware_seconds;cpu=time.process_time();t=time.perf_counter();got=graph(x);elapsed=time.perf_counter()-t
                np.testing.assert_array_equal(got.data>=got.zero,references[90]>=0)
                timings.append(dict(mode=mode,repeat=repeat+1,graph_seconds=elapsed,input_seconds=input_time,process_cpu_seconds=time.process_time()-cpu,pl_wait_seconds=b.hardware_seconds-hw,layers=list(calls),native_ops=list(op_calls)))
                del got
            b.conv_quantized=actual
            if period is not None:
                held=b.allocate_activation((8,8,16));b.close()
                held.fill(5);assert np.all(held==5)
                del held # Final lease closes the diagnostic context/monitor.
            else:b.close()
            b=None
            # No mapped output survives between device contexts.
            del graph,prep,x
        sources={n:sha(ROOT/n) for n in ['ct_pl/profile_traffic.py','ct_pl/traffic_monitor.hpp','ct_pl/build/bottleneck_profile/traffic_xrt.cpp','ct_pl/build/bottleneck_profile/libct_traffic.so','ct_pl/build/libct_xrt.so']}
        write_json(out/'report.json',dict(status='completed',loaded_bit_bin_sha256=loaded,model_sha256=json.loads((folder/'graph.json').read_text())['source_sha256'],clock_hz=100000000,validation_rows=rows,timings=timings,sources=sources,state_fields=['neither','valid_without_ready','ready_without_valid','transfer'],sample_requested_microseconds=50,monitor_mapping_lease_lifetime_verified=True,exact_stall_cycle_counters_available=False,exact_mac_busy_counter_available=False,notes=['Counter snapshots are exact transfer counts modulo 32 bits, taken with no other PL job active.','Clock window covers IP launch/completion and polling, not isolated MAC busy cycles.','Handshake state percentages are Linux-scheduled observations, not cycle-exact utilization.','Separate single-slice graphs; timing is not the two-slice full-volume benchmark.','Compute loop floor excludes weight setup, pipeline fill/drain, DDR stalls and completion polling.'],process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
        write_json(out/'status.json',dict(status='completed'));print('PASS: traffic counts, inputs, logits and masks match',flush=True)
    except Exception as exc:
        write_json(out/'status.json',dict(status='failed',error=str(exc)));raise
    finally:
        if b is not None:b.close()
        os.close(fd) # mmap remains owned by any surviving library/output lease.

if __name__=='__main__':main()
