"""Independent CT segmentation PL validation and detached full-volume inference."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,hashlib,json,os,resource,subprocess,time,traceback
import numpy as np
import SimpleITK as sitk
from ct_pl.runtime import Graph,XRTInteger
from airway.ct_segmentation import read_ct,write_json,write_like,sha256,agreement,refine_airway,preview,require_geometry
from airway.ct_geometry import prepare_grid,make_context,largest_airway_component
ROOT=Path(__file__).resolve().parents[1]

def tensor(ct,z,spacing_z=None):
    if spacing_z is not None:x=make_context(ct,z,spacing_z)
    else:
        idx=np.clip(np.arange(z-2,z+3),0,len(ct)-1);x=(np.clip(ct[idx].astype(np.float32),-1000,400)+1000)/1400
    h,w=x.shape[-2:];return np.pad(x[None],((0,0),(0,0),(0,(-h)%8),(0,(-w)%8)),mode='edge')

def backend(output_pool=False):
    firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
    if firmware.read_bytes().rstrip(b'\0')!=b'ct_segmentation.bit.bin':
        raise RuntimeError('未加载匹配的 CT 分割固件，请先手动加载。')
    os.environ.setdefault('CT_PL_WAIT_MODE','adaptive')
    os.environ.setdefault('CT_PL_POLL_US','10' if os.environ['CT_PL_WAIT_MODE']=='adaptive' else '50')
    os.environ.setdefault('CT_PL_CLEAN_BO','1')
    manifest=json.loads((ROOT/'ct_pl/package/debug_monitor.json').read_text())
    loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
    if loaded!=manifest['bit_bin_sha256']:
        raise RuntimeError('Staged CT firmware is not loaded; reset the board before PL validation')
    result=XRTInteger(ROOT/'ct_pl/build/libct_xrt.so',ROOT/'ct_pl/package/ct_segmentation.xclbin',pl_quantization=manifest.get('pl_requantization',False),output_pool=output_pool)
    result.pointwise_streaming=manifest.get('pointwise_streaming',False)
    result.spatial_streaming=manifest.get('spatial_streaming',False)
    result.pl_activation_lut=manifest.get('pl_activation_lut',False)
    return result

def smoke(out,model_dir):
    state=out.parent/'hardware_status.json';os.environ['CT_PL_STATUS_PATH']=str(state)
    write_json(state,{'status':'running','pid':os.getpid(),'action':'smoke'})
    b=None
    try:
        b=backend();vectors=np.load(model_dir/'layer_vectors.npz',allow_pickle=False);results=[]
        plan=json.loads((model_dir/'graph.json').read_text());arrays=dict(np.load(model_dir/'tensors.npz',allow_pickle=False));quant_nodes={}
        for pos,node in enumerate(plan['nodes'][:-1]):
            if node['op']=='Conv' and plan['nodes'][pos+1]['op']=='QuantizeLinear':quant_nodes[node['integer']['id']]=(node,plan['nodes'][pos+1])
        for id in range(18):
            x,w,expected=[vectors[f'{n}_{id}'] for n in ['x','w','y']]
            got=b.conv(id,x,w);np.testing.assert_array_equal(got,expected)
            row={'layer':id,'input_shape':list(x.shape),'weights_shape':list(w.shape),'max_integer_error':0}
            if b.pl_quantization:
                node,q=quant_nodes[id];c=node['integer'];bias=arrays[c['bias']];scale=arrays[c['input_scale']]*arrays[c['weight_scale']];qs,qz=[arrays[n] for n in q['inputs'][1:]]
                reference=np.clip(np.rint((expected+bias[None,:,None,None]).astype(np.float32)*scale[None,:,None,None]/qs)+qz,-128,127).astype(np.int8)
                quantized=b.conv_quantized(id,x,w,bias,scale,qs,qz);np.testing.assert_array_equal(quantized,reference)
                row['pl_requantization_exact']=True
            results.append(row)
            print('PL layer',id,'exact',flush=True)
        plan=json.loads((model_dir/'graph.json').read_text())
        loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
        report={'status':'completed','loaded_bit_bin_sha256':loaded,'model_sha256':plan['source_sha256'],'layers':results,'hardware_seconds':b.hardware_seconds,'pl_conv_calls':b.calls,'accumulator_dtype':'int32','pl_requantization':b.pl_quantization,'pointwise_streaming':b.pointwise_streaming,'spatial_streaming':b.spatial_streaming,'exact':True}
        write_json(out,report)
        write_json(model_dir/'board_layer_validation.json',report)
        write_json(state,{'status':'completed','pid':os.getpid(),'action':'smoke'})
    except Exception as exc:
        write_json(state,{'status':'failed','pid':os.getpid(),'action':'smoke','error':str(exc)})
        raise
    finally:
        if b is not None:b.close()

def worker(a):
    os.environ['CT_PL_STATUS_PATH']=str(a.output/'status.json')
    started=time.perf_counter();original=read_ct(a.input);phases={'ct_read_seconds':time.perf_counter()-started}
    plan=json.loads((a.model_dir/'graph.json').read_text());physical='preprocessing' in plan
    image=prepare_grid(original) if physical else original;ct=sitk.GetArrayFromImage(image)
    spacing_z=image.GetSpacing()[2] if physical else None
    if max(ct.shape[1:])>512:raise ValueError('Current PL engine supports at most 512x512 per slice')
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    graph_type=Graph
    if a.scheduler=='int8':
        from ct_pl.quantized_runtime import QuantizedGraph
        graph_type=QuantizedGraph
    elif a.scheduler=='native':
        from ct_pl.native_graph import NativeGraph
        graph_type=NativeGraph
    elif a.scheduler=='fused':
        from ct_pl.fused_graph import FusedGraph
        graph_type=FusedGraph
    elif a.scheduler in ['stream','mapped']:
        from ct_pl.stream_graph import StreamGraph,MappedGraph
        graph_type=MappedGraph if a.scheduler=='mapped' else StreamGraph
    b=backend(output_pool=a.scheduler in ['mapped','fused']);graph=graph_type(a.model_dir,b);masks={n:np.zeros(ct.shape,np.uint8) for n in ['lung','airway','nodule']}
    graph.return_quantized=a.scheduler in ['stream','mapped','fused'] and os.environ.get('CT_PS_DIRECT_MASK','1')=='1'
    prepare=None
    if a.scheduler in ['stream','mapped','fused']:
        from ct_pl.stream_graph import ContextPreparer
        prepare=ContextPreparer(graph,ct,spacing_z)
    times=[];hardware=[];repeat_hashes=[];cpu_times=[];skipped_sync=[]
    from ct_pl.slice_pipeline import infer_slices
    setup_seconds=time.perf_counter()-started
    recorder=None
    if a.save_airway_logits:
        from airway.airway_detail import LogitRecorder
        recorder=LogitRecorder(a.output,image)
    try:
        # Full-size warmup is reported separately.
        tick=time.perf_counter();graph(prepare(len(ct)//2) if prepare else tensor(ct,len(ct)//2,spacing_z));warm=time.perf_counter()-tick
        for repeat in range(a.repeats):
            tick=time.perf_counter();hw_begin=b.hardware_seconds;cpu_begin=time.process_time()
            sync_before=[b.lib.ct_skipped_sync(b.handle,i) for i in range(4)] if hasattr(b.lib,'ct_skipped_sync') else [0]*4
            inputs=prepare.slices() if prepare else ((z,tensor(ct,z,spacing_z)) for z in range(len(ct)))
            for z,prediction in infer_slices(graph,inputs,a.slice_workers):
                from ct_pl.quantized_runtime import Quantized
                if isinstance(prediction,Quantized):
                    # For scalar finite positive scale, (INT8-zero)*scale >= 0
                    # is exactly INT8 >= zero, including equality at zero.
                    if prediction.data.dtype!=np.int8 or prediction.zero.dtype!=np.int8 or prediction.scale.size!=1 or prediction.zero.size!=1 or not np.isfinite(prediction.scale).all() or not (prediction.scale>=np.finfo(np.float32).tiny).all() or not (prediction.scale<=np.finfo(np.float32).max/255).all():
                        raise ValueError('Direct mask requires finite positive scalar INT8 quantization')
                    y=prediction.data[0,:,:ct.shape[1],:ct.shape[2]];threshold=prediction.zero.item()
                else:
                    y=prediction[0,:,:ct.shape[1],:ct.shape[2]];threshold=0
                    if not np.isfinite(y).all():raise ValueError('Non-finite graph output')
                for c,n in enumerate(masks):masks[n][z]=y[c]>=threshold
                if recorder is not None and repeat==0:recorder.record(z,prediction)
                write_json(a.output/'status.json',{'status':'running','backend':'pl_int8_convolution_ps_graph','repeat':repeat+1,'repeats':a.repeats,'slice':z+1,'slices':len(ct),'elapsed_seconds':time.perf_counter()-started,'inference_elapsed_seconds':sum(times)+time.perf_counter()-tick,'stage':'inference','pid':os.getpid()})
            times.append(time.perf_counter()-tick);hardware.append(b.hardware_seconds-hw_begin);cpu_times.append(time.process_time()-cpu_begin)
            skipped_sync.append([b.lib.ct_skipped_sync(b.handle,i)-sync_before[i] for i in range(4)] if hasattr(b.lib,'ct_skipped_sync') else [0]*4)
            hashes={n:hashlib.sha256(m).hexdigest() for n,m in masks.items()}
            if repeat_hashes and hashes!=repeat_hashes[0]:raise ValueError('Full-volume outputs changed between benchmark repeats')
            repeat_hashes.append(hashes)
        calls=b.calls
        pooled_bytes=b.lib.ct_output_pool_bytes(b.handle) if b.output_pool else 0
    finally:b.close()
    write_json(a.output/'status.json',{'status':'running','stage':'postprocess','repeat':a.repeats,'repeats':a.repeats,'slice':len(ct),'slices':len(ct),'elapsed_seconds':time.perf_counter()-started,'pid':os.getpid()})
    tick=time.perf_counter();write_like(masks['airway'],image,a.output/'airway_mask_network.nii.gz')
    phases['raw_mask_save_seconds']=time.perf_counter()-tick
    tick=time.perf_counter()
    if physical:masks['airway'],refinement=largest_airway_component(masks['airway'])
    else:masks['airway'],refinement=refine_airway(image,masks['airway'],include_proximal=False)
    post=time.perf_counter()-tick
    tick=time.perf_counter()
    same_grid=all(getattr(image,name)()==getattr(original,name)() for name in ['GetSize','GetSpacing','GetOrigin','GetDirection'])
    phases['identity_geometry_skipped']=physical and same_grid
    if physical and not same_grid:
        for name,mask in masks.items():
            pred=sitk.GetImageFromArray(mask);pred.CopyInformation(image)
            masks[name]=sitk.GetArrayFromImage(sitk.Resample(pred,original,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkUInt8))
        image=original
    phases['restore_geometry_seconds']=time.perf_counter()-tick
    # Integration: references are explicitly chosen per case, never implicitly
    # compare a new patient against the development CT.
    reference=getattr(a,'reference_dir',None)
    comparisons={};phases['final_mask_save_seconds']=0.;phases['reference_check_seconds']=0.
    for n,m in masks.items():
        tick=time.perf_counter();write_like(m,image,a.output/f'{n}_mask.nii.gz');phases['final_mask_save_seconds']+=time.perf_counter()-tick
        tick=time.perf_counter()
        if reference is not None:
            ref=sitk.ReadImage(str(reference/f'{n}_mask.nii.gz'));require_geometry(ref,image)
            comparisons[n]=agreement(m,sitk.GetArrayFromImage(ref));comparisons[n]['metric_kind']='pl_vs_pc_int8_not_ground_truth'
        phases['reference_check_seconds']+=time.perf_counter()-tick
    tick=time.perf_counter()
    if not getattr(a,'no_preview',False):preview(image,masks,a.output/'ct_overlay.png',compress_level=1)
    phases['preview_seconds']=time.perf_counter()-tick
    tick=time.perf_counter();input_hash=sha256(a.input);phases['input_hash_seconds']=time.perf_counter()-tick
    logits_metadata=None
    if recorder is not None:
        tick=time.perf_counter();logits_metadata=recorder.finish(input_hash,plan['source_sha256'])
        phases['airway_logits_save_seconds']=time.perf_counter()-tick
    report={'status':'completed','backend':'pl_int8_convolution_ps_graph','input_sha256':input_hash,'device_requested':'pl',
        'model_status':'experimental_multicase_partial_labels' if physical else 'experimental_single_case_distillation','model_sha256':plan['source_sha256'],'physical_context':physical,'pl_inference_implemented':True,'all_operators_on_pl':False,
        'pl_operators':('all 18 convolutions with INT8 requantization; fused ReLU and exact activation LUT on 8 single-consumer chains, AXIS streaming' if a.scheduler=='fused' else 'all 18 convolution MACs plus bias, float32 scaling and nearest-even INT8 requantization, AXIS streaming' if b.pl_quantization and a.scheduler!='original' else 'all 18 convolution MACs, INT8 x INT8 -> INT32, AXIS streaming'),
        'ps_operators':('input preprocessing, remaining activation LUTs/ReLU, pooling, resize, concat, scheduling, airway postprocessing' if a.scheduler=='fused' else 'input preprocessing, activation LUTs, ReLU, pooling, resize, concat, layer scheduling, airway postprocessing' if b.pl_quantization and a.scheduler!='original' else 'input preprocessing, quantization/scaling/bias, ReLU, pooling, resize, concat, layer scheduling, airway postprocessing'),
        'pl_requantization':b.pl_quantization and a.scheduler!='original',
        'pointwise_streaming':b.pointwise_streaming,'spatial_streaming':b.spatial_streaming,
        'pl_activation_lut':b.pl_activation_lut,'fused_activation_layers':getattr(graph,'fused_layers',[]),
        'slice_workers':a.slice_workers,
        'ps_pool_quantize_fusions':len(getattr(graph,'fused_pools',[])),
        'direct_int8_mask_requested':graph.return_quantized,
        'clean_bo_sync_elision':os.environ.get('CT_PL_CLEAN_BO','0')=='1',
        'wait_mode':os.environ.get('CT_PL_WAIT_MODE','sleep'),'poll_microseconds':int(os.environ.get('CT_PL_POLL_US','10' if os.environ.get('CT_PL_WAIT_MODE')=='adaptive' else '50')),
        'repeat_process_cpu_seconds':cpu_times,
        'repeat_skipped_sync':skipped_sync,'skipped_sync_fields':['input_calls','input_bytes','output_prepare_calls','output_prepare_bytes'],
        'repeats':a.repeats,'setup_seconds':setup_seconds,'warmup_slice_seconds':warm,'repeat_inference_seconds':times,'repeat_pl_wait_seconds':hardware,
        'ps_scheduler':a.scheduler,'output_pool_bytes':pooled_bytes,'buffer_mode':os.environ.get('CT_PL_BO_MODE','cacheable'),'repeat_raw_mask_sha256':repeat_hashes,'loaded_bit_bin_sha256':Path('/run/kv260-ct-loaded.sha256').read_text().strip(),
        'median_inference_seconds':float(np.median(times)),'postprocess_seconds':post,'median_inference_and_postprocess_seconds':float(np.median(times))+post,
        'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'pl_conv_calls':calls,
        'worker_total_seconds':time.perf_counter()-started,
        'worker_stages':phases,
        'worker_total_note':'All requested repeats, CT loading, setup, warmup, postprocessing, mask I/O, reference comparison and preview generation; excludes process launch, final JSON write and Notebook rendering.',
        'agreement_with_pc':comparisons,'airway_refinement':refinement,'generalization_validated':False,
        'airway_logits':logits_metadata,
        'timing_note':'Inference includes input preparation (including prefetch startup/drain), PS graph and BO synchronization. median_inference_and_postprocess_seconds excludes file I/O; worker_total_seconds includes all repeats and file I/O as described in worker_total_note. PL wait includes polling; not pure MAC cycles.'}
    write_json(a.output/'report.json',report);write_json(a.output/'status.json',{'status':'completed','backend':report['backend']});print(json.dumps(report,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['smoke','start','status','_worker']);p.add_argument('--output',type=Path,default=ROOT/'outputs/ct_pl_benchmark_20260928');p.add_argument('--input',type=Path,default=ROOT/'data/CT-chest.nrrd');p.add_argument('--model-dir',type=Path,default=ROOT/'ct_pl/model');p.add_argument('--repeats',type=int,default=3);p.add_argument('--scheduler',choices=['original','int8','native','stream','mapped','fused'],default='original');p.add_argument('--slice-workers',type=int,choices=[1,2],default=1);p.add_argument('--save-airway-logits',action='store_true');a=p.parse_args();a.output=a.output.resolve();a.model_dir=a.model_dir.resolve()
    if a.repeats<1:raise ValueError('repeats must be positive')
    if a.slice_workers==2 and a.scheduler not in ['mapped','fused']:raise ValueError('Two slices require mapped or fused scheduling')
    if a.action=='smoke':smoke(ROOT/'ct_pl/package/board_layer_validation.json',a.model_dir);return
    if a.action=='status':print((a.output/'status.json').read_text());return
    if a.action=='start':
        a.output.mkdir(parents=True,exist_ok=False);write_json(a.output/'status.json',{'status':'starting','backend':'pl'})
        with (a.output/'run.log').open('w') as log:
            command=[sys.executable,str(Path(__file__).resolve()),'_worker','--output',str(a.output),'--input',str(a.input.resolve()),'--model-dir',str(a.model_dir),'--repeats',str(a.repeats),'--scheduler',a.scheduler,'--slice-workers',str(a.slice_workers)]
            if a.save_airway_logits:command.append('--save-airway-logits')
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write_json(a.output/'launch.json',{'pid':proc.pid});print('Started',proc.pid);return
    try:worker(a)
    except Exception as exc:
        write_json(a.output/'status.json',{'status':'failed','error':str(exc),'traceback':traceback.format_exc()});raise

if __name__=='__main__':main()
