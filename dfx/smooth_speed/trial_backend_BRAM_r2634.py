"""CLI benchmark facade over the same bounded background XRT owner.

Only the benchmark harness waits for Futures. Application callbacks use
SmoothClient directly and return immediately. No alternate compute backend
or PS fallback is selected here.
"""
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/'host_streaming_r2140'))
from client import SmoothClient
import runtime_BRAM_r2634 as backend

verify=backend.verify


class Session:
    def __init__(self,profile=False):
        self.client=SmoothClient(lambda:backend.Session(profile=profile))

    def __enter__(self):
        self.client.ready.result()
        return self

    def run(self,*args):
        return self.client.submit(*args).result()

    def profile_snapshot(self):
        return self.client._owner.submit(lambda session:session.profile_snapshot()).result()

    def restore(self):
        return self.client._owner.submit(lambda session:session.restore()).result()

    def __exit__(self,*error):
        self.client.close().result()
