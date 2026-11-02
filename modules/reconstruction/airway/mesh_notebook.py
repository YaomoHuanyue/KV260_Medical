"""Background reconstruction and offline WebGL output inside the one Notebook."""
import asyncio
import base64
import gzip
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor

def _encode_mesh_buffer(data):
    return base64.b64encode(gzip.compress(data,compresslevel=1,mtime=0)).decode()


def viewer_html(folder, height=650):
    folder = Path(folder)
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if report.get('backend')!='pl':
        raise ValueError('PS Marching Cubes 已移除；此前 PS 网格仅保留为历史参考，不作为当前 PL 结果显示。')
    payload = []
    # Independent gzip streams release the GIL. Bound concurrency to three
    # cores and retain the identical payload ordering and byte representation.
    with ThreadPoolExecutor(max_workers=3) as workers:
        for name, item in report['layers'].items():
            with np.load(folder/item['mesh_file'], allow_pickle=False) as mesh:
                points, faces, normals = mesh['points'], mesh['faces'], mesh['normals']
                if not len(faces):
                    continue
                vertices = np.empty((len(points), 6), dtype='<f4')
                vertices[:, :3] = points
                vertices[:, 3:] = normals
                payload.append(dict(name=name, vertices=workers.submit(_encode_mesh_buffer,vertices.tobytes()),
                    indices=workers.submit(_encode_mesh_buffer,np.asarray(faces,dtype='<u4').tobytes()),
                    triangles=len(faces), bounds=item['bounds_mm']))
        for item in payload:
            item['vertices']=item['vertices'].result()
            item['indices']=item['indices'].result()
    if not payload:
        raise ValueError('当前 Mask 为空，没有可显示的三角形')
    source = (Path(__file__).with_name('mesh_viewer.js')).read_text(encoding='utf-8')
    label = '完整体素模型' if report['quality'] == 'full' else '肺部预览模型；气道／病灶保留完整采样'
    label += ' · '+('受约束表面平滑' if report.get('surface')=='smooth' else '原始表面')
    if report.get('airway')=='detail':label+=' · 近邻气道候选（未经人工验证）'
    content = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>*{box-sizing:border-box}body{margin:0;background:#111d2b;color:#e5effb;font:14px system-ui,"Microsoft YaHei",sans-serif}
main{display:flex;flex-direction:column;height:100vh}header{padding:12px 16px;border-bottom:1px solid #35475b}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:7px 0}button,select{background:#234057;color:#fff;border:1px solid #69859b;border-radius:5px;padding:5px 10px}
label{white-space:nowrap}input[type=range]{width:100px;vertical-align:middle}#stage{position:relative;flex:1;min-height:250px}
canvas{display:block;width:100%;height:100%;touch-action:none}#status{position:absolute;top:12px;left:16px;color:#b5cce0;pointer-events:none;background:#111d2bcc;padding:5px;border-radius:4px}
footer{padding:8px 16px;color:#b5cce0;font-size:12px}#error{white-space:pre-wrap;color:#ffaba4;padding:15px;display:none}</style>
<main><header><b>肺／气道／病灶候选 · 交互三维模型</b><div id="caption"></div>
<div class="row"><label><input id="lung" type="checkbox" checked>肺</label><label>肺透明度 <input id="opacity" type="range" min="0" max="1" step="0.05" value="0.20"></label>
<label><input id="airway" type="checkbox" checked>气道</label><label><input id="nodule" type="checkbox" checked>病灶候选</label>
<label>显示 <select id="display-quality"><option value="auto">拖动预览／静止高清</option><option value="high" selected>始终高清</option><option value="low">始终预览</option></select></label></div>
<div class="row"><button id="front">正面</button><button id="side">侧面</button><button id="top">顶部</button><button id="reset">重置</button>
<label>裁剪 <select id="clip-axis"><option value="none">关闭</option><option value="0">X</option><option value="1">Y</option><option value="2">Z</option></select><input id="clip" type="range" min="0" max="1" step="0.01" value="1"></label>
<button id="benchmark">测试交互速度（3 秒）</button></div></header>
<div id="stage"><canvas id="view" aria-label="可旋转缩放裁剪的三维模型"></canvas><div id="status">上传网格…</div><div id="error"></div></div>
<footer>拖动旋转 · Shift＋拖动平移 · 滚轮缩放 · 旋转不重新建模 · 裁剪面不封口。显示由当前浏览器 GPU 执行。</footer></main><script>const meshPayload=__PAYLOAD__;const meshCaption=__CAPTION__;
__SCRIPT__</script></html>'''
    content = content.replace('__PAYLOAD__', json.dumps(payload, separators=(',', ':')))
    content = content.replace('__CAPTION__', json.dumps(label+' · 建模后端 '+report['backend'].upper(), ensure_ascii=True))
    content = content.replace('__SCRIPT__', source)
    return '<iframe title="医学影像交互三维模型" sandbox="allow-scripts" style="width:100%;height:'+str(int(height))+'px;border:0" srcdoc="'+html.escape(content, quote=True)+'"></iframe>'


class MeshPanel:
    def __init__(self, root, input_panel):
        import ipywidgets as w
        self.root = Path(root)
        self.input_panel = input_panel
        self.task = None
        self.process = None
        self.quality = w.Dropdown(options=[('完整：原始体素', 'full'),
            ('预览：肺部粗采样，保留细气道／病灶', 'preview')], description='建模精度', layout=w.Layout(width='500px'))
        self.start = w.Button(description='生成／打开三维模型', button_style='primary')
        self.surface=w.Dropdown(options=[('原始表面（对照）','raw'),('受约束平滑（保护细气道）','smooth')],value='smooth',description='表面',layout=w.Layout(width='380px'))
        self.airway=w.Dropdown(options=[('原始分割结果','baseline'),('保留可信近邻候选（实验）','detail')],description='气道',layout=w.Layout(width='380px'))
        from fpga.smooth_xrt_backend import available as smoothing_available
        pl_smoothing=smoothing_available(self.root)
        validation=self.root/'docs/pl_smooth/board_validation.json'
        pl_verified=False
        if pl_smoothing and validation.is_file():
            verified=json.loads(validation.read_text())
            loaded=Path('/run/kv260-mc-loaded.sha256')
            pl_verified=(verified.get('status')=='passed' and verified.get('performance_accepted') is True
                and loaded.is_file() and verified.get('loaded_bit_sha256')==loaded.read_text().strip())
            fingerprints=verified.get('runtime_source_sha256',{})
            pl_verified=pl_verified and bool(fingerprints) and all(
                (self.root/name).is_file() and hashlib.sha256((self.root/name).read_bytes()).hexdigest()==expected
                for name,expected in fingerprints.items())
        self.smoothing_backend=w.Dropdown(options=[('PS 平滑（对照）','ps')]+([('PL 平滑','pl')] if pl_smoothing else []),
            value='pl' if pl_verified else 'ps',description='平滑执行',layout=w.Layout(width='380px'))
        self.status = w.HTML('使用本重建工程内选中的 Mask。网格常驻浏览器，旋转、缩放和裁剪无需重新出图。')
        from .mesh_reconstruction import available_backend
        if available_backend(self.root)!='pl':
            self.status.value='PS Marching Cubes 已移除。请先手动加载本工程的 PL 重建位流。'
        # Explicit HTML widget state survives asynchronous comm callbacks;
        # do not route detached-task display through an Output capture context.
        self.output = w.HTML(layout=w.Layout(width='100%'))
        self.box = w.VBox([w.HBox([self.quality, self.start]),w.HBox([self.surface,self.airway]),self.smoothing_backend, self.status, self.output])
        self.start.on_click(self.launch)

    def launch(self, _):
        from .mesh_reconstruction import available_backend
        if available_backend(self.root)!='pl':
            self.output.value=''
            self.status.value='当前位流不含 PL Marching Cubes；PS 回退已移除，程序不会切换位流。'
            return
        if self.process and self.process.poll() is None:
            self.status.value = '已有建模任务运行，请等待完成。'
            return
        if not self.input_panel.results.value:
            self.status.value = '请先完成分割并选择结果。'
            return
        directory = self.root/'outputs/reconstruction/jobs'/str(time.time_ns())
        directory.mkdir(parents=True)
        self.state = directory/'status.json'
        with (directory/'run.log').open('w') as log:
            self.process = subprocess.Popen([sys.executable, '-m', 'airway.mesh_reconstruction',
                '--result', self.input_panel.results.value, '--quality', self.quality.value,
                '--surface',self.surface.value,'--airway',self.airway.value,
                '--smoothing-backend',self.smoothing_backend.value,
                '--status', str(self.state)], cwd=self.root, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
        self.start.disabled = True
        self.status.value = '后台生成网格；完成后只传输一次，交互在浏览器内刷新。'
        self.task = asyncio.create_task(self.poll())

    async def poll(self):
        try:
            await self._poll()
        except Exception as error:
            self.status.value = '结果显示失败：'+html.escape(str(error))
        finally:
            self.start.disabled = False

    async def show_result(self, state):
        report = state['report']
        triangles = sum(v['triangles'] for v in report['layers'].values())
        description=('受约束平滑' if report.get('surface')=='smooth' else '原始表面')
        if report.get('surface')=='smooth':description+='（'+report.get('smoothing_backend','ps').upper()+'）'
        if report.get('airway_candidates'):
            description+=f"；保留 {report['airway_candidates']['retained_components']} 个近邻片段（候选，尚未人工验证）"
        self.status.value = (f"建模后端：<b>{report['backend'].upper()}</b>；{triangles:,} 个三角形；"
            + ('已复用网格缓存' if state['cached'] else f"生成耗时 {report['build_seconds']:.2f} 秒")
            + '。正在准备显示数据…')
        frame = await asyncio.to_thread(viewer_html, state['output'])
        self.output.value = frame
        self.status.value = (f"建模后端：<b>{report['backend'].upper()}</b>；{triangles:,} 个三角形；"
            + ('已复用网格缓存' if state['cached'] else f"生成耗时 {report['build_seconds']:.2f} 秒")
            + f'；{description}。显示后端：当前电脑浏览器 WebGL；未切换板卡固件。')

    async def _poll(self):
        while True:
            try:
                state = json.loads(self.state.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                if self.process.poll() is not None:
                    self.start.disabled = False
                    self.status.value = '建模进程退出，请检查 '+html.escape(str(self.state.parent/'run.log'))
                    return
                await asyncio.sleep(.3)
                continue
            if state['status'] in ('completed', 'failed'):
                if state['status'] == 'failed':
                    self.status.value = '建模失败：'+html.escape(state['error'])
                    return
                await self.show_result(state)
                return
            await asyncio.sleep(.3)

    def close(self):
        if self.task:
            self.task.cancel()
        # Detached workers may own DMA allocations; closing UI never kills them.
        self.box.close()
