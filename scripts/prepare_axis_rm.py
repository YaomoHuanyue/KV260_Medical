"""Reuse the accepted MC/HU port generator with output confined to this checkout."""
from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('target',choices=['mc','hu32']);a=p.parse_args();targets=json.loads((ROOT/'hardware/hls_targets.json').read_bytes());t=targets[a.target]
 source=ROOT/t['source'];generator=source.parent/'generate_rm.py';code=generator.read_text(encoding='utf8')
 code=code.replace('assert out.is_relative_to(HERE) and not out.exists()','assert out.is_relative_to(ROOT) and not out.exists()')
 boundary=ROOT/'dfx/medical/build/rp_ports.json';boundary.parent.mkdir(parents=True,exist_ok=True);boundary.write_bytes((ROOT/'hardware/static/rp_ports.json').read_bytes())
 namespace={'__file__':str(generator),'__name__':'_git_axis_generator'};exec(compile(code,str(generator),'exec'),namespace)
 hls=ROOT/'build/hls'/a.target/'hls/syn/verilog'/(t['top']+'.v');assert hls.is_file(),'Run HLS csynth first'
 out=ROOT/'build/rm'/a.target/'binding';out.parent.mkdir(parents=True,exist_ok=True);namespace['generate'](hls,out)
if __name__=='__main__':main()
