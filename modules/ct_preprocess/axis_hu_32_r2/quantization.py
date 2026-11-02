"""Small model LUT configuration; this is not bulk CT preprocessing on PS."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / 'modules/segmentation/outputs/ct_accuracy_v2/pl_model'


def model_table():
    plan = json.loads((MODEL / 'graph.json').read_text())
    node = next(n for n in plan['nodes']
                if n['op'] == 'QuantizeLinear' and n['inputs'][0] == plan['input'])
    with np.load(MODEL / 'tensors.npz', allow_pickle=False) as arrays:
        scale, zero = [arrays[name] for name in node['inputs'][1:]]
    if (scale.size != 1 or zero.size != 1 or scale.dtype != np.float32 or
            zero.dtype != np.int8 or not np.isfinite(scale).all() or scale.item() <= 0):
        raise ValueError('Scalar positive float32 scale and int8 zero point required')
    hu = np.arange(-1000, 401, dtype=np.int16)
    # Preserve the released model's float32 operations and nearest-even rounding.
    normalized = (hu.astype(np.float32) + 1000) / 1400
    table = np.clip(np.rint(normalized / scale) + zero, -128, 127).astype(np.int8)
    metadata = dict(scale=float(scale.item()), zero=int(zero.item()),
                    table_SHA256=hashlib.sha256(table.tobytes()).hexdigest(),
                    model_SHA256={name: hashlib.sha256((MODEL / name).read_bytes()).hexdigest()
                                  for name in ['graph.json', 'tensors.npz']})
    return table, metadata
