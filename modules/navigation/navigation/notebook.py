"""One-cell Notebook entry with background workers and cached extraction."""
import asyncio
import html
import json
from pathlib import Path
import sys
import numpy as np
from .viewer import viewer_html


class NavigationPanel:
    def __init__(self, root):
        import ipywidgets as w
        self.root=Path(root).resolve();self.output=self.root/"outputs"/"own_ct"
        self.task=None;self.process=None;self._scene=None;self._scene_key=None;self._route_session=None;self._route_planner=None;self._target_cache={}
        from pl.runtime import available
        self.backend=w.Dropdown(description='距离场计算',options=[('PS / SciPy','ps'),('PL / AXIS','pl')],value='pl' if available() else 'ps')
        from pl.route_runtime import available as route_available
        self.planner_backend=w.Dropdown(description='路径与相机',options=[('PS','ps'),('PL / AXIS','pl')],value='pl' if route_available() else 'ps')
        self.release_button=w.Button(description='释放 PL 会话')
        self.release_button.on_click(lambda _:self.release_pl())
        self.airway=w.Text(value=str(self.root/"data"/"own_ct"/"airway_mask.nii.gz"),description="气道 Mask",layout=w.Layout(width="95%"))
        self.lesion=w.Text(value=str(self.root/"data"/"own_ct"/"nodule_mask.nii.gz"),description="病灶候选",layout=w.Layout(width="95%"))
        self.root_point=w.Text(placeholder="自动；或输入 LPS x,y,z（mm）",description="气管入口",layout=w.Layout(width="500px"))
        self.build=w.Button(description="提取中心线 / 分支树",button_style="primary")
        self.target=w.Dropdown(description="导航目标",options=[("病灶候选","lesion")],layout=w.Layout(width="500px"))
        self.lesion_index=w.BoundedIntText(value=0,min=0,max=9999,description="候选编号")
        self.point=w.Text(placeholder="LPS x,y,z（mm）",description="目标坐标")
        self.scope=w.BoundedFloatText(value=1.,min=0,max=20,step=.1,description="镜体直径")
        self.margin=w.BoundedFloatText(value=.2,min=0,max=5,step=.1,description="余量 mm")
        self.plan_button=w.Button(description="规划 / 更新导航",button_style="success")
        self.status=w.HTML();self.viewer=w.HTML()
        self.widget=w.VBox([w.HTML("<b>独立支气管导航</b> · PL 可计算距离场、路径和平滑相机；PS 提取骨架与准备分岔标记。输入为分割 Mask，坐标为 LPS/mm。"),
            self.airway,self.lesion,w.HBox([self.backend,self.planner_backend,self.release_button]),w.HBox([self.root_point,self.build]),
            w.HBox([self.target,self.lesion_index]),self.point,
            w.HBox([self.scope,self.margin,self.plan_button]),self.status,self.viewer])
        self.build.on_click(lambda _:self.launch(self.extract))
        self.plan_button.on_click(lambda _:self.launch(self.plan))
        if (self.output/"centerline.json").exists():self.refresh()

    def launch(self, work):
        if self.task and not self.task.done():return
        try:loop=asyncio.get_running_loop()
        except RuntimeError:
            self.status.value="请在 Jupyter Notebook 的异步内核中运行界面；命令行请使用 run.py。";return
        self.task=loop.create_task(self.worker(work))

    async def worker(self, work):
        self.build.disabled=True;self.plan_button.disabled=True;self.backend.disabled=True;self.planner_backend.disabled=True;self.release_button.disabled=True
        self.status.value="后台计算中…"
        try:
            await work();self.refresh()
        except Exception as error:
            self.status.value='<span style="color:#b42318">'+html.escape(str(error))+'</span>'
        finally:
            self.build.disabled=False;self.plan_button.disabled=False;self.backend.disabled=False;self.planner_backend.disabled=False;self.release_button.disabled=False;self.process=None

    def release_pl(self):
        if self._route_session is not None:self._route_session.close()
        self._route_session=None;self._route_planner=None

    @staticmethod
    def coordinates(value):
        if not value.strip():return None
        result=[float(x) for x in value.replace(","," ").split()]
        if len(result)!=3 or not np.all(np.isfinite(result)):raise ValueError("坐标必须为三个有限数值：LPS x,y,z")
        return result

    async def command(self, arguments):
        self.process=await asyncio.create_subprocess_exec(sys.executable,str(self.root/"run.py"),*map(str,arguments),
            cwd=str(self.root),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        text,_=await self.process.communicate()
        if self.process.returncode:raise RuntimeError(text.decode(errors="replace"))

    async def extract(self):
        self.release_pl();self._scene=None;self._scene_key=None;self._target_cache.clear()
        args=["--airway",self.airway.value,"--output",self.output,'--backend',self.backend.value]
        root=self.coordinates(self.root_point.value)
        if root is not None:args += ["--root-lps",*root]
        await self.command(args)

    async def plan(self):
        if not (self.output/"centerline.json").exists():await self.extract()
        # Detect changed input/root before reusing a cached graph.
        from .geometry import sha256
        meta=json.loads((self.output/"centerline.json").read_text(encoding="utf-8"))
        expected='pl_edt_ps_skeleton_graph' if self.backend.value=='pl' else 'ps'
        manual_root=self.coordinates(self.root_point.value)
        changed=meta.get('backend')!=expected or await asyncio.to_thread(sha256,self.airway.value)!=meta['input_sha256']
        if manual_root is not None:
            if meta["root_mode"]!="manual_lps" or not np.allclose(meta.get("requested_root_lps_mm"),manual_root,rtol=0,atol=1e-5):
                changed=True
        elif meta["root_mode"]=="manual_lps":changed=True
        if changed:await self.extract()
        # Keep graph, target metadata and PL scene across clicks. No new worker,
        # XRT context or scene upload is needed for a repeated target.
        from .pipeline import load_prepared,choose_target,run_route
        cache_path=self.output/'centerline.npz';stat=cache_path.stat();key=(stat.st_mtime_ns,stat.st_size)
        if key!=self._scene_key:
            self.release_pl();self._scene=await asyncio.to_thread(load_prepared,self.output);self._scene_key=key;self._target_cache.clear()
        c=self._scene;kind=self.target.value;arguments={}
        if kind=='lesion':
            path=Path(self.lesion.value).resolve();s=path.stat();target_key=(str(path),s.st_mtime_ns,s.st_size,self.lesion_index.value)
            arguments=dict(lesion_path=path,lesion_index=self.lesion_index.value)
        elif kind=='point':
            point=self.coordinates(self.point.value)
            if point is None:raise ValueError('请输入目标 LPS 坐标')
            target_key=('point',*point);arguments=dict(target_lps_mm=point)
        else:target_key=(kind,);arguments=dict(endpoint_id=int(kind.split(':')[1]))
        if target_key not in self._target_cache:self._target_cache[target_key]=await asyncio.to_thread(choose_target,c,**arguments)
        target=self._target_cache[target_key]
        if self.planner_backend.value=='pl' and self._route_planner is None:
            from pl.route_runtime import RouteXRT,RoutePlanner
            def open_scene():
                session=RouteXRT()
                try:return session,RoutePlanner(c,session)
                except Exception:session.close();raise
            self._route_session,self._route_planner=await asyncio.to_thread(open_scene)
        elif self.planner_backend.value=='ps':self.release_pl()
        await asyncio.to_thread(run_route,c,target,self.output,planner=self._route_planner,
                               scope_diameter_mm=self.scope.value,safety_margin_mm=self.margin.value)

    def refresh(self):
        meta=json.loads((self.output/"centerline.json").read_text(encoding="utf-8"))
        tree=json.loads((self.output/"branches.json").read_text(encoding="utf-8"))
        selected=self.target.value
        choices=[("病灶候选（从 0 编号，按体积排序）","lesion"),("手动 LPS 坐标","point")]
        choices += [(f"末端 {n['id']} · {'入口连通' if n['root_connected'] else '断裂分支'}",f"endpoint:{n['id']}")
            for n in tree["nodes"] if n["degree"]<=1 and n["id"]!=meta["root"]]
        self.target.options=choices
        if selected in [x[1] for x in choices]:self.target.value=selected
        self.viewer.value=viewer_html(self.output)
        route_path=self.output/"route.json";detail=""
        if route_path.exists():
            report=json.loads(route_path.read_text(encoding="utf-8"))
            if report.get("centerline_id")==meta["centerline_id"]:
                planner='PL 路径与相机' if report.get('backend')=='pl_route' else 'PS 路径与相机'
                seconds=report['timing'].get('plan_and_camera_seconds',report['timing']['plan_seconds'])
                detail=f" · {planner} · 路径状态：{report['status']} · 长度 {report['length_mm']:.1f} mm · 规划 {seconds:.3f} 秒"
        backend='PL 距离场 + PS 骨架' if meta.get('backend')=='pl_edt_ps_skeleton_graph' else 'PS'
        self.status.value=f"{backend} · 中心线 {meta['skeleton_points']} 点 · 分支 {len(tree['branches'])} 条 · 连通域 {meta['component_count']}"+detail+"<br>自动入口和分支拓扑需要核对。管径为基于体素的估计；不可达时只显示可达段。"
