"""Match navigation AXIS kernels to the unchanged medical static boundary."""
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parent
variant="route"
assert variant in ('edt','route')
rp=json.loads((root.parent/'medical/build/rp_ports.json').read_text())
ports=re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*;',Path(sys.argv[1]).read_text(),re.M)
lines=['module rm_medical('+','.join(f'{d} wire {w} {n}' for d,w,n in rp)+');']
for d,w,n in rp:
    if d=='output' and n.startswith('memory_'):lines.append(f'assign {n}=0;')
mapping={};declared=set()
for d,w,n in ports:
    if n.startswith('stream_in_'):value='s_'+n.removeprefix('stream_in_t')
    elif n.startswith('stream_out_'):
        value=('core_' if variant=='route' else 'm_')+n.removeprefix('stream_out_t')
        if variant=='route' and value not in declared:
            lines.append(f'wire {w} {value};');declared.add(value)
    elif n in ('control_araddr','control_awaddr'):value=n+w
    else:value=n
    mapping[n]=value
lines.append(f'algorithm_{variant}_wrapper algorithm('+','.join(f'.{n}({v})' for n,v in mapping.items())+');')
if variant=='route':
    lines.append('route_pad padding(.clk(clk),.resetn(resetn),'+','.join(f'.s_{s}(core_{s})' for s in ('valid','ready','data','keep','strb','user','last'))+','+','.join(f'.m_{s}(m_{s})' for s in ('valid','ready','data','keep','strb','user','last'))+');')
lines.append(f"assign identity=8'h{'c3' if variant=='edt' else 'c4'};\nendmodule")
(root/'build/rm_medical.v').write_text('\n'.join(lines)+'\n')
