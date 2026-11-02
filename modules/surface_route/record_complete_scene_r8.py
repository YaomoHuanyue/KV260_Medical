"""Close the R8 milestone and advance only explicitly mutable progress ledgers."""
from pathlib import Path
import json
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import sha, write_json


def main():
    result = ROOT/'modules/surface_route/results'
    reference = json.loads((result/'reference_frames_ARM_r8/acceptance.json').read_text())
    cross = json.loads((result/'complete_bundles_cross_platform_r8b.json').read_text())
    live = json.loads((ROOT/'results/complete_scene_live_r8.json').read_text())
    assert len(reference['cases']) == len(cross['cases']) == 8 and not reference['PL_access']
    assert all(c['every_depth_normal_target_outline_word_exact_PS1_PS4'] for c in reference['cases'])
    for platform in ('Windows', 'ARM'):
        assert json.loads((result/f'bundle_dispatch_tests_{platform}_r8.json').read_text())['count'] == 19
        assert len(json.loads((result/f'portable_reader_tests_{platform}_r8b.json').read_text())['cases']) == 4
    sources = [
        'modules/surface_route/'+n for n in [
            'bundle_r8.py', 'prepare_bundles_r8.py', 'scene_runtime_r8.py', 'quality_worker_r8.py',
            'test_bundle_r8.py', 'bundle_reader_r8b.py', 'compare_bundles_r8b.py',
            'portable_reader_derivation_r8b.json', 'test_portable_reader_r8b.py',
            'reference_frames_r8b.py', 'reference_frames_derivation_r8b.json',
            'README_COMPLETE_SCENES_r8.md', 'record_complete_scene_r8.py']]
    sources += ['tools/verify_complete_scenes_r8.py', 'tools/cleanup_complete_surface_transfers_r8.py']
    evidence = [ROOT/'results/complete_scene_live_r8.json', result/'complete_bundles_cross_platform_r8b.json',
                result/'reference_frames_ARM_r8/acceptance.json', ROOT/'modules/surface_route/work_checkpoint_r7.json']
    for platform in ('Windows', 'ARM'):
        evidence += [result/f'bundle_dispatch_tests_{platform}_r8.json',
                     result/f'portable_reader_tests_{platform}_r8b.json',
                     result/f'worker_prepare_{platform}_r8.json']
        folder = result/f'complete_bundles_{platform}_r8'
        proof = json.loads((folder/'acceptance.json').read_text()); assert len(proof['cases']) == 8
        evidence += [folder/'acceptance.json']+[folder/c['label']/'scene.json' for c in proof['cases']]
    evidence += [result/'reference_frames_ARM_r8'/c['label']/'report.json' for c in reference['cases']]
    evidence += [result/n for n in ['complete_bundle_ARM_r8_started.json', 'complete_bundle_ARM_r8_terminal.json',
        'reference_frames_ARM_r8_started.json', 'reference_frames_ARM_r8_failed.json',
        'reference_frames_ARM_r8b_started.json', 'reference_frames_ARM_r8b.log']]
    source_hashes = {n: sha(ROOT/n) for n in sources}
    for n, h in reference['reference_bound_files'].items():
        assert sha(ROOT/n) == h; source_hashes[n] = h
    times = [c['PS4_median_full_call_seconds'] for c in reference['cases']]
    checkpoint = dict(status='eight_complete_original_surface_scenes_and_full_resolution_PS_references_verified_UI_C9_pending',
        goal_turn_classification='progress', whole_goal_completed=False, production_promoted=False,
        source_sha256=source_hashes,
        evidence_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in evidence},
        current_board_state=live, source_and_default_UI_preserved=True,
        PL_access_this_milestone=False, new_bitstream=False,
        computation=dict(PL='retained earlier actual C1 topology; existing C9 available but not accessed in R8',
            PS='complete bundle preparation, mesh overview normals, route/camera/guidance validation and PS1/PS4 reference rendering'),
        validation=dict(complete_bundles=8, Windows_binding_dispatch_cases=19, ARM_binding_dispatch_cases=19,
            Windows_portable_reader_cases=4, ARM_portable_reader_cases=4, cross_platform_packet_bytes_exact=True,
            reference_frames=8, viewport=[640, 363], maximum_steps=1023,
            every_depth_normal_target_outline_word_exact_PS1_PS4=True,
            PS4_render_full_call_seconds_range=[min(times), max(times)],
            reference_test_peak_RSS_MiB=reference['maximum_test_process_RSS_MiB'],
            statistics_are_not_UI_FPS_or_production_memory=True),
        known_failures_preserved=[
            'Strict R8 cross-platform recomputed camera up differs 2.22e-16; portable reader retains exact positions and permits axis roundoff1e-12.',
            'First reference script stopped with unmatched parenthesis before initialization; original source/log retained, corrected R8b completed.'],
        next_actions=[
            'Integrate complete scene into a new native Qt candidate, atomically updating mesh/path/camera/HUD/selected-exit; no automatic delayed geometry swaps.',
            'Safely initialize the medical static shell for this boot without the old ZOCL-unload path before any actual C9 trial.',
            'Replay the saved exact eight requests/scene packets on actual C9, compare all64bit pixels to strongest PS and verify DMA guards/C6 restoration.',
            'Measure and reduce cold preparation/proof IO; current batch proof generation is offline and must not enter per-frame paths.',
            'Complete native UI regressions and physical review; retain the original broader feature/profile/smoothing/performance goals.'])
    write_json(ROOT/'modules/surface_route/work_checkpoint_r8.json', checkpoint)
    report = '''# 完整表面数据与导航交接 R8 验证结果

已完成四种原始表面的八份完整包：四份 1 mm 弯曲约束路径和四份根点路径。每份同时绑定实际 PL C1 网格、原 Q5/Q6 标量、新路径、相机、分岔标签及同一路径的 HUD。Windows/ARM 的 C9 数据包字节一致，网格坐标与索引一致；路径/相机全量对照通过。

Windows 和 ARM 各通过 19 项绑定/交互队列测试、4 项便携读取误差边界测试，以及完整场景 worker 准备合同。严格相机轴逐位比较的跨平台浮点尾差保留在记录中；便携读取器只允许 1e-12 的方向尾差，相机位置仍完全一致。

八个 640×363、最多 1023 步的自动对齐/手动镜头在 ARM 上完成 PS1/PS4 对照，全部 64 位像素完全一致。PS4 调用中位数约 0.915—1.185 秒/帧，测试进程峰值 RSS 约 557.8 MiB。此数不是完整界面帧率、产品内存峰值或 PL 加速比。第一次参考脚本的语法失败保留；成功结果来自 reference_frames_r8b.py。

当前 HDMI 默认版本未替换，没有加载新的静态或部分位流。板卡当前启动仍是 starter-kit 外壳，医疗 UI 未运行。R8 是完成的数据准备与交接接口，原生 Qt 接入、当前启动上的实际 C9 同输入加速对照和实机交互验收仍未完成。

代码目录：本地 D:\\Xilinx_Project\\2026FPGA\\kv260_system\\modules\\surface_route；板端 /home/ubuntu/jupyter_notebooks/KV260_System/modules/surface_route。

详细接口见 README_COMPLETE_SCENES_r8.md。便携读取使用 bundle_reader_r8b.py / compare_bundles_r8b.py；成功的 ARM 参考渲染入口为 reference_frames_r8b.py。最终状态及完整 SHA 绑定见 work_checkpoint_r8.json。所有场景、镜头和参考像素保留；本轮传输 ZIP 在两端校验负载后清除。
'''
    path = ROOT/'docs/COMPLETE_SCENES_R8.md'
    with path.open('x', encoding='utf-8', newline='\n') as stream: stream.write(report)
    plans = {}
    for name in ['docs/FEATURE_COMPLETION_PROGRESS.json', 'dfx/smooth_speed/work_checkpoint.json']:
        path = ROOT/name; old = sha(path); data = json.loads(path.read_text(encoding='utf-8'))
        assert data['current_surface_route_checkpoint'] == 'modules/surface_route/work_checkpoint_r7.json'
        data['current_surface_route_checkpoint'] = 'modules/surface_route/work_checkpoint_r8.json'
        data['current_goal_turn_result'] = 'progress'
        data['previous_goal_turn_classification'] = 'progress'
        if name.startswith('docs/'):
            data['completed_batches'].append(dict(feature='complete_original_surface_scene_bundle_R8',
                state=checkpoint['status'], checkpoint='modules/surface_route/work_checkpoint_r8.json',
                whole_UI_or_goal_completed=False, PL_access=False))
            data['current_board_UI_state']['receipt'] = 'results/complete_scene_live_r8.json'
            for item in data['next']:
                if item.get('feature') == 'new_surface_graph_replanning_and_complete_UI_binding':
                    item['state'] = checkpoint['status']
                    item['scope'] += ' R8 eight atomic scene bundles, both-host19+4 tests and eight640x363 ARM PS1/4 references passed; Qt activation and actual C9 remain pending.'
            data['remaining_from_original_audit'] = [x+' R8 complete bundle/PS reference backend now passed, still no UI/C9 promotion.' if isinstance(x,str) and x.startswith('Original probability/isotropic SDF') else x for x in data['remaining_from_original_audit']]
        else:
            data['previous_status_before_R8'] = data['status']
            data['status'] = 'active_original_feature_completion_complete_surface_bundles_R8_C9_UI_pending'
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
        plans[name] = dict(previous_sha256=old, new_sha256=sha(path))
    archive = ROOT/'tools/complete_surface_progress_r8.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for n in plans: z.write(ROOT/n, n)
        z.writestr('progress_manifest.json', json.dumps(plans, indent=2)+'\n')
    print(json.dumps(dict(checkpoint=checkpoint['status'], progress_zip_sha256=sha(archive))))


if __name__ == '__main__': main()
