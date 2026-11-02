"""Self-contained Notebook viewer; no web server, CDN, VTK or mesh reconstruction."""
import base64
import gzip
import html
import json
from pathlib import Path
import numpy as np
from .pipeline import load_prepared
from .guidance import branch_guidance,guidance_route_id


def viewer_document(folder):
    folder=Path(folder);c=load_prepared(folder)
    report=json.loads((folder/"route.json").read_text(encoding="utf-8")) if (folder/"route.json").exists() else None
    if report and report.get("centerline_id") != c.metadata["centerline_id"]:
        report=None
    route={};camera={}
    if report:
        with np.load(folder/"route.npz",allow_pickle=False) as a:route={k:a[k].tolist() for k in a.files}
        with np.load(folder/"camera.npz",allow_pickle=False) as a:camera={k:a[k].tolist() for k in a.files}
    # R8 texture represents the original mask; this does not perform PS MC.
    guidance=report.get('branch_guidance',{}) if report else dict(events=[])
    if report and (guidance.get('schema')!='kv260.navigation.guidance.v3' or guidance.get('revision')!=1
                   or guidance.get('route_id')!=guidance_route_id(route)):
        guidance=branch_guidance(c,route)
    payload=dict(points=c.points_lps_mm.tolist(),edges=c.edges.tolist(),components=c.components.tolist(),root=c.root,
        guidance=guidance,
        radii=c.radii_mm.tolist(),route=route,camera=camera,report=report,
        geometry=c.geometry.to_dict(),offset=c.offset_zyx.tolist(),shape_xyz=list(c.mask.shape[::-1]),
        mask=base64.b64encode(gzip.compress(c.mask.astype(np.uint8).tobytes(),compresslevel=1,mtime=0)).decode())
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#132233;color:#e8f1fc;font:14px system-ui,"Microsoft YaHei"}
header{padding:10px 14px}button,select{background:#28465f;color:white;padding:5px 9px;border:1px solid #65819b;border-radius:4px}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:8px 0}.views{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px}
.pane{position:relative;height:470px;background:#0c1724;border:1px solid #3f566c}canvas{width:100%;height:100%;display:block;touch-action:none}
.label{position:absolute;top:8px;left:10px;background:#132233bb;padding:5px;pointer-events:none}#error{color:#ffb8aa;white-space:pre-wrap;padding:12px}
#guidance{position:absolute;inset:0;pointer-events:none}.branch-hint{margin-top:7px;padding:11px 12px;min-height:62px;background:#071810ef;border:2px solid #65819b;border-radius:5px;pointer-events:none;font-weight:750;font-size:16px;color:#d4e5f5}.branch-hint.active{color:#b1ffcb;border:3px solid #59ff91}
input[type=range]{min-width:180px;flex:1}footer{padding:10px 14px;color:#b7cbe1;font-size:12px}#state{font-variant-numeric:tabular-nums}
@media(max-width:760px){.views{grid-template-columns:1fr}.pane{height:290px}}
</style><header><b>支气管导航 · 独立模块</b><div id="summary"></div>
<div class="row"><button id="back">后退 1 mm</button><button id="play">播放</button><button id="next">前进 1 mm</button>
<button id="reset">回到入口</button><label>速度 <select id="speed"><option>5</option><option selected>10</option><option>20</option></select> mm/s</label>
<label>视野 <select id="fov"><option>45</option><option>65</option><option selected>90</option><option>110</option></select>°</label><label><input id="slow" type="checkbox" checked>分岔处减速</label><button id="align">对准路线</button><button id="fork">定位分岔</button></div>
<div class="row"><span>沿路径位置</span><input id="progress" type="range" min="0" max="1" value="0" step="0.1"><span id="state"></span></div>
</header><div class="views"><div class="pane"><canvas id="overview"></canvas><span class="label">分支树 / 路径 · 拖动旋转，滚轮缩放</span></div>
<div class="scope-column"><div class="pane"><canvas id="scope"></canvas><svg id="guidance" xmlns="http://www.w3.org/2000/svg" aria-label="目标分岔入口标记" style="width:100%;height:100%"></svg><span class="label">虚拟气镜 · 拖动转向，双击回正</span></div><div id="branchHint" class="branch-hint" role="status" aria-live="polite"></div></div></div><div id="error"></div>
<footer>右侧：绿色填充与金色轮廓突出实际可见的选中通道，单一短箭头指示当前方向；完整路线显示在左侧。密集分岔只突出当前一步，通过后更新。左侧：黄色规划路径、红色当前位置、紫色候选目标。当前为 Notebook 气镜预览，尚未接入 HDMI 或实际镜体定位。</footer>
<script>const navPayload=__PAYLOAD__;
__RENDERER__
__SCRIPT__</script></html>'''.replace("__PAYLOAD__",json.dumps(payload,ensure_ascii=True,separators=(",",":"))).replace(
        "__RENDERER__",Path(__file__).with_name("scope_renderer.js").read_text(encoding="utf-8")).replace(
        "__SCRIPT__",Path(__file__).with_name("viewer.js").read_text(encoding="utf-8"))


def viewer_html(folder,height=760):
    return '<iframe title="独立支气管导航" sandbox="allow-scripts" style="width:100%;height:'+str(int(height))+'px;border:0" srcdoc="'+html.escape(viewer_document(folder),quote=True)+'"></iframe>'
