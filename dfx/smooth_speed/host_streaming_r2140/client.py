"""Nonblocking smoothing submission; explicitly qualified backend required.

One owner opens, runs and closes XRT. Callers retain their arrays unchanged
until the returned Future finishes, then dispatch display work to the GUI
thread. This module selects no firmware, loads no bitstream and supplies no
PS fallback. Sequential smoothing iterations keep their data dependencies.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'dfx/navigation_profile/host_streaming_r1180'))
from async_session import AsyncSession


def _run(session, inputs, output, report, nv, nf, nnz, limit, iterations):
    return session.run(inputs, output, report, nv, nf, nnz, limit, iterations)


class SmoothClient:
    """Bounded pending work raises queue.Full immediately when full.

    submit() and close() return Futures. Only queued work can be cancelled;
    accepted running work retains all buffers until the backend finishes.
    The supplied factory must enforce matching release and firmware gates.
    """
    def __init__(self, qualified_backend_factory, max_pending=2):
        if not callable(qualified_backend_factory):
            raise TypeError('Explicit qualified smoothing backend factory required')
        self._owner = AsyncSession(qualified_backend_factory, max_pending=max_pending)
        self._owner._thread.name = 'smoothing-streaming-owner'
        self.ready, self.closed = self._owner.ready, self._owner.closed

    def submit(self, inputs, output, report, nv, nf, nnz, limit, iterations):
        # Snapshot only the small container; do not copy, sample or change arrays.
        return self._owner.submit(_run, tuple(inputs), output, report,
                                  nv, nf, nnz, limit, iterations)

    def close(self):
        """Drain accepted work before backend restore/close; return immediately."""
        return self._owner.close()
