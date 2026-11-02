"""Verify a prepared complete scene before native Qt activates its payload."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.ui_bridge_r9 import verify_prepared
from modules.surface_route.bundle_r8 import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True)
    p.add_argument('--input',type=Path,required=True);a=p.parse_args()
    scene=verify_prepared(a.scene)
    if sha(a.input)!=scene['input_sha256'] or a.input.resolve()!=Path(scene['input']).resolve():
        raise ValueError('Native selected CT and complete scene differ')
    print(json.dumps(dict(event='prepared',scene=str(a.scene.resolve()),
        revision=scene['complete_surface']['revision'],PL_access=False)),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error))),flush=True);raise
