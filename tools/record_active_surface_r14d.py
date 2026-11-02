"""Record actual current-surface UI evidence without promoting production."""
from pathlib import Path
import hashlib,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main():
    rel='modules/surface_route/';results=ROOT/rel/'results'
    parent=ROOT/rel/'work_checkpoint_r13.json';old=read(parent)
    closure=ROOT/rel/'native_UI_source_closure_r14d.json';sources=dict(read(closure)['files_sha256'])
    for n,h in sources.items():assert sha(ROOT/n)==h,n
    evidence={}
    def bind(p):
        evidence[p.relative_to(ROOT).as_posix()]=sha(p)
        return read(p) if p.suffix=='.json' else None
    for platform in ('Windows','ARM'):
        proof=bind(results/f'active_binding_{platform}_{"r14" if platform=="Windows" else "r14d"}.json')
        assert proof['status']=='active_surface_comparison_target_constraints_and_display_integrity_passed' and len(proof['tests'])==10
        capability=bind(results/f'capabilities_{platform}_{"r14c" if platform=="Windows" else "r14d"}.json');assert len(capability['tests'])==5
    for p in (results/'capability_scene_ARM_r14d').iterdir():bind(p)
    build_path=ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r14d/build.json';build=bind(build_path)
    assert build['source_closure_sha256']==sha(closure) and build['source_sha256']==read(closure)['files_sha256']
    binary=build_path.parent/'medical_ui';assert sha(binary)==build['binary_sha256']
    evidence[binary.relative_to(ROOT).as_posix()]=sha(binary)
    evidence[(build_path.parent/'build.log').relative_to(ROOT).as_posix()]=sha(build_path.parent/'build.log')
    trial=bind(results/'active_surface_trial_ARM_r14d/acceptance.json')
    assert trial['status']=='ARM_current_surface_binding_build_HDMI_actions_and_PS_PL_replay_passed'
    for n,h in trial['evidence_sha256'].items():assert sha(ROOT/n)==h,n
    proof=bind(results/'native_active_surface_GUI_ARM_r14d/acceptance.json')
    assert proof['adapter_closure_sha256']==sha(closure) and proof['source_closure_sha256']==build['source_closure_sha256'] and not proof['production_promoted'] and not proof['physical_user_review']
    for n,h in proof['evidence_sha256'].items():assert sha(ROOT/n)==h,n;evidence[n]=h
    actual=proof['actual_UI'];render=proof['replayed_actual_UI_frame']
    assert all(x['passed'] for x in actual['checks']) and render['actual_manual_UI_camera_replayed']
    assert any(x['name']=='preview_highlights_current_target' and x['passed'] for x in actual['checks'])
    assert render['all_depth_normal_target_outline_words_exact_PS1_PS4_actual_PL'] and render['PL_over_PS4_speedup']>1
    assert render['full_static_1MiB_echo_and_C6_restore_passed'] and len(render['samples'])==3
    pixels_path=results/'native_active_surface_GUI_ARM_r14d/replayed_actual_UI_PL.u64'
    pixels=np.fromfile(pixels_path,dtype='<u8');assert len(pixels)==render['width']*render['height'] and sha(pixels_path)==render['PL_pixels_sha256']
    coverage=dict(surface_pixels=int(np.count_nonzero((pixels&65535)!=65535)),
        target_pixels=int(np.count_nonzero(((pixels>>np.uint64(16))&255)>0)),
        outline_pixels=int(np.count_nonzero(((pixels>>np.uint64(24))&255)>0)))
    assert all(value>0 for value in coverage.values()),coverage
    pixels_proof=results/'active_surface_pixel_validation_r14d.json';assert not pixels_proof.exists()
    pixels_proof.write_text(json.dumps(dict(status='actual_manual_UI_replay_has_wall_target_and_outline',pixels_sha256=sha(pixels_path),**coverage),indent=2)+'\n',encoding='utf-8')
    bind(pixels_proof)
    for n in ('active_surface_trial_ARM_r14d_started.json','active_surface_trial_ARM_r14d_terminal.json','active_surface_trial_ARM_r14d.log','active_surface_live_r14d.json'):
        bind(results/n)
    for n in ('active_surface_trial_ARM_r14_started.json','active_surface_trial_ARM_r14.log',
        'active_surface_trial_ARM_r14/failure.json','native_active_surface_GUI_ARM_r14/failure.json',
        'native_active_surface_GUI_ARM_r14/started.json','native_active_surface_GUI_ARM_r14/UI.log',
        'native_active_surface_GUI_ARM_r14/graceful_close_requested.json'):
        bind(results/n) if n.endswith('.json') else evidence.update({(results/n).relative_to(ROOT).as_posix():sha(results/n)})
    for n in ('active_surface_trial_ARM_r14b_started.json','active_surface_trial_ARM_r14b.log',
        'active_surface_trial_ARM_r14b/failure.json','native_active_surface_GUI_ARM_r14b/failure.json',
        'native_active_surface_GUI_ARM_r14b/started.json','native_active_surface_GUI_ARM_r14b/UI.log',
        'native_active_surface_GUI_ARM_r14b/graceful_close_requested.json'):bind(results/n)
    live=read(results/'active_surface_live_r14d.json')
    assert live['supervisor_terminal'] and live['PL_lock_free'] and not live['UI_processes']
    assert live['boot_id']==old['current_board_state']['boot_id']
    defaults=old['current_board_state']['preserved_defaults_sha256']
    for n,h in defaults.items():assert sha(ROOT/n)==h,n
    for n in (rel+'native_UI_source_closure_r14d.json','tools/record_active_surface_r14d.py','tools/finalize_active_surface_r14d.py','tools/launch_active_surface_review_r14d.py'):
        sources[n]=sha(ROOT/n)
    doc=ROOT/'docs/ACTIVE_SURFACE_UI_R14D.md';assert not doc.exists()
    text=f'''# 当前表面比较、选路与原生导航联动

普通透明度修复保持有效，用户已确认“表面完整，异常消失”。本批完成独立 R14d 原生界面的当前表面比较与采用路径入口；默认启动版本未替换，新功能尚未经过人工鼠标验收。

测试中发现旧的已验证场景缺少后加入的可用结构和体素计数字段，导致比较按钮被禁用。R14d 从已校验的打包掩膜补齐这些字段，原生比较预览显式选中当前目标候选；没有改动掩膜、C1 网格、标量或原有路线。Windows 与 ARM 各通过 5 项空掩膜、保留位、重叠结构及类型检查。首次与第二次未完成的界面试验日志均保留，没有当作通过。

截图复核还发现原预览默认圈选第 0 个候选。已改为显式使用当前目标，并加入预览目标编号检查。GUI 控制代码按 O1 编译以缩短迭代，渲染与传输代码仍按 O2 编译，计算库和 PL 核心不变。以下性能只采用最终版本实测。

界面按当前 C1 网格、标量场、CT、原始骨架及当前目标重新比较。比较只更新报告，不改变现有导航路线或模型。采用明确选中的 Pareto 候选时，重新审核完整曲线及安全前缀，再将路线、相机、HUD 和分岔引导作为同一个新版本载入。原始表面和分析属性仅在网格、顶点流和标量哈希完全相同后复用。切换目标或器械约束后，旧比较不能直接用于新选择。

## 验证

Windows 与 ARM 各通过 10 项数据完整性测试。板端实际 Qt/HDMI 自动操作切换了目标、重新比较，遍历全部五组器械的 Pareto 预览，并点击“审核并用于导航”。模型、路径、目标、相机和 HUD 配对检查通过；实际 C9 自动及手动镜头帧、绿色通道、轮廓和联动参考镜头的序号检查通过。共 {len(actual['checks'])} 项界面检查通过。这是实际界面自动测试，尚不代替人工观察。

从实际手动镜头帧提取相同输入再次对照：{render['width']}×{render['height']}；PS1、PS4 与实际 PL 的完整 64 位深度、法线、目标覆盖和轮廓输出一致。三次热调用中位数：PS4 {render['PS4_median_seconds']*1000:.2f} ms，PL {render['PL_median_seconds']*1000:.2f} ms，PL 快 {render['PL_over_PS4_speedup']:.2f} 倍。时间包含完整调用、同步、复制和保护区检查，不含共同数据准备、场景上传、文件写出及显示，不能当作 HDMI 帧率。UI 进程峰值 RSS 为 {actual['UI_peak_RSS_MiB']:.1f} MiB，未包含所有子进程。

## PS / PL

PS：Qt 操作与图表、当前数据验证、比较报告、选路审核、相机与引导准备。器械比较继续使用先前同输入实测更快的优化 PS4；原 C4/R4 硬件结果作为对照保留。

PL：既有 C9 管壁、法线、目标覆盖和轮廓渲染，四路流水线 II=1、100 MHz。本批未生成新位流，资源占用沿用该版本：全设计 LUT 46,292、FF 49,672、DSP 328、BRAM36 121、URAM 64。测试期间按既有 DFX 协议使用 C9，结束后完成静态 1 MiB 回环并恢复 C6；未重载静态壳或卸载驱动。

代码位于 `modules/surface_route/active_actions_r14.py`、`active_backend_r14.py`，原生入口位于 `ui/releases/feature_completion_r6/src/main_complete_scene_r14d.cpp`。证据入口是 `modules/surface_route/results/native_active_surface_GUI_ARM_r14d/acceptance.json`。旧源码与默认启动配置保持不变。

待完成：本批人工验收；当前完整表面的精度/新病例入口；当前场景批量图像、视频和恢复接口；冷启动验证复用及原 Python 剩余视觉控制。
'''
    doc.write_text(text,encoding='utf-8',newline='\n');evidence[doc.relative_to(ROOT).as_posix()]=sha(doc)
    checkpoint=ROOT/rel/'work_checkpoint_r14d.json';assert not checkpoint.exists()
    status='actual_native_current_surface_comparison_selected_path_C9_manual_camera_and_PS_PL_replay_verified'
    current=dict(old['current_board_state'],status='R14_native_trials_terminal_C6_restored_defaults_preserved',ordinary_available_bytes=live['ordinary_available_bytes'])
    checkpoint.write_text(json.dumps(dict(status=status,goal_turn_classification='progress',whole_goal_completed=False,
        production_promoted=False,sealed_parent_checkpoint=parent.relative_to(ROOT).as_posix(),sealed_parent_checkpoint_sha256=sha(parent),
        source_sha256=sources,evidence_sha256=evidence,current_board_state=current,
        native_UI_scope=dict(current_surface_comparison_integrated=True,current_surface_selected_path_integrated=True,
            changed_target_tested=True,actual_Qt_checks=len(actual['checks']),binding_tests_per_platform=10,physical_review=False),
        same_actual_manual_camera_API_metrics=render,actual_UI_replay_pixel_counts=coverage,UI_peak_RSS_MiB=actual['UI_peak_RSS_MiB'],
        remaining=['R14 native current-surface controls physical review','active quality selection and generic completed-new-case producer',
            'active-scene batch image video and recovery dispatch','cold immutable asset verification reuse and remaining original Python visual controls'],
        new_bitstream=False,static_shell_reload=False,driver_unload=False),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for n in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):
        p=ROOT/n;state=read(p);state['previous_goal_turn_result']=state['current_goal_turn_result']
        state['current_goal_turn_result']=dict(classification='progress',checkpoint=checkpoint.relative_to(ROOT).as_posix(),status=status,whole_goal_completed=False,production_promoted=False)
        state['current_surface_route_checkpoint']=checkpoint.relative_to(ROOT).as_posix()
        state['active_surface_UI_r14d']=dict(checkpoint=checkpoint.relative_to(ROOT).as_posix(),actual_Qt_checks=len(actual['checks']),physical_review=False,production_promoted=False)
        p.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('R14 actual UI and same-input evidence recorded',flush=True)


if __name__=='__main__':main()
