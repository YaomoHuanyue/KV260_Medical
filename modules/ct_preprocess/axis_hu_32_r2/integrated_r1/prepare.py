"""Select D6 once, process the entire HU volume, drain before opening C5.

Use the independently board-qualified 32-lane release. No PS quantization
or fallback is permitted in this entry.
"""
from pathlib import Path
import hashlib
import json
import os
import time
import numpy as np
import SimpleITK as sitk
from ct_pl.run import read_ct, prepare_grid, write_json
from modules.ct_preprocess.axis_hu_32_r2.quantization import model_table, MODEL
from modules.ct_preprocess.axis_hu_32_r2.host_r1.runtime import Session, quantize_volume


def prepare_ct(args):
    started = time.perf_counter()
    original = read_ct(args.input)
    phases = {'ct_read_seconds': time.perf_counter() - started}
    plan = json.loads((args.model_dir / 'graph.json').read_text())
    if args.model_dir.resolve() != MODEL.resolve() or 'preprocessing' not in plan:
        raise ValueError('This D6 entry requires the qualified physical-context model')
    t = time.perf_counter()
    image = prepare_grid(original)
    ct = sitk.GetArrayFromImage(image)
    if ct.dtype != np.int16 or ct.ndim != 3 or min(ct.shape) < 1 or max(ct.shape[1:]) > 512:
        raise ValueError('Nonempty int16 CT grid, at most 512x512 per slice required')
    phases['geometry_grid_seconds'] = time.perf_counter() - t
    table, metadata = model_table()
    write_json(args.output / 'status.json', dict(status='running',
        stage='PL_HU_preprocessing', backend='DFX_PL_HU_AXIS_D6', pid=os.getpid()))
    t = time.perf_counter()
    with Session() as session:
        quantized, metrics = quantize_volume(session, ct, table, chunk_voxels=1 << 23)
        metrics['open'] = session.open_metrics
    metrics['open_stream_and_drained_close_seconds'] = time.perf_counter() - t
    metrics['HU_quantization_backend'] = 'DFX_PL_HU_AXIS_D6'
    metrics['parallel_HU_lanes'] = 32
    metrics['input_word_loop_II'] = 1
    metrics['geometry_and_context_layout_backend'] = 'PS'
    metrics['quantized_SHA256'] = hashlib.sha256(quantized).hexdigest()
    metrics['model'] = metadata
    metrics['source_shape_zyx'] = list(ct.shape)
    metrics['no_PS_quantization_or_fallback'] = True
    metrics['D6_drained_closed_and_isolated_before_C5_open'] = True
    quantized.flags.writeable = False
    phases['PL_HU_preprocessing_seconds'] = metrics['open_stream_and_drained_close_seconds']
    write_json(args.output / 'preprocessing.json', metrics)
    return dict(started=started, original=original, image=image, ct=ct,
                phases=phases, quantized=quantized, metadata=metadata, metrics=metrics)
