def _run_locked(input_path, mode, source, lesion, diameter, margin, stop_file, minimum_bend):
    input_path=Path(input_path).resolve(); digest=sha(input_path)
    source = Path(source).resolve() if source else None
    if mode != 'all':
        if source is None: raise ValueError('请先选择属于该 CT 的已完成结果')
        validate_result(source, digest)
    partial = None
    if source and mode != 'all':
        from modules.image_import.partial_r1.contracts import validate_source, require_navigation
        partial = validate_source(input_path, source)
        if partial and mode in ('navigation', 'comparison'):
            require_navigation(input_path, source)
    CANDIDATE_RUNS.mkdir(parents=True,exist_ok=True)
    output = CANDIDATE_RUNS/(time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    output.mkdir()
    emit('started', output=str(output), text='准备 DFX 任务')
    if source:
        # Each result is self-contained, so deleting an older run cannot break it.
        for name in ('segmentation', 'reconstruction', 'airway_detail'):
            if name == 'airway_detail' and mode == 'airway-detail': continue
            if (source/name).exists() and not (mode=='reconstruction' and name=='reconstruction'):
                (output/name).mkdir()
                for file in (source/name).iterdir():
                    if file.is_file(): shutil.copy2(file, output/name/file.name)
    stages = ['segmentation', 'reconstruction', 'navigation'] if mode=='all' else ['navigation' if mode=='comparison' else mode]
    command = {
        'segmentation': [str(ROOT/'modules/segmentation/streaming_stage_r1/entry.py'),'--input',str(input_path),'--output',str(output/'segmentation'),'--job-lock-fd',str(_candidate_job_fd)],
        'reconstruction': [str(ROOT/'modules/reconstruction/streaming_functional_r1/run_reconstruction.py'),'--ct',str(input_path),'--mask-dir',str(output/'segmentation'),'--output',str(output/'reconstruction')],
        'navigation': [str(Path(__file__).parent/'navigation_task_r6.py'),'--airway',str(output/'segmentation/airway_mask.nii.gz'),
            '--lesion',str(output/'segmentation/nodule_mask.nii.gz'),'--lesion-index',str(lesion),
            '--scope-diameter-mm',str(diameter),'--safety-margin-mm',str(margin),'--minimum-bend-radius-mm',str(minimum_bend),'--output',str(output/'navigation')]+(['--compare'] if mode=='comparison' else []),
        'airway-detail': [str(ROOT/'modules/airway_detail/run_recovery.py'),'--input',str(input_path),
            '--segmentation',str(output/'segmentation'),'--lesion-index',str(lesion),'--output',str(output/'airway_detail')]
    }
    if partial:
        command['reconstruction'] = [str(ROOT/'modules/reconstruction/streaming_functional_r2/run_partial.py'),
            '--ct',str(input_path),'--mask-dir',str(output/'segmentation'),'--output',str(output/'reconstruction')]
    if mode in ('reconstruction', 'airway-detail') and source and (source/'navigation').exists():
        (output/'navigation').mkdir()
        for file in (source/'navigation').iterdir():
            if file.is_file(): shutil.copy2(file, output/'navigation'/file.name)
    phases=[]; start=time.monotonic()
    report=dict(schema='kv260.ui.pipeline.v1',status='running',backend='PS_ROI_sparse' if mode=='airway-detail' else 'dfx_pl',input_sha256=digest,
                input=str(input_path),mode=mode,source_result=str(source) if source else None,stages=phases,
                functional_streaming_candidate=True,performance_qualification_pending=True,all_operators_on_PL=False)
    if partial:
        report.update(available_structures=partial['declared_structures'], unavailable_structures=partial['unavailable_structures'],
            external_segmentation_report_sha256=sha(output/'segmentation/report.json'))
    write(output/'pipeline.json', report)
    try:
        for i, stage in enumerate(stages):
            if stop_file and Path(stop_file).exists():
                report['status']='stopped'; break
            emit('stage', stage=stage, index=i, count=len(stages), text='执行 '+stage)
            t=time.monotonic()
            original_logs=_snapshot_candidate_logs()
            with (output/(stage+'.log')).open('w') as log:
                argv=[sys.executable,str(MEDICAL/command[stage][0]),*command[stage][1:]]
                child=subprocess.Popen(argv,cwd=MEDICAL,stdout=log,stderr=subprocess.STDOUT,pass_fds=(_candidate_job_fd,))
                ticks=int(Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19])
                write(output/(stage+'_process.json'),dict(PID=child.pid,start_ticks=ticks,argv=argv))
                rc=child.wait()
            _retain_candidate_stage_logs(output,stage,child.pid,original_logs)
            if rc:
                tail=(output/(stage+'.log')).read_text(errors='replace')[-5000:]
                raise RuntimeError(stage+' 失败：\n'+tail)
            phases.append(dict(stage=stage,wall_seconds=time.monotonic()-t))
            emit('stage_done',stage=stage,seconds=phases[-1]['wall_seconds'])
        else:
            report['status']='passed'
    except BaseException as e:
        report.update(status='failed',error=str(e)); raise
    finally:
        report['total_wall_seconds']=time.monotonic()-start
        write(output/'pipeline.json',report)
    emit('completed',output=str(output),status=report['status'],seconds=report['total_wall_seconds'])
