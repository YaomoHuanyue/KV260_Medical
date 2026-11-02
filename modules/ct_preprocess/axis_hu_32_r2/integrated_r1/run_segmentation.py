"""CT DFX entry: unchanged frozen model, fused PS graph, two-pixel PL spatial conv."""
from pathlib import Path
import argparse,json,os,sys,time
SYSTEM=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(SYSTEM),str(SYSTEM/'dfx/medical')]
from runtime_extended import ROOT,SYSTEM,Session,ct_backend
sys.path.insert(0,str(SYSTEM/'modules/segmentation'))
from ct_pl.run import *
from runtime_extended import ROOT,SYSTEM
backend=ct_backend
def worker(a,prepared):
    os.environ['CT_PL_STATUS_PATH']=str(a.output/'status.json')
    started=prepared['started'];original=prepared['original'];phases=prepared['phases']
    plan=json.loads((a.model_dir/'graph.json').read_text());physical='preprocessing' in plan
    image=prepared['image'];ct=prepared['ct']
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
        from modules.ct_preprocess.axis_hu_32_r2.integrated_r1.pl_context import PLContextPreparer
        prepare=PLContextPreparer(graph,prepared['quantized'],prepared['metadata'],spacing_z)
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
                write_json(a.output/'status.json',{'status':'running','backend':'dfx_pl_HU_and_int8_convolution_ps_graph','repeat':repeat+1,'repeats':a.repeats,'slice':z+1,'slices':len(ct),'elapsed_seconds':time.perf_counter()-started,'inference_elapsed_seconds':sum(times)+time.perf_counter()-tick,'stage':'inference','pid':os.getpid()})
            times.append(time.perf_counter()-tick);hardware.append(b.hardware_seconds-hw_begin);cpu_times.append(time.process_time()-cpu_begin)
            skipped_sync.append([b.lib.ct_skipped_sync(b.handle,i)-sync_before[i] for i in range(4)] if hasattr(b.lib,'ct_skipped_sync') else [0]*4)
            hashes={n:hashlib.sha256(m).hexdigest() for n,m in masks.items()}
            if repeat_hashes and hashes!=repeat_hashes[0]:raise ValueError('Full-volume outputs changed between benchmark repeats')
            repeat_hashes.append(hashes)
        calls=b.calls
        pooled_bytes=b.lib.ct_output_pool_bytes(b.handle) if b.output_pool else 0
    finally:b.close()
    write_json(a.output/'status.json',{'status':'running','stage':'postprocess','repeat':a.repeats,'repeats':a.repeats,'slice':len(ct),'slices':len(ct),'elapsed_seconds':time.perf_counter()-started,'pid':os.getpid()})
    raw_airway=masks['airway']
    tick=time.perf_counter();write_like(raw_airway,image,a.output/'airway_mask_network.nii.gz')
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
    report={'status':'completed','backend':'dfx_pl_HU_and_int8_convolution_ps_graph','input_sha256':input_hash,'device_requested':'pl',
        'model_status':'experimental_multicase_partial_labels' if physical else 'experimental_single_case_distillation','model_sha256':plan['source_sha256'],'physical_context':physical,'pl_inference_implemented':True,'all_operators_on_pl':False,
        'pl_operators':('all 18 convolutions with INT8 requantization; fused ReLU and exact activation LUT on 8 single-consumer chains, AXIS streaming' if a.scheduler=='fused' else 'all 18 convolution MACs plus bias, float32 scaling and nearest-even INT8 requantization, AXIS streaming' if b.pl_quantization and a.scheduler!='original' else 'all 18 convolution MACs, INT8 x INT8 -> INT32, AXIS streaming'),
        'ps_operators':('geometry conversion and five-plane context packing, remaining activation LUTs/ReLU, pooling, resize, concat, scheduling, airway postprocessing' if a.scheduler=='fused' else 'geometry conversion and five-plane context packing, activation LUTs, ReLU, pooling, resize, concat, layer scheduling, airway postprocessing' if b.pl_quantization and a.scheduler!='original' else 'geometry conversion and five-plane context packing, quantization/scaling/bias, ReLU, pooling, resize, concat, layer scheduling, airway postprocessing'),
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
        'ps_scheduler':a.scheduler,'output_pool_bytes':pooled_bytes,'buffer_mode':os.environ.get('CT_PL_BO_MODE','cacheable'),'repeat_raw_mask_sha256':repeat_hashes,'loaded_bit_bin_sha256':Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip(),
        'median_inference_seconds':float(np.median(times)),'postprocess_seconds':post,'median_inference_and_postprocess_seconds':float(np.median(times))+post,
        'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'pl_conv_calls':calls,
        'worker_total_seconds':time.perf_counter()-started,
        'worker_stages':phases,
        'worker_total_note':'All requested repeats, CT loading, setup, warmup, postprocessing, mask I/O, reference comparison and preview generation; excludes process launch, final JSON write and Notebook rendering.',
        'agreement_with_pc':comparisons,'airway_refinement':refinement,'generalization_validated':False,
        'airway_logits':logits_metadata,
        'timing_note':'Inference includes input preparation (including prefetch startup/drain), PS graph and BO synchronization. median_inference_and_postprocess_seconds excludes file I/O; worker_total_seconds includes all repeats and file I/O as described in worker_total_note. PL wait includes polling; not pure MAC cycles.'}
    if logits_metadata is not None and same_grid:
        # Raw/clean masks, CT and recorded logits are already validated in this
        # process. Reuse their actual inference snapshot, without rereading CT.
        sys.path.insert(0,str(SYSTEM/'ui'))
        from features.airway_audit import audit_arrays,publish_audit
        tick=time.perf_counter()
        candidate,detail=audit_arrays(raw_airway>0,masks['airway']>0,ct,
            np.load(a.output/logits_metadata['file'],mmap_mode='r',allow_pickle=False),logits_metadata,image)
        publish_audit(candidate,detail,image,a.output,a.output,logits_metadata)
        phases['airway_detail_audit_seconds']=time.perf_counter()-tick
        report['airway_detail']={k:detail[k] for k in ('status','policy','retained_components','added_voxels','mask_file','mask_sha256','default_mask_replaced','computation')}
        report['ps_operators']+=', sparse discarded-airway candidate audit (same-input PL comparison favors PS)'
        del candidate,raw_airway
    elif logits_metadata is not None:
        report['airway_detail']={'status':'not_run_geometry_mismatch','reason':'Recorded logits and raw mask use the network grid; explicit evidence-preserving resampling is required.'}
    report['worker_total_seconds']=time.perf_counter()-started
    report['process_peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    report['worker_total_note']+=' Includes candidate audit when its geometry is supported.'
    report['PL_HU_preprocessing']=prepared['metrics']
    report['pl_operators']='HU clipping, normalization and exact model INT8 quantization over AXIS; '+report['pl_operators']
    report['timing_note']+=' D6 preprocessing/open/switch/drain is performed once before C5 setup, included in setup_seconds and worker_total_seconds, and reported in PL_HU_preprocessing; measured inference repeats reuse that volume.'
    report['PL_HU_entry_candidate']=True
    write_json(a.output/'report.json',report);write_json(a.output/'status.json',{'status':'completed','backend':report['backend']});print(json.dumps(report,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=1);p.add_argument('--reference-dir',type=Path);a=p.parse_args()
    if a.repeats<1:raise ValueError('Positive repeats required')
    a.input=a.input.resolve();a.output=a.output.resolve()
    if a.reference_dir:a.reference_dir=a.reference_dir.resolve()
    a.output.mkdir(parents=True,exist_ok=False)
    a.model_dir=SYSTEM/'modules/segmentation/outputs/ct_accuracy_v2/pl_model'
    a.scheduler='fused';a.slice_workers=2;a.save_airway_logits=True;a.no_preview=True
    os.environ.setdefault('CT_PL_WAIT_MODE','adaptive');os.environ.setdefault('CT_PL_CLEAN_BO','1')
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1.prepare import prepare_ct
    try:
        # D6 session is completely drained and closed before the C5 session can
        # acquire the shared PL lock. No intermediate restoration bit is loaded.
        prepared=prepare_ct(a)
        with Session() as session:
            worker(a,prepared);session.report(a.output/'dfx_session.json')
    except BaseException as error:
        write_json(a.output/'status.json',{'status':'failed','error':str(error),'pid':os.getpid()})
        raise
if __name__=='__main__':main()
