"""Wrap the complete candidate BD with the unchanged frozen DFX RP ports."""
from pathlib import Path
import json,re,sys
rp_path,wrapper_path,output_path=map(Path,sys.argv[1:])
rp=json.loads(rp_path.read_text())
ports=re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*;',wrapper_path.read_text(),re.M)
lookup={name:(direction,width) for direction,width,name in rp}
norm=lambda width:'' if width=='[0:0]' else width
for direction,width,name in ports:
    if name in ('control_arprot','control_awprot'):
        assert direction=='input' and width=='[2:0]';continue
    assert name in lookup,name
    expected=lookup[name]
    assert expected[0]==direction and (name in ('control_araddr','control_awaddr') or norm(expected[1])==norm(width)),(name,expected,(direction,width))
body='module rm_medical('+','.join(f'{direction} wire {width} {name}' for direction,width,name in rp)+');\n'
connections=[]
for direction,width,name in ports:
    value="3'b000" if name in ('control_arprot','control_awprot') else name+(width if name in ('control_araddr','control_awaddr') else '')
    connections.append(f'.{name}({value})')
body+='a_wrapper algorithm('+','.join(connections)+');\n'
for direction,width,name in rp:
    if direction=='output' and name.startswith('memory_') and name not in {port[2] for port in ports}:body+=f'assign {name}=0;\n'
body+='assign s_ready=m_ready;assign m_valid=s_valid;assign m_data=s_data;assign m_keep=s_keep;assign m_strb=s_strb;assign m_user=s_user;assign m_last=s_last;\n'
body+="assign identity=8'hc5;\nendmodule\n"
assert not output_path.exists();output_path.write_text(body,encoding='ascii')
