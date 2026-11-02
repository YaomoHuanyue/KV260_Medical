"""Packed-mask capability fields, including empty and reserved-bit cases."""
from pathlib import Path
import argparse,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.capabilities_r14c import capabilities
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    tests=[]
    for name,mask,expected in [('empty',np.zeros(9,np.uint8),([],dict(lung=0,airway=0,nodule=0))),
        ('reserved_probability_bits',np.array([8,16,24,32,128],np.uint8),([],dict(lung=0,airway=0,nodule=0))),
        ('overlapping_structures',np.array([1,2,4,7,10,20],np.uint8),(['lung','airway','nodule'],dict(lung=2,airway=3,nodule=3)))]:
        assert capabilities(mask)==expected,name;tests.append(name)
    for name,mask in [('wrong_type',np.zeros(8,np.int8)),('wrong_shape',np.zeros((2,4),np.uint8))]:
        try:capabilities(mask)
        except ValueError:tests.append(name)
        else:raise AssertionError(name)
    write_json(a.output,dict(status='packed_scene_capabilities_empty_reserved_overlap_and_type_checked',tests=tests,
        source_sha256={n:sha(ROOT/n) for n in ('modules/surface_route/capabilities_r14c.py','modules/surface_route/test_capabilities_r14c.py')},PL_access=False))
    print('Capability tests passed',len(tests),flush=True)


if __name__=='__main__':main()
