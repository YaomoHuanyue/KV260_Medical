"""Generate C8 with the exact frozen medical RP port signature."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
ports = json.loads((ROOT.parent/'medical/build/rp_ports.json').read_text(encoding='utf-8'))
actual = re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*;',
                    Path(sys.argv[1]).read_text(encoding='utf-8'), re.M)
canonical = lambda width: '' if width in ('', '[0:0]') else width
expected = {name: (direction, canonical(width)) for direction, width, name in ports
            if name in ('clk', 'resetn') or name.startswith(('control_', 'memory_'))}
observed = {name: (direction, canonical(width)) for direction, width, name in actual}
# HLS implements 0x00..0x44; retain the full 16-bit RP boundary and connect
# its low seven bits, as the accepted memory RMs do for their control maps.
for name in ('control_araddr', 'control_awaddr'):
    if observed.get(name) != ('input', '[6:0]'):
        raise RuntimeError('Unexpected composite control register width')
    observed[name] = ('input', '[15:0]')
if observed != expected:
    raise RuntimeError('Composite wrapper differs from the frozen memory/control boundary')
lines = ['module rm_medical(\n '+',\n '.join(f'{d} wire {w} {n}' for d,w,n in ports)+'\n);']
lines.append('algorithm_volume_wrapper algorithm('+','.join(
    f'.{n}({n}[6:0])' if n in ('control_araddr', 'control_awaddr') else f'.{n}({n})'
    for _,_,n in actual)+');')
lines.extend([
    'assign s_ready=m_ready;assign m_valid=s_valid;assign m_data=s_data;',
    'assign m_keep=s_keep;assign m_strb=s_strb;assign m_user=s_user;assign m_last=s_last;',
    "assign identity=8'hc8;\nendmodule"
])
(ROOT/'build/rm_medical.v').write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
(ROOT/'build/rp_ports.json').write_text(json.dumps(ports, indent=2)+'\n', encoding='utf-8', newline='\n')
