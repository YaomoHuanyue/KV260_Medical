"""Wire the real algorithm AXIS to the exact frozen67-pin DFX boundary.

Identity D9 is a new ABI: old C2 hosts must refuse this streamed core. This
generator never claims synthesis, PR compatibility, or board qualification.
"""
from pathlib import Path
import argparse,hashlib,json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
FROZEN=ROOT/'dfx/medical/build/rp_ports.json'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def declarations(text):
    return [(d,re.sub(r'\s+','',w or ''),n) for d,w,n in re.findall(
        r'^\s*(input|output)\s+(?:wire\s+)?(\[[^\]]+\])?\s*(\w+)\s*(?:[,;]|\))',text,re.M)]
def bits(width):
    if not width:return 1
    m=re.fullmatch(r'\[(\d+):(\d+)\]',width);assert m,'Nonconstant boundary width'
    return abs(int(m[1])-int(m[2]))+1
def generate(bd_text,module_name):
    assert re.fullmatch(r'[A-Za-z_]\w*',module_name)
    ports=declarations(bd_text);assert len(ports)==len({p[2] for p in ports})
    frozen=[tuple(x) for x in json.loads(FROZEN.read_text())];assert len(frozen)==67
    original={n:(d,w) for d,w,n in frozen}
    mapped={};internal_widths={}
    for direction,width,name in ports:
        lowered=name.lower();match=re.fullmatch(r'([sm])_t(data|keep|strb|user|last|valid|ready)',lowered)
        target=match[1]+'_'+match[2] if match else name
        assert target in original and target!='identity',('Unexpected BD pin',name)
        assert target not in mapped,('Ambiguous BD pin',name)
        expected_direction,expected_width=original[target]
        assert direction==expected_direction,('Pin direction mismatch',name)
        if target in ('control_araddr','control_awaddr'):
            assert bits(expected_width)==16 and bits(width) in (8,16),('Unsupported internal AXIL width',name,width)
        else:assert bits(width)==bits(expected_width),('Pin width mismatch',name,width,original[target])
        internal_widths[target]=bits(width)
        mapped[target]=name
    assert set(mapped)==set(original)-{'identity'},('Missing exact RP pins',set(original)-{'identity'}-set(mapped))
    control=[(d,w,n) for d,w,n in frozen if n.startswith('control_')];assert len(control)==17
    body='module rm_medical #(parameter ENABLE_DIAGNOSTICS=1)(\n '+',\n '.join(f'{d} wire {w} {n}' for d,w,n in frozen)+'\n);\n'
    body+='\n'.join(f'wire {w} kernel_{n};' for d,w,n in control)+'\n'
    connections=[]
    for target,source in mapped.items():
        signal='kernel_'+target if target.startswith('control_') else target
        if target in ('control_araddr','control_awaddr') and internal_widths[target]==8:signal+='[7:0]'
        connections.append('.'+source+'('+signal+')')
    body+=module_name+' algorithm('+','.join(connections)+');\n'
    links=['.clk(clk)','.resetn(resetn)']
    for d,w,n in control:
        field=n[len('control_'):];links.extend([f'.s_{field}({n})',f'.m_{field}(kernel_{n})'])
    for n in ['arvalid','arready','arlen','arsize','rvalid','rready','rlast','rresp','awvalid','awready',
              'awlen','awsize','wvalid','wready','wstrb','bvalid','bready','bresp']:links.append(f'.memory_{n}(memory_{n})')
    body+='optional_profile_r332 #(.ENABLE_DIAGNOSTICS(ENABLE_DIAGNOSTICS)) diagnostics('+','.join(links)+');\n'
    body+="assign identity=8'hd9;\nendmodule\n"
    assert declarations(body)==frozen
    assert 'assign s_ready=m_ready' not in body and 'assign m_data=s_data' not in body
    return body,mapped

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bd_wrapper',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    body,mapping=generate(a.bd_wrapper.read_text(),a.bd_wrapper.stem)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists():assert a.output.read_text()==body
    else:a.output.write_text(body,encoding='utf-8',newline='\n')
    receipt=dict(schema='kv260.smoothing.real_AXIS_DFX_boundary.v1',boundary_pin_count=67,
        boundary_and17_control_fields_preserved=True,identity=0xd9,streamed_ABI_version=12,
        actual_algorithm_input_output_AXIS_wired=True,no_loopback_passthrough=True,
        port_mapping=mapping,bd_wrapper_SHA256=sha(a.bd_wrapper),frozen_boundary_SHA256=sha(FROZEN),
        generated_SHA256=sha(a.output),generator_SHA256=sha(Path(__file__)),
        external_control_address_bits=16,explicit_internal_address_slice_supported=True,
        synthesis_full14RTL_route_PR_and_board_not_yet_qualified=True,production_promoted=False)
    target=a.output.with_suffix('.json')
    if target.exists():assert json.loads(target.read_text())==receipt
    else:target.write_text(json.dumps(receipt,indent=2)+'\n')
    print('Exact67-pin DFX wrapper generated; real algorithm AXIS wired; not qualified')
