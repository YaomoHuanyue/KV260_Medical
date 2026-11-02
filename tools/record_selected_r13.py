"""Close tested R13 outputs and advance only the active progress pointers."""
from pathlib import Path
import json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    result=ROOT/'modules/surface_route/results';parent=ROOT/'modules/surface_route/work_checkpoint_r12.json'
    source=ROOT/'modules/surface_route/selected_source_closure_r13.json'
    closure=read(source);proofs={};evidence={}
    for platform in ('Windows','ARM'):
        for kind in ('selected_kernels','selected_actions'):
            p=result/f'{kind}_{platform}_r13.json';doc=read(p)
            assert 'passed' in doc['status'];evidence[p.relative_to(ROOT).as_posix()]=sha(p)
        p=result/f'selected_own_CT_{platform}_r13/acceptance.json';proofs[platform]=read(p)
        assert proofs[platform]['source_closure_sha256']==sha(source) and len(proofs[platform]['cases'])==6
        for name,h in proofs[platform]['evidence_sha256'].items():
            path=p.parent/name;assert sha(path)==h,name;evidence[path.relative_to(ROOT).as_posix()]=h
        evidence[p.relative_to(ROOT).as_posix()]=sha(p)
    matched=[]
    for w,a in zip(proofs['Windows']['cases'],proofs['ARM']['cases']):
        assert (w['label'],w['kind'],w['group_index'],w['candidate_id'])==(a['label'],a['kind'],a['group_index'],a['candidate_id'])
        assert w['available_branch_events']==a['available_branch_events']
        for name in ('route.npz','camera.npz'):
            with np.load(ROOT/w['bundle']/name,allow_pickle=False) as wx,np.load(ROOT/a['bundle']/name,allow_pickle=False) as ax:
                assert set(wx.files)==set(ax.files)
                for key in wx.files:
                    assert wx[key].shape==ax[key].shape,(name,key)
                    if key=='clearance_state':np.testing.assert_array_equal(wx[key],ax[key])
                    elif wx[key].dtype.kind in 'f':np.testing.assert_allclose(wx[key],ax[key],rtol=0,atol=1e-7,err_msg=w['label']+'/'+key)
                    else:np.testing.assert_array_equal(wx[key],ax[key])
        matched.append(dict(label=w['label'],kind=w['kind'],route_and_camera_columns_equal_with_float64_atol_1e_7=True,
            integer_node_ids_and_clearance_states_exact=True,available_branch_events=w['available_branch_events']))
    equivalence=result/'selected_equivalence_r13.json';assert not equivalence.exists()
    equivalence.write_text(json.dumps(dict(status='Windows_ARM_selected_route_camera_and_cue_counts_match',cases=matched),indent=2)+'\n',encoding='utf-8')
    evidence[equivalence.relative_to(ROOT).as_posix()]=sha(equivalence)
    hardware=result/'selected_actual_PL_ARM_r13/acceptance.json';h=read(hardware)
    assert h['status']=='selected_current_surface_C4_and_all_branch_C9_PS_PL_checked_C6_restored'
    assert h['all_C9_frames_faster_than_PS4'] and len(h['audit_cases'])==6 and len(h['render_cases'])==16
    for name,value in h['evidence_sha256'].items():
        p=hardware.parent/name;assert sha(p)==value;evidence[p.relative_to(ROOT).as_posix()]=value
    evidence[hardware.relative_to(ROOT).as_posix()]=sha(hardware)
    for name in ('selected_trial_ARM_r13/acceptance.json','selected_trial_ARM_r13_started.json',
                 'selected_trial_ARM_r13_terminal.json','selected_trial_ARM_r13.log','selected_live_r13.json'):
        p=result/name;assert p.is_file();evidence[p.relative_to(ROOT).as_posix()]=sha(p)
    live=read(result/'selected_live_r13.json');assert live['test_processes_terminal'] and live['PL_lock_free']
    assert not live['UI_processes'] and live['boot_id']==read(parent)['current_board_state']['boot_id']
    sources=dict(closure['files_sha256'])
    for name in ('modules/surface_route/selected_source_closure_r13.json','modules/surface_route/actual_selected_C9_r13.py',
        'modules/surface_route/test_selected_actions_r13.py','tools/selected_trial_r13.py','tools/record_selected_r13.py',
        'tools/finalize_selected_r13.py'):
        sources[name]=sha(ROOT/name)
    rows=[]
    for label in sorted({x['label'] for x in h['render_cases']}):
        group=[x for x in h['render_cases'] if x['label']==label]
        rows.append(dict(label=label,frames=len(group),width=640,height=363,
            median_PS4_frame_seconds=float(np.median([x['PS4_median_full_call_seconds'] for x in group])),
            median_PL_frame_seconds=float(np.median([x['PL_median_full_call_seconds'] for x in group])),
            minimum_PL_over_PS4_speedup=min(x['PL_over_PS4_speedup'] for x in group),
            maximum_PL_over_PS4_speedup=max(x['PL_over_PS4_speedup'] for x in group)))
    doc=ROOT/'docs/SELECTED_SURFACE_NAVIGATION_R13.md';assert not doc.exists()
    text='''# 当前表面选路、相机与分岔引导验证

本批完成 R13 后端与实际 PL 验证，尚未接入新表面候选界面的比较/采用按钮，也未替换默认界面。普通透明修复及已通过的人工验收保持有效。

选择一个完整原始图上的 Pareto 候选后，先核对比较报告、原始父节点链、当前标量、C1 网格、CT 和目标。把所选曲线作为线性图重新审核，不能换到另一分支。连续管壁、裁剪边界、源掩膜区间和原弯曲前缀策略继续执行。按生产者保留的真实源参数映射骨架节点，截短后移除尚未到达的节点，不使用长度比例猜测位置。

重新生成的路线、相机、HUD、分岔轮廓标签和 C9 数据包绑定为一个完整不可变版本。若原始 26 邻接图选中非原导航森林边，单独派生包含所选链的引导森林，保留节点、连通分量和原掩膜，并记录替换边。此次自带 CT 的候选链均位于原森林，无需替换。

Windows 与 ARM 各通过 7 项几何/引导测试和 11 项错误输入检查；自带 CT 的二值与网络概率、高清与超清四种表面各生成完整选路场景。完整场景每条路径 1025 个采样点、3 个有效分岔标记；非零弯曲约束的测试路径截为起点时，不生成运动相机或前方标记。完整路径硬件渲染测试显式使用弯曲阈值 0；另测阈值 1 的拒绝/截短行为，未修改默认器械约束。

既有 C9 对四种表面的三个分岔及第一处分岔的手动视角，共 16 帧逐像素比较。640×363，最大 1023 步；PS1、PS4 与实际 PL 的深度、法线、目标覆盖和轮廓全部 64 位输出一致。每帧均有管壁、目标覆盖和轮廓，DMA 保护区、令牌与输入检查通过。新路径 C4 审核也进行了同输入完整 8706 字输出检查，浮点统计容差 1e-7/2e-9、状态精确。

| 表面 | PS4 帧 API / ms | PL 帧 API / ms | PL/PS4 提速范围 |
|---|---:|---:|---:|
'''
    for row in rows:text+=f"| {row['label']} | {row['median_PS4_frame_seconds']*1000:.2f} | {row['median_PL_frame_seconds']*1000:.2f} | {row['minimum_PL_over_PS4_speedup']:.2f}—{row['maximum_PL_over_PS4_speedup']:.2f}× |\n"
    text+='\n帧时间包含复制、同步、保护区和检查，不含共同场景准备、场景上传、文件写出及 HDMI 显示，不是界面 FPS。冷上传与每项准备时间另存。C4 单独审核仍由原优化 PS 实现承担，实际 PL 用于对照，没有因硬件名义强行替换。R4 器械比较继续沿用 R12 实测结论，默认使用更快的 PS4。\n\n没有生成新位流或重载静态壳，没有卸载驱动。实际测试结束已完成完整静态 1 MiB 回环并恢复 C6。\n\n代码：`modules/surface_route/surface_actions_r13.py`、`selected_surface_r13.py`、`guidance_r13.py`。真实数据及证据：`modules/surface_route/results/selected_own_CT_ARM_r13/`、`selected_actual_PL_ARM_r13/acceptance.json`。\n\n待完成：新表面比较/采用路径的原生界面接入与人工验收；新病例与精度入口；当前场景批量图像/视频/恢复分支接口；原 Python 其余视觉控制和性能对照。\n'
    doc.write_text(text,encoding='utf-8',newline='\n');evidence[doc.relative_to(ROOT).as_posix()]=sha(doc)
    checkpoint=ROOT/'modules/surface_route/work_checkpoint_r13.json';assert not checkpoint.exists()
    status='selected_current_surfaces_path_prefix_camera_guidance_actual_C4_C9_verified_backend_only'
    board_state=dict(read(parent)['current_board_state'],status='selected_backend_trials_terminal_C6_restored_defaults_preserved',
        ordinary_available_bytes=live['ordinary_available_bytes'],UI_processes=live['UI_processes'],test_processes=[])
    checkpoint.write_text(json.dumps(dict(status=status,goal_turn_classification='progress',whole_goal_completed=False,
        production_promoted=False,sealed_parent_checkpoint=parent.relative_to(ROOT).as_posix(),sealed_parent_checkpoint_sha256=sha(parent),
        source_sha256=sources,evidence_sha256=evidence,current_board_state=board_state,
        selected_backend_scope=dict(full_CT_surface_cases=4,geometry_tests_per_platform=7,negative_tests_per_platform=11,
            complete_cases=6,actual_C4_cases=6,actual_C9_frames=16,source_geometry_or_masks_modified=False,
            native_UI_comparison_and_selected_path_controls_integrated=False,physical_review=False),
        C9_same_input_API_metrics=rows,C4_same_input_API_metrics=[{k:v for k,v in x.items() if k not in ('samples',)} for x in h['audit_cases']],
        ARM_preparation_peak_RSS_MiB=proofs['ARM']['peak_preparation_test_RSS_MiB'],hardware_test_peak_RSS_MiB=h['peak_hardware_test_RSS_MiB'],
        remaining=['active-surface native comparison and selected-path UI integration and physical review',
            'active quality selection and generic completed-new-case producer',
            'active-scene batch image video and recovery dispatch',
            'cold immutable asset verification reuse and remaining original Python visual controls'],
        new_bitstream=False,static_shell_reload=False,driver_unload=False),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for name in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):
        p=ROOT/name;data=read(p)
        data['previous_goal_turn_result']=data.get('current_goal_turn_result')
        data['current_goal_turn_result']=dict(classification='progress',checkpoint=checkpoint.relative_to(ROOT).as_posix(),
            status=status,whole_goal_completed=False,production_promoted=False)
        data['current_surface_route_checkpoint']=checkpoint.relative_to(ROOT).as_posix()
        data['selected_surface_backend_r13']=dict(checkpoint=checkpoint.relative_to(ROOT).as_posix(),
            status=status,actual_C9_frames=16,native_UI_integration_pending=True,production_promoted=False)
        p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('R13 backend checkpoint recorded',len(sources),len(evidence))


if __name__=='__main__':main()
