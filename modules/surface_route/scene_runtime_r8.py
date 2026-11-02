"""Revision-bound camera/guide/HUD dispatch for a complete scene snapshot.

No PL accesses here. C9/UI adapters can acquire a prepared immutable snapshot,
then exchange it atomically only on an explicit scene selection.
"""
from pathlib import Path
import json
import numpy as np
from .bundle_r8 import verify_bundle, arrays
from modules.navigation.navigation.camera import pose_at


class SceneSnapshot:
    def __init__(self, folder, expected_revision=None):
        self.folder = Path(folder).resolve()
        self.meta = verify_bundle(self.folder, expected_revision)
        self.revision = self.meta['revision']
        self.route = arrays(self.folder/'route.npz')
        self.camera = arrays(self.folder/'camera.npz')
        self.guidance = json.loads((self.folder/'guidance.json').read_text(encoding='utf-8'))
        self.report = json.loads((self.folder/'route.json').read_text(encoding='utf-8'))
        self.hud = json.loads((self.folder/'hud.json').read_text(encoding='utf-8'))
        # Payloads are read after verification, into one owned snapshot. No
        # per-frame filesystem reads or whole-volume hash/packing operations.
        self.scenes = {int(k): (self.folder/v['file']).read_bytes()
                       for k, v in self.meta['scenes'].items()}
        # Close the verify/read interval against changed packets.
        from .bundle_r8 import digest
        for k, blob in self.scenes.items():
            filename = self.meta['scenes'][str(k)]['file']
            if digest(blob) != self.meta['identity']['files_sha256'][filename]:
                raise ValueError('Scene changed during snapshot acquisition')

    def pose(self, arc_mm, yaw_degrees=0., pitch_degrees=0.):
        if not np.isfinite([arc_mm, yaw_degrees, pitch_degrees]).all():
            raise ValueError('Finite camera controls required')
        return pose_at(self.camera, self.route['arc_mm'], arc_mm, yaw_degrees, pitch_degrees)

    def frame_plan(self, request):
        if request.get('revision') != self.revision:
            raise ValueError('Frame request belongs to another scene revision')
        width, height, sequence = [request[k] for k in ('width', 'height', 'sequence')]
        if (any(type(v) is not int for v in (width, height, sequence))
                or not 16 <= width <= 640 or width % 16 or not 4 <= height <= 512
                or not 0 <= sequence <= 0x7fffffff):
            raise ValueError('Invalid C9 dimensions or frame sequence')
        arc = request['arc_mm']
        if (not isinstance(arc, (int, float)) or not np.isfinite(arc)
                or not 0 <= arc <= self.route['arc_mm'][-1]):
            raise ValueError('Frame outside the accepted physical route')
        if len(self.route['arc_mm']) < 2:
            raise ValueError('No navigable camera path')
        # The actual camera supplied by the UI includes manual yaw/pitch. Use
        # this same pose for rendering and the linked overview, never silently
        # replace it with the automatic-alignment pose.
        p, f, u = [np.asarray(request[k], dtype=float) for k in ('camera', 'forward', 'up')]
        if (any(v.shape != (3,) for v in (p, f, u))
                or not np.isfinite(np.r_[p, f, u]).all()
                or abs(np.linalg.norm(f)-1) > 1e-5 or abs(np.linalg.norm(u)-1) > 1e-5
                or abs(np.dot(f, u)) > 1e-5):
            raise ValueError('Finite orthonormal actual camera required')
        expected = self.pose(arc)
        if not np.allclose(p, expected['position_lps_mm'], rtol=0, atol=1e-4):
            raise ValueError('Camera position does not correspond to current route progress')
        eligible = [e for e in self.guidance['events'] if e['available']
                    and e['show_from_mm'] <= arc <= e['hide_after_mm']]
        # When intervals overlap, guide the next junction, not an already
        # passed one. Stable tie-break makes Windows and ARM deterministic.
        eligible.sort(key=lambda e: (e['junction_arc_mm'] < arc, abs(e['junction_arc_mm']-arc), e['id']))
        event = eligible[0]['id'] if eligible else -1
        point = min(int(np.searchsorted(self.route['arc_mm'], arc, side='left')),
                    len(self.route['arc_mm'])-1)
        return dict(revision=self.revision, branch_event=event, scene=self.scenes[event],
                    camera=p.tolist(), forward=f.tolist(), up=u.tolist(),
                    width=width, height=height, sequence=sequence, arc_mm=float(arc),
                    hud_point=point, hud=self.hud['samples'][point])


class LatestFrameQueue:
    """One inflight frame plus latest pending pose; stale results never publish."""
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.inflight = self.pending = None
        self.last_sequence = -1

    def submit(self, request):
        plan = self.snapshot.frame_plan(request)
        if plan['sequence'] <= self.last_sequence:
            raise ValueError('Nonincreasing frame sequence')
        self.last_sequence = plan['sequence']
        self.pending = plan

    def take(self):
        if self.inflight is not None or self.pending is None:
            return None
        self.inflight, self.pending = self.pending, None
        return self.inflight

    def finish(self, revision, sequence):
        if (self.inflight is None or revision != self.snapshot.revision
                or sequence != self.inflight['sequence']):
            raise ValueError('Completion does not match the inflight scene/frame')
        publish = sequence == self.last_sequence
        self.inflight = None
        return publish

    def replace(self, snapshot):
        if self.inflight is not None:
            raise RuntimeError('Drain the current frame before atomic scene replacement')
        self.snapshot, self.pending, self.last_sequence = snapshot, None, -1
