"""在气道外包框内执行原始清理算法，结果与整幅计算逐体素一致。

原始算法 clean_mask（mixed_r30/reference/original_clean_airway_tree.py，SHA 校验后原样执行）：
  1 保留最大 26 连通域 → 2 闭运算（6 邻域，1 次，边界视为 0）→ 3 再保留最大连通域
  → 4 填洞（与体数据边界 6 连通的背景之外全部填充）→ 5 再保留最大连通域。
等价性：
  * 第 1 步只在全部前景的外包框内标记。框外全为 0，连通域集合、体素数和光栅扫描顺序都与整幅相同（argmax 平局时选同一个）。
  * 之后只依赖最大连通域 M。闭运算结果距 M 不超过 1 个体素（L1），因此取 M 外包框外扩 MARGIN≥2 后，框边界一层全为背景；
    框外背景都能沿某一坐标轴直线走到体数据边界而不进入框，所以“与边界连通的背景”在框内外判定一致，填洞结果相同；
    框被体数据边界截断时，截断面就是体数据边界，语义相同。
  * info 中的输入体素数、连通域数取自整幅输入，其余与原函数相同。"""
import numpy as np

MARGIN = 3


def _bbox(mask):
    zs = np.flatnonzero(mask.any(axis=(1, 2)))
    ys = np.flatnonzero(mask.any(axis=(0, 2)))
    xs = np.flatnonzero(mask.any(axis=(0, 1)))
    return (zs[0], zs[-1] + 1, ys[0], ys[-1] + 1, xs[0], xs[-1] + 1)


def clean_mask_bbox(mask, functions, closing_iterations=1):
    """mask: 整幅 bool 数组；functions: 原始算法命名空间（含 keep_largest_component 和 clean_mask）。"""
    if closing_iterations != 1:
        raise ValueError('Exact bounding-box margin is proven for one closing iteration only')
    before = int(mask.sum())
    if before == 0:
        return functions['clean_mask'](mask, closing_iterations)  # 原函数给出相同的空掩膜错误
    z0, z1, y0, y1, x0, x1 = _bbox(mask)
    sub = mask[z0:z1, y0:y1, x0:x1]
    main_sub, count, _, _ = functions['keep_largest_component'](sub)
    a0, a1, b0, b1, c0, c1 = _bbox(main_sub)
    a0 += z0; a1 += z0; b0 += y0; b1 += y0; c0 += x0; c1 += x0
    shape = mask.shape
    box = (max(0, a0 - MARGIN), min(shape[0], a1 + MARGIN), max(0, b0 - MARGIN), min(shape[1], b1 + MARGIN),
           max(0, c0 - MARGIN), min(shape[2], c1 + MARGIN))
    crop = np.zeros((box[1] - box[0], box[3] - box[2], box[5] - box[4]), dtype=bool)
    crop[a0 - box[0]:a1 - box[0], b0 - box[2]:b1 - box[2], c0 - box[4]:c1 - box[4]] = \
        main_sub[a0 - z0:a1 - z0, b0 - y0:b1 - y0, c0 - x0:c1 - x0]
    cleaned_crop, inner = functions['clean_mask'](crop, closing_iterations)
    cleaned = np.zeros(shape, dtype=np.uint8)
    cleaned[box[0]:box[1], box[2]:box[3], box[4]:box[5]] = cleaned_crop
    largest = int(inner['largest_component_voxels'])
    info = {
        "input_foreground_voxels": before,
        "input_connected_components": int(count),
        "largest_component_voxels": largest,
        "retained_fraction": float(largest / max(before, 1)),
        "closing_iterations": int(closing_iterations),
    }
    return cleaned, info, dict(box_zyx=[int(v) for v in box], box_voxels=int(crop.size), full_voxels=int(mask.size))
