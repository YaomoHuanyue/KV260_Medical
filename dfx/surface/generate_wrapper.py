from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parent
ports=json.loads((root.parent/'medical/build/rp_ports.json').read_text())
actual=re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*;',Path(sys.argv[1]).read_text(),re.M)
lines=['module rm_medical('+','.join(f'{d} wire {w} {n}' for d,w,n in ports)+');']
for d,w,n in ports:
    if d=='output' and n.startswith('memory_'):lines.append(f'assign {n}=0;')
mapping=[]
for d,w,n in actual:
    if n.startswith('stream_in_'):value='s_'+n.removeprefix('stream_in_t')
    elif n.startswith('stream_out_'):value='m_'+n.removeprefix('stream_out_t')
    elif n in ('control_araddr','control_awaddr'):value=n+w
    else:value=n
    mapping.append(f'.{n}({value})')
lines.append('algorithm_scope_wrapper algorithm('+','.join(mapping)+');')
lines.append("assign identity=8'hc6;\nendmodule")
(root/'build/rm_medical.v').write_text('\n'.join(lines)+'\n')
