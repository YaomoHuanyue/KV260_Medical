"""Bind only an already loaded AXIS4 design, using its combined XCLBIN."""
from pathlib import Path
import fcntl
import hashlib
import json
import subprocess
import tempfile
import numpy as np
from .mc_host import validate_mask


class XRTAccelerator:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.xclbin = self.root/'fpga/render_axis/package/medical_axis4.xclbin'
        self.executable = self.root/'fpga/build/mc_xrt'

    def reconstruct(self, mask):
        mask = validate_mask(mask)
        folder = self.root/'outputs/xrt'
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/'.hardware.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            firmware = Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
            loaded=firmware.read_bytes().rstrip(b'\0')
            if loaded==b'kv260_mc_smooth.bit.bin':
                package=self.root/'fpga/smooth/package'
                manifest=json.loads((package/'manifest.json').read_text())
                self.xclbin=package/'kv260_mc_smooth.xclbin'
                expected=manifest['xclbin_sha256']
                if Path('/run/kv260-mc-loaded.sha256').read_text().strip()!=manifest['bit_bin_sha256']:
                    raise RuntimeError('MC smoothing firmware hash mismatch')
            elif loaded==b'medical_axis4.bit.bin':
                self.xclbin=self.root/'fpga/render_axis/package/medical_axis4.xclbin'
                expected='73e1f912f7c9d9097b467157f1894a74139c64b7acab146eefbbc95c40b8cfb7'
            else:raise RuntimeError('MC firmware is not loaded; no PL registers accessed')
            if hashlib.sha256(self.xclbin.read_bytes()).hexdigest()!=expected:
                raise ValueError('Unverified reconstruction metadata')
            with tempfile.TemporaryDirectory(prefix='.mesh-', dir=folder) as work:
                work = Path(work)
                mask.tofile(work/'mask.u8')
                # No timeout/kill: the native host retains DMA BOs on PL timeout.
                subprocess.run([str(self.executable), str(self.xclbin),
                    str(work/'mask.u8'), *map(str, mask.shape[::-1]),
                    str(work/'vertices.u64'), str(work/'report.json')],
                    check=True, cwd=self.root)
                return np.fromfile(work/'vertices.u64', dtype='<u8'), json.loads(
                    (work/'report.json').read_text())
