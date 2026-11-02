"""Publish actual R11/R12 proof and preserve the remaining full feature scope."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main():
    folder=ROOT/'modules/surface_route';checkpoint=folder/'work_checkpoint_r12.json'
    assert not checkpoint.exists()
    kernel=[folder/'results'/f'comparison_kernels_{p}_r{v}.json' for p in ('Windows','ARM') for v in (11,12)]
    for path in kernel:assert read(path)['status'].endswith('passed')
    equivalence={p:read(folder/'results'/f'comparison_equivalence_{p}_r12.json') for p in ('Windows','ARM')}
    for proof in equivalence.values():
        assert len(proof['cases'])==4 and all(c['all_report_fields_and_saved_arrays_exact'] for c in proof['cases'])
    hardware=read(folder/'results/comparison_own_CT_ARM_r12/acceptance.json')
    assert hardware['PL_access'] and hardware['full_static_1MiB_echo_and_C6_restore_passed']
    assert len(hardware['cases'])==4
    for case in hardware['cases']:
        assert case['raw_nodes']==863 and case['raw_edges']==871 and case['original_forest_edges']==862
        assert case['all_FP64_costs_parents_profiles_candidates_and_path_arrays_exact']
        assert len(case['samples'])==3
        for sample in case['samples']:
            assert set(sample['providers'])=={'PS1','PS4','PL_R4'}
            assert all(call['all_four_full_4096_byte_DMA_guards_checked'] for call in sample['providers']['PL_R4']['PL_calls'])
    live=read(ROOT/'results/comparison_live_r12.json')
    assert live['PL_lock_free'] and not live['UI_processes'] and not live['test_processes']
    for p,h in live['preserved_defaults_sha256'].items():assert sha(ROOT/p)==h,p
    rows=equivalence['ARM']['cases']
    assert all(row['PL_over_strongest_PS_solve_API_speedup']<1 for row in rows)
    profile=read(folder/'results/comparison_profile_ARM_r12/acceptance.json')
    assert profile['status']=='actual_complete_report_profiled_with_full_output_equivalence'
    lines=['# 新表面器械比较与根节点复用实测','',
        '此批补齐新 C1 表面下的完整原始骨架器械比较与 Pareto 候选生成，并在板卡运行已有 R4 PL 比较核。HDMI 新表面候选界面的比较按钮、选择路径后重建相机及分岔引导仍待接入，本批没有替换默认界面。','',
        '原始 863 个骨架节点、871 条 26 邻接边全部进入比较；862 边的导航森林不替代原始比较图。按新表面连续管壁、裁剪边界、原始掩膜和器械尺寸筛选，保留原始代价公式、全可达节点候选、80 个候选上限及 8 条 Pareto 上限。只扣除一次原始图像分辨率余量。','',
        '优化只复用同一不可变模型中、完全相同物理坐标的根节点绕数。管壁距离、整段连续下界、掩膜区间和完整路径检查继续执行。四组模型优化前后的所有报告字段（计时与复用计数除外）及保存数组逐项一致。','',
        '| 模型 | 优化前 PS 完整 API / s | 优化后 PS 完整 API / s | 同 PS 提速 | 优化后 PL 完整 API / s | PL 求路 / PS 求路提速 |',
        '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        providers=row['optimized_medians'];ps=min(('PS1','PS4'),key=lambda p:providers[p]['full_report_API_seconds'])
        old=row['baseline_medians'][ps]['full_report_API_seconds'];new=providers[ps]['full_report_API_seconds']
        lines.append(f"| {row['label']} | {old:.4f} | {new:.4f} | {old/new:.2f}× | {providers['PL_R4']['full_report_API_seconds']:.4f} | {row['PL_over_strongest_PS_solve_API_speedup']:.3f}× |")
    lines+=['','计时为三次交替执行的中位数。完整 API 包含求路、所有候选生成、实际连续管壁审核及报告计算；不含共同的模型验证/几何预处理和文件写出，这些另存于 prepared_input.json。PS1、PS4 和实际 PL 使用完全相同的筛选图与半径；每次都重新计算，完整输出、8706 字输出容量和四个 4096 字节 DMA 保护区均检查。',
        '',f"板端测试进程峰值 RSS：{hardware['peak_test_process_RSS_MiB']:.1f} MiB。此数字包含验证、几何模型和测试结果数组，不能当成医疗应用完整流程的内存峰值。",'',
        '实际 PL 求路仍慢于最强 PS，因此 R4 保留为实测后端，不提升为默认。新网格拓扑由既有 PL C1 产生；器械比较中的三角形距离与候选整理运行于 PS。本批未生成新位流，结束后完整静态 1 MiB 回环检查通过并恢复 C6，未重新加载静态壳或卸载驱动。','',
        '源代码：modules/surface_route/comparison_r11.py（完整比较）、comparison_r12.py（根节点复用）、own_CT_comparison_r12.py（同输入实测）。实际输出在 modules/surface_route/results/comparison_own_CT_ARM_r12/；完整等价与时间证据为 comparison_equivalence_ARM_r12.json。','',
        '后续按原目标继续：接入新表面比较界面与选路后的相机/分岔引导；新病例和建模精度入口；当前场景的批量图像、视频与恢复分支接口；原 Python 其余视觉控制和性能对照。']
    lines+=['','## 剩余耗时采样','',
        '下面是在测试完成后单独执行的完整报告分析，含分析器开销，不参与上表性能对比。累计时间包含子调用，不可直接求和。','',
        '| 函数 | 调用次数 | 累计 / s | 自身 / s |','|---|---:|---:|---:|']
    for item in profile['top_cumulative'][:12]:
        lines.append(f"| {item['function']} | {item['calls']} | {item['cumulative_seconds']:.4f} | {item['self_seconds']:.4f} |")
    doc=ROOT/'docs/ACTIVE_SURFACE_COMPARISON_R12.md'
    with doc.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
    closure=folder/'comparison_source_closure_r12.json';c=read(closure)
    sources={**read(ROOT/c['sealed_parent_closure'])['files_sha256'],**c['files_sha256']}
    extra=[Path(__file__),folder/'compare_trials_r12.py',ROOT/'tools/comparison_trial_r11.py',
           ROOT/'tools/finalize_comparison_r12.py',ROOT/'tools/profile_comparison_r12.py',closure,folder/'comparison_source_closure_r11.json']
    sources.update({p.relative_to(ROOT).as_posix():sha(p) for p in extra})
    evidence=kernel+[doc,folder/'work_checkpoint_r10.json',ROOT/'results/comparison_live_r12.json']
    for host in ('Windows','ARM'):
        names=[f'comparison_own_CT_{host}_r12',f'comparison_own_CT_{host}_'+('all_r11' if host=='Windows' else 'r11')]
        for name in names:evidence+=list((folder/'results'/name).rglob('*'))
        evidence.append(folder/'results'/f'comparison_equivalence_{host}_r12.json')
    for revision in (11,12):
        evidence+=list((folder/'results'/f'comparison_trial_ARM_r{revision}').rglob('*'))
        evidence+=list((folder/'results').glob(f'comparison_trial_ARM_r{revision}*.*'))
    evidence+=list((folder/'results/comparison_profile_ARM_r12').rglob('*'))
    evidence+=list((folder/'results').glob('comparison_profile_ARM_r12*.*'))
    result=dict(status='four_active_surface_PS1_PS4_actual_PL_exact_and_root_winding_reuse_verified',
        goal_turn_classification='progress',whole_goal_completed=False,production_promoted=False,
        source_sha256=sources,evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(evidence)) if p.is_file()},
        previous_checkpoint_sha256=sha(folder/'work_checkpoint_r10.json'),current_board_state=live,
        actual_PL_full_report_comparison=True,new_bitstream=False,
        R4_profile_promoted=False,profile_speed_gate='PL solver slower than strongest PS; retained for comparison only',
        complete_original_raw_graph_nodes=863,complete_original_raw_graph_edges=871,
        optimized_board_comparisons=rows,peak_test_process_RSS_MiB=hardware['peak_test_process_RSS_MiB'],
        remaining_hotspot_evidence='modules/surface_route/results/comparison_profile_ARM_r12/acceptance.json',
        current_active_surface_UI_comparison_available=False,
        next_actions=['Integrate active-scene profiles and Pareto UI and bind selected path to rebuilt camera/branch guidance',
            'Integrate explicit scene/quality selection and generic new-run scene preparation',
            'Bind batch/video/recovery dispatch to active scene and complete their physical review',
            'Reduce repeated cold full-asset verification with immutable content binding',
            'Complete original exposure/vignette/outline glow/ray-step heatmap/breathing and remaining performance comparisons'])
    write_json(checkpoint,result)
    changes={}
    for relative in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):
        path=ROOT/relative;old=sha(path);value=read(path)
        value['previous_goal_turn_result']=value.get('current_goal_turn_result')
        value['current_goal_turn_result']=dict(classification='progress',checkpoint=checkpoint.relative_to(ROOT).as_posix(),
            status=result['status'],whole_goal_completed=False,production_promoted=False)
        value['current_surface_route_checkpoint']=checkpoint.relative_to(ROOT).as_posix()
        if relative.startswith('docs/'):
            value['current_board_UI_state']=live
        else:
            value['status']='active_original_feature_completion_surface_comparison_R12_verified'
            value['last_current_board_state_receipt']='results/comparison_live_r12.json'
            value['current_board_boot_id']=live['boot_id']
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
        changes[relative]=dict(previous_sha256=old,new_sha256=sha(path))
    write_json(folder/'results/comparison_progress_plan_r12.json',dict(files=changes))
    print(result['status'],flush=True)


if __name__=='__main__':main()
