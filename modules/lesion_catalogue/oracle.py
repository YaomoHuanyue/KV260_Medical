"""Exact extracted original component_report; tests only, no inference."""
import numpy as np
import SimpleITK as sitk

def component_report(mask: np.ndarray, ref: sitk.Image, min_volume_mm3: float) -> tuple[np.ndarray, list[dict]]:
    # Build a binary SimpleITK image with the same physical geometry as the CT.
    binary_img = sitk.GetImageFromArray(mask.astype(np.uint8))
    binary_img.CopyInformation(ref)

    # Use the object-oriented API instead of the procedural keyword form.
    # Some SimpleITK Python builds do not accept `fullyConnected=` as a keyword
    # for the overloaded ConnectedComponent() wrapper.
    cc_filter = sitk.ConnectedComponentImageFilter()
    cc_filter.SetFullyConnected(True)
    cc = cc_filter.Execute(binary_img)

    stats = sitk.LabelShapeStatisticsImageFilter()
    stats.Execute(cc)

    labels = []
    for lab in stats.GetLabels():
        vol = float(stats.GetPhysicalSize(lab))
        if vol < min_volume_mm3:
            continue
        centroid = tuple(float(v) for v in stats.GetCentroid(lab))
        bbox = tuple(int(v) for v in stats.GetBoundingBox(lab))  # x,y,z,sx,sy,sz
        labels.append((lab, vol, centroid, bbox))

    labels.sort(key=lambda x: x[1], reverse=True)
    cc_arr = sitk.GetArrayFromImage(cc)
    out_labels = np.zeros_like(cc_arr, dtype=np.uint16)
    report = []
    for new_id, (lab, vol, centroid, bbox) in enumerate(labels, start=1):
        out_labels[cc_arr == lab] = new_id
        eq_diam = float((6.0 * vol / np.pi) ** (1.0 / 3.0))
        report.append({
            'id': new_id,
            'volume_mm3': vol,
            'equivalent_sphere_diameter_mm': eq_diam,
            'centroid_xyz_mm': [float(v) for v in centroid],
            'bbox_xyz_size': [int(v) for v in bbox],
        })
    return out_labels, report
