"""Candidate entry point; all medical computation uses the original dispatcher."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent)]
from modules.view_assets_r1.backend_optimized import namespace
from reuse_r2 import Reuse


def main():
    state=namespace()
    import backend_core_r6 as backend
    import backend_selected_r1 as accepted
    backend.prepare=Reuse(state).prepare
    return accepted.main()


if __name__=='__main__':
    main()
