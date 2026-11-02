"""One CT-only notebook panel. Work runs in detached processes; no mesh dependency."""
import asyncio
from datetime import datetime
import html,json
from pathlib import Path
import subprocess,sys


def progress_text(r):
    state=r.get('status')
    if state=='completed':return '已完成'
    if state=='starting':return '正在读取 CT、加载模型并预热'
    slices=r.get('slices',139);repeat=r.get('repeat',1);repeats=r.get('repeats',1)
    current=r.get('slice',0);done=(repeat-1)*slices+current;total=repeats*slices
    text=f"第 {repeat}/{repeats} 遍 | 切片 {current}/{slices}"
    elapsed=r.get('elapsed_seconds')
    if elapsed is not None:text+=f" | 已用 {elapsed:.0f} 秒"
    if state=='running' and (r.get('stage')=='postprocess' or done>=total):
        return text+' | 推理已完成，正在后处理、保存和核对结果'
    inference=r.get('inference_elapsed_seconds')
    if state=='running' and inference is not None and done>=8 and done<total:
        text+=f" | 预计剩余推理 {inference*(total-done)/done:.0f} 秒（不含后处理与保存）"
    return text


class CTPanel:
    def __init__(self,root):
        import ipywidgets as w
        self.root=Path(root);self.task=None;self.run_dir=None;self.viewer=None
        self.model_dir=self.root/'outputs/ct_accuracy_v2'
        self.variant=w.Dropdown(options=[('当前实验模型：15.7 万参数','accuracy_v2')],description='模型',layout=w.Layout(width='380px'))
        options=[('PS INT8','int8'),('PS FP32','fp32')]
        self.backend=w.Dropdown(options=options,description='执行方式')
        self.variant.observe(self.refresh_backends,names='value');self.refresh_backends()
        if 'pl' in [value for _,value in self.backend.options]:self.backend.value='pl'
        self.repeats=w.BoundedIntText(value=1,min=1,max=5,description='重复次数')
        self.start=w.Button(description='开始后台分割',button_style='primary');self.refresh=w.Button(description='刷新结果列表')
        self.results=w.Dropdown(description='已完成结果',layout=w.Layout(width='750px'))
        self.status=w.HTML('扩容版为实验候选：部分病例改善，细气道仍有遗漏；病灶尚无独立人工验证。执行方式列表按所选模型与当前位流的板端验证结果更新，可在下方检查二维叠加。')
        self.progress=w.IntProgress(min=0,max=139,description='切片')
        # Child widgets are published through widget state, not IOPub capture.
        # Nested Output display can lose widget views during comm callbacks.
        self.statistics=w.HTML()
        self.output=w.VBox()
        self.box=w.VBox([self.variant,w.HBox([self.backend,self.repeats,self.start]),self.status,self.progress,w.HBox([self.results,self.refresh]),self.output])
        self.start.on_click(self.launch);self.refresh.on_click(self.refresh_display)
        self.refresh_results()
        preferred=str(self.model_dir/'board_pl_host_overlap_single')
        if preferred not in [v for _,v in self.results.options]:preferred=str(self.model_dir/'board_ps/int8')
        candidates=[]
        try:
            model_sha=json.loads((self.model_dir/'pl_model/graph.json').read_text())['source_sha256']
            for _,value in self.results.options:
                directory=Path(value)
                report=json.loads((directory/'report.json').read_text())
                if report.get('model_sha256')==model_sha and report.get('airway_logits',{} ) and report['airway_logits'].get('status')=='completed' and (directory/'airway_logits.npy').is_file():
                    candidates.append((directory.stat().st_mtime,value))
            if candidates:preferred=max(candidates)[1]
        except (OSError,ValueError,KeyError):pass
        if preferred in [v for _,v in self.results.options]:self.results.value=preferred
        self.results.observe(self.show_result,names='value');self.show_result()
    def refresh_backends(self,*_):
        options=[('PS INT8','int8'),('PS FP32','fp32')]
        model=self.model_dir/'pl_model' if self.variant.value=='accuracy_v2' else self.root/'ct_pl/model'
        try:
            firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
            if firmware.read_bytes().rstrip(b'\0')!=b'ct_segmentation.bit.bin':
                raise ValueError('CT firmware is not loaded')
            check=json.loads((model/'board_layer_validation.json').read_text())
            plan=json.loads((model/'graph.json').read_text())
            loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
            if check.get('exact') and check.get('model_sha256')==plan['source_sha256'] and check.get('loaded_bit_bin_sha256')==loaded:
                label='PL 卷积/量化＋PS 层间算子' if check.get('pl_requantization') else 'PL 卷积＋PS 其余算子'
                options.append((label,'pl'))
        except (OSError,ValueError,KeyError):pass
        self.backend.options=options
    def refresh_results(self):
        self.refresh_backends()
        options=[]
        for p in (self.root/'outputs').glob('ct_*/**/report.json'):
            try:r=json.loads(p.read_text())
            except (ValueError,OSError):continue
            if r.get('status')=='completed' and r.get('backend') in ['ps_cpu_onnxruntime','pl_int8_convolution_ps_graph']:
                options.append((str(p.parent.relative_to(self.root/'outputs')),str(p.parent)))
        old=self.results.value;self.results.options=sorted(options,reverse=True)
        if old in [v for _,v in options]:self.results.value=old
    def refresh_display(self,_):
        self.refresh_results();self.show_result()
    def pl_settings(self):
        if self.variant.value!='accuracy_v2':return ('original',1)
        for folder in ['board_pl_host_overlap']:
            try:
                report=json.loads((self.model_dir/folder/'report.json').read_text())
                plan=json.loads((self.model_dir/'pl_model/graph.json').read_text())
                loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
                if report.get('status')=='completed' and report.get('ps_scheduler') in ['int8','native','stream','mapped','fused'] and report.get('model_sha256')==plan['source_sha256'] and report.get('loaded_bit_bin_sha256')==loaded and all(report['agreement_with_pc'][n]['dice']==1 for n in ['lung','airway','nodule']):
                    workers=report.get('slice_workers',1)
                    if workers not in [1,2]:continue
                    return (report['ps_scheduler'],workers)
            except (OSError,ValueError,KeyError):pass
        return ('original',1)
    def pl_scheduler(self):return self.pl_settings()[0]
    def show_result(self,change=None):
        from .ct_segmentation_view import show_segmentation
        if not self.results.value:return
        try:
            path=Path(self.results.value);r=json.loads((path/'report.json').read_text(encoding='utf-8'))
            statistics=f"网络与调度：<b>{r['median_inference_seconds']:.2f} 秒</b>；后处理：<b>{r['postprocess_seconds']:.2f} 秒</b>；进程峰值 RSS：<b>{r['process_peak_rss_bytes']/2**20:.1f} MiB</b>。计时不含文件读写。"
            if 'worker_total_seconds' in r:
                statistics+=f"<br>本次任务总时间（共 {r['repeats']} 遍）：<b>{r['worker_total_seconds']:.2f} 秒</b>，包含 CT 读取、预热、推理、后处理、保存和结果核对；不含进程启动与 Notebook 显示。"
            viewer=show_segmentation(self.root/'data/CT-chest.nrrd',path,display_panel=False)
            previous=self.viewer
            self.statistics.value=statistics
            self.viewer=viewer
            self.output.children=(self.statistics,viewer)
            if previous:previous.close()
        except Exception as error:
            self.status.value='结果显示失败：'+html.escape(str(error))
    def launch(self,_):
        # Refuse concurrent benchmark jobs to keep CPU timing meaningful.
        for state in (self.root/'outputs').glob('ct_*/**/status.json'):
            try:r=json.loads(state.read_text())
            except (OSError,ValueError):continue
            if r.get('status') in ['starting','running','hardware_blocked']:
                launch=state.parent/'launch.json'
                try:
                    import os
                    pid=r.get('pid') or json.loads(launch.read_text())['pid'];os.kill(pid,0)
                except (OSError,ValueError,KeyError):continue
                self.status.value='已有后台分割任务运行，请等待完成。';return
        out=self.root/'outputs'/('ct_run_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        mode=self.backend.value
        script=self.root/('ct_pl/run.py' if mode=='pl' else 'ct_ps_benchmark.py')
        cmd=[sys.executable,str(script),'start','--output',str(out),'--repeats',str(self.repeats.value)]
        if mode!='pl':
            cmd+=['--models',mode]
            if self.variant.value=='accuracy_v2':
                cmd+=['--model-dir',str(self.model_dir),'--physical-context',
                      '--reference-dir',str(self.model_dir/('evaluation_'+mode)/'own')]
        else:
            model=self.model_dir/'pl_model' if self.variant.value=='accuracy_v2' else self.root/'ct_pl/model'
            scheduler,workers=self.pl_settings()
            cmd+=['--model-dir',str(model),'--scheduler',scheduler,'--slice-workers',str(workers),'--save-airway-logits']
        result=subprocess.run(cmd,capture_output=True,text=True,cwd=self.root)
        if result.returncode:self.status.value=html.escape(result.stderr);return
        self.run_dir=out;self.start.disabled=True;self.task=asyncio.create_task(self.poll())
    async def poll(self):
        while True:
            try:r=json.loads((self.run_dir/'status.json').read_text())
            except (OSError,ValueError):await asyncio.sleep(2);continue
            state=r.get('status');self.status.value=html.escape(progress_text(r))
            if state=='hardware_blocked':
                self.status.value='PL 传输超时，已保留缓冲区。请勿结束进程，需复位板卡后继续。';return
            self.progress.max=r.get('slices',139);self.progress.value=r.get('slice',0)
            if state in ['completed','failed']:
                self.start.disabled=False
                if state=='failed':self.status.value='失败：'+html.escape(r.get('error','请查看 run.log'))
                else:
                    self.refresh_results()
                    target=self.run_dir if (self.run_dir/'report.json').exists() else next(self.run_dir.glob('*/report.json')).parent
                    self.results.value=str(target)
                return
            await asyncio.sleep(2)
    def show(self):
        from IPython.display import display
        display(self.box)
    def close(self):
        if self.task:self.task.cancel()
        if self.viewer:self.viewer.close()
        self.box.close()
