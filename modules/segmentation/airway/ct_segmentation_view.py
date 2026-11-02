"""Inline axial CT review for the single project Notebook; no web server or mesh."""
from pathlib import Path
import io
import json


def show_segmentation(ct_path, result_dir, *, display_panel=True):
    import ipywidgets as widgets
    import numpy as np
    import SimpleITK as sitk
    from PIL import Image
    from IPython.display import display
    from .ct_segmentation import read_ct, require_geometry, sha256

    result_dir = Path(result_dir)
    report_path = result_dir / "report.json"
    if not report_path.exists():
        report_path = result_dir / "quantization_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "completed":
        raise ValueError("This segmentation run is not complete")
    ct_path = Path(ct_path)
    if ct_path.is_file() and report.get("input_sha256") != sha256(ct_path):
        raise ValueError("CT does not match the segmentation report")
    reference = read_ct(ct_path)
    ct = sitk.GetArrayFromImage(reference)
    masks = {}
    for name in ("lung", "airway", "nodule"):
        image = sitk.ReadImage(str(result_dir / f"{name}_mask.nii.gz"))
        require_geometry(image, reference)
        masks[name] = sitk.GetArrayFromImage(image) > 0
    raw_path=result_dir/'airway_mask_network.nii.gz'
    raw_airway=None
    if raw_path.exists():
        image=sitk.ReadImage(str(raw_path));require_geometry(image,reference)
        raw_airway=sitk.GetArrayFromImage(image)>0
    airway_options=[('原始后处理结果','baseline')]
    if raw_airway is not None:airway_options.append(('筛选前气道（可能有误检）','network'))
    detail_path=result_dir/'airway_mask_detail.nii.gz'
    detail_report_path=result_dir/'airway_detail_report.json'
    if detail_path.is_file() and detail_report_path.is_file():
        detail_report=json.loads(detail_report_path.read_text(encoding='utf-8'))
        if detail_report.get('status')=='completed':airway_options.append(('近邻候选：新增片段为紫色','detail'))
    airway_mode=widgets.Dropdown(options=airway_options,description='气道结果',layout=widgets.Layout(width='420px'))
    detail_airway=None
    slider = widgets.IntSlider(value=ct.shape[0]//2, min=0, max=ct.shape[0]-1,
                               description="轴位切片", continuous_update=False)
    checks = {name: widgets.Checkbox(value=True, description=label, indent=False)
              for name, label in (("lung", "肺（蓝）"), ("airway", "气道（黄）"), ("nodule", "结节候选（红）"))}
    opacity = widgets.FloatSlider(value=.4, min=0, max=.8, step=.05,
                                  description="叠加透明度", continuous_update=False)
    picture = widgets.Image(format="png", layout=widgets.Layout(width="640px", max_width="100%"))
    caption = widgets.HTML()
    colors = {"lung": (70, 180, 255), "airway": (255, 200, 20), "nodule": (255, 60, 70)}
    device_name = "CPU/GPU 混合" if report.get("device_requested") == "gpu" else "CPU"
    if report.get('backend') == 'pl_int8_convolution_ps_graph':
        result_label = 'KV260 实测：PL 卷积＋PS 其余算子及后处理'
    elif report.get('backend') == 'ps_cpu_onnxruntime':
        result_label = f"KV260 PS {report.get('model_precision', '').upper()} 实测结果"
    elif report_path.name == "quantization_report.json":
        result_label = "电脑 CPU INT8 小模型实验结果（含气道连通域后处理）"
    elif report.get("model_status") == "experimental_single_case_distillation":
        result_label = "电脑 GPU FP32 小模型实验结果（含 CPU 气道后处理）"
    else:
        result_label = f"电脑 {device_name} 教师模型参考结果"

    def update(*_):
        nonlocal detail_airway
        if airway_mode.value=='detail' and detail_airway is None:
            if detail_report['mask_sha256']!=sha256(detail_path) or detail_report['input_sha256']!=report['input_sha256'] or detail_report['model_sha256']!=report['model_sha256']:
                raise ValueError('Candidate mask does not match this segmentation')
            image=sitk.ReadImage(str(detail_path));require_geometry(image,reference)
            detail_airway=sitk.GetArrayFromImage(image)>0
        z = slider.value
        gray = np.clip((ct[z].astype(np.float32) + 1000) / 1400 * 255, 0, 255)
        rgb = np.repeat(gray[..., None], 3, axis=-1)
        for name, color in colors.items():
            if checks[name].value:
                selected = masks[name][z]
                if name=='airway':
                    if airway_mode.value=='network':selected=raw_airway[z]
                    elif airway_mode.value=='detail':selected=detail_airway[z]
                rgb[selected] = (1-opacity.value)*rgb[selected] + opacity.value*np.array(color)
                if name=='airway' and airway_mode.value=='detail':
                    added=selected & ~masks['airway'][z]
                    rgb[added]=(1-opacity.value)*rgb[added]+opacity.value*np.array([240,60,255])
        buffer = io.BytesIO(); Image.fromarray(rgb.astype(np.uint8)).save(buffer, format="PNG")
        picture.value = buffer.getvalue()
        caption.value = (f"<b>切片 {z+1}/{ct.shape[0]}</b>；原始层间距 {reference.GetSpacing()[2]:.3f} mm。"
                         f"<br>{result_label}；本 CT 无独立人工真值，当前为研究原型。")
        if airway_mode.value=='detail':
            ranges=['%d–%d'%(item['bounds_zyx'][0][0]+1,item['bounds_zyx'][0][1]) for item in detail_report['components'] if item['retained_candidate'] and 'bounds_zyx' in item]
            caption.value+='<br>紫色为新增近邻片段，尚未人工确认；未填补断点或生成连接桥。'
            if ranges:caption.value+=' 候选所在切片：'+', '.join(ranges)+'。'
    for control in [slider, opacity, airway_mode, *checks.values()]:
        control.observe(update, names="value")
    update()
    panel = widgets.VBox([caption, slider, widgets.HBox(list(checks.values())), airway_mode, opacity, picture])
    if display_panel:
        display(panel)
    return panel
