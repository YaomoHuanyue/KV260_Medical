"""Real BO-pool tests; PS is used only for fixture/reference calculations."""
from pathlib import Path
import json
import shutil
import numpy as np
from fpga.mc_host import to_mesh
from fpga.smooth_host import prepare
from modules.reconstruction.axis_mc_8_r2.integrated_pooled_r3.reconstruction import write_smooth_inputs


def copied_inputs(original, target):
    target.mkdir(exist_ok=False)
    for name in ['config.txt', 'original.bin', 'rows.bin', 'edges.bin', 'frozen.bin', 'faces.bin', 'mesh_before.npz']:
        shutil.copyfile(original / name, target / name)
    return target


def exercise_pool(session, tiny, first, ps, reference, work):
    assert first['pool_allocations_this_call'] == 11 and first['pool_reused_buffers_this_call'] == 0
    mask = np.zeros((24,24,24),np.uint8)
    mask[5:19,5:19,5:19] = 1
    words, _ = ps.run(mask,4)
    points, faces = to_mesh(words,(1,1,1),(0,0,0),np.eye(3),np.zeros(3,int))
    larger = work / 'pool_growth'
    larger.mkdir()
    np.savez(larger / 'mesh_before.npz',points=points,faces=faces)
    write_smooth_inputs(larger,prepare(points,faces,.1,8))
    grown = session.run('smooth',larger,larger/'points.f32',larger/'smooth.json')
    assert grown['pool_allocations_this_call'] == 10 and grown['pool_reused_buffers_this_call'] == 1
    reference(larger,grown)
    modified = copied_inputs(tiny,work/'same_shape_changed_data')
    data = np.fromfile(modified/'original.bin','<f4').reshape(-1,4)
    data[:,0] += np.float32(.25)
    data.tofile(modified/'original.bin')
    fixed = np.fromfile(modified/'frozen.bin','<u4')
    fixed[:] = 1
    fixed.tofile(modified/'frozen.bin')
    with np.load(tiny/'mesh_before.npz',allow_pickle=False) as old:
        np.savez(modified/'mesh_before.npz',points=data[:,:3].copy(),faces=old['faces'])
    changed = session.run('smooth',modified,modified/'points.f32',modified/'smooth.json')
    assert changed['pool_allocations_this_call'] == 0 and changed['pool_reused_buffers_this_call'] == 11
    assert changed['pool_capacity_bytes'] == grown['pool_capacity_bytes']
    changed_reference=reference(modified,changed,all_vertices_frozen=True)
    np.testing.assert_array_equal(np.fromfile(modified/'points.f32','<f4').reshape(-1,4),data)
    rejected = []
    errors=dict(point_nonfinite='Nonfinite point',CSR_order='Invalid CSR',edge_index='Invalid edge',
        weight_nonfinite='Invalid edge',weight_zero='Invalid edge',face_index='Invalid face',
        frozen_flag='Invalid frozen flag',source_size='Input size mismatch',iterations='Invalid smoothing configuration')
    for name,expected_error in errors.items():
        folder = copied_inputs(tiny,work/('bad_'+name))
        if name == 'point_nonfinite':
            value=np.fromfile(folder/'original.bin','<f4');value[0]=np.nan;value.tofile(folder/'original.bin')
        elif name == 'CSR_order':
            value=np.fromfile(folder/'rows.bin','<u4');value[1]=value[-1]+1;value.tofile(folder/'rows.bin')
        elif name == 'edge_index':
            value=np.fromfile(folder/'edges.bin','<u4');value[0]=data.shape[0];value.tofile(folder/'edges.bin')
        elif name in ['weight_nonfinite','weight_zero']:
            value=np.fromfile(folder/'edges.bin',[('index','<u4'),('weight','<f4')])
            value['weight'][0]=np.nan if name=='weight_nonfinite' else 0
            value.tofile(folder/'edges.bin')
        elif name == 'face_index':
            value=np.fromfile(folder/'faces.bin','<u4');value[0]=data.shape[0];value.tofile(folder/'faces.bin')
        elif name == 'frozen_flag':
            value=np.fromfile(folder/'frozen.bin','<u4');value[0]=2;value.tofile(folder/'frozen.bin')
        elif name == 'source_size':
            value=(folder/'original.bin').read_bytes();(folder/'original.bin').write_bytes(value[:-1])
        else:
            value=(folder/'config.txt').read_text().split();value[-1]='0';(folder/'config.txt').write_text(' '.join(value)+'\n')
        try:
            session.run('smooth',folder,folder/'points.f32',folder/'smooth.json')
        except RuntimeError as error:
            assert expected_error in str(error),(name,str(error))
            rejected.append(dict(case=name,error=str(error)))
        else:
            raise AssertionError('Invalid smoothing input reached accepted output: '+name)
        assert not (folder/'points.f32').exists() and not (folder/'smooth.json').exists()
    recovery = copied_inputs(tiny,work/'pool_recovery')
    restored = session.run('smooth',recovery,recovery/'points.f32',recovery/'smooth.json')
    assert restored['pool_allocations_this_call'] == 0 and restored['pool_reused_buffers_this_call'] == 11
    reference(recovery,restored)
    np.testing.assert_array_equal(np.fromfile(recovery/'points.f32','<u4'),np.fromfile(tiny/'points.f32','<u4'))
    return dict(capacity_grow_then_reuse_passed=True,same_shape_changed_data_then_original_passed=True,
        malformed_inputs_refused_before_DMA=rejected,all_FMA_outputs_and16_words_exact=True,
        all22_red_zones_retained=True,first_allocations=11,growth_allocations=10,growth_reuses=1,
        changed_data_allocations=0,changed_data_reuses=11,recovery_allocations=0,recovery_reuses=11,
        changed_data_reference=changed_reference,grown_capacity_bytes=grown['pool_capacity_bytes'])
