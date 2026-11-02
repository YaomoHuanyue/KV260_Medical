"""Verify the actual enabled PL clock before any compute-unit access."""
import json
import sys
from pathlib import Path


def main():
    package=Path(sys.argv[1])
    manifest=json.loads((package/'manifest.json').read_text())
    rows=[line.split() for line in Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()]
    clocks=[row for row in rows if row and row[0]=='pl0_ref']
    assert len(clocks)==1,clocks
    clock=clocks[0];rate=int(clock[4])
    assert int(clock[1])>0 and int(clock[2])>0 and abs(rate-manifest['clock_hz'])<=100,(clock,manifest['clock_hz'])
    record=dict(status='passed',kind='actual_kv260',nominal_hz=manifest['clock_hz'],actual_hz=rate,
                enable_count=int(clock[1]),prepare_count=int(clock[2]),bit_sha256=manifest['bit_sha256'])
    if manifest.get('route_core')=='nav_route.v1':
        Path('docs/pl_route_clock_validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Verified enabled PL0 clock:',rate,'Hz')


if __name__=='__main__':main()
