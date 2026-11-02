"""Generate explicit scalar RP boundaries from validated Vivado BD wrappers."""
import json,re,sys,os
from pathlib import Path
root=Path(__file__).resolve().parent
out=Path(os.environ['KV260_STATIC_BUILD'])
def ports(path):
    text=Path(path).read_text()
    found=re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*;',text,re.M)
    if not found:raise ValueError('No wrapper ports')
    return [(d,w or '',n) for d,w,n in found]
def declaration(items):return ',\n '.join(f'{d} wire {w} {n}' for d,w,n in items)
axis=[('input','','s_valid'),('output','','s_ready'),('input','[511:0]','s_data'),('input','[63:0]','s_keep'),('input','[63:0]','s_strb'),('input','','s_user'),('input','','s_last'),('output','','m_valid'),('input','','m_ready'),('output','[511:0]','m_data'),('output','[63:0]','m_keep'),('output','[63:0]','m_strb'),('output','','m_user'),('output','','m_last'),('output','[7:0]','identity')]
if sys.argv[1]=='rm':
    variant=sys.argv[2];p=ports(sys.argv[3])
    boundary=[(d,'[15:0]' if n in ('control_araddr','control_awaddr') else w,n) for d,w,n in p]
    allports=boundary+axis
    signature=root/'rp_ports.json'
    if signature.exists():assert json.loads(signature.read_text())==[list(v) for v in allports],'RM port mismatch'
    else:signature.write_text(json.dumps(allports,indent=2))
    body=f'module rm_medical(\n {declaration(allports)}\n);\n'
    body+=f'algorithm_{variant}_wrapper algorithm('+','.join(f'.{n}({n}{w if n in ("control_araddr","control_awaddr") else ""})' for _,w,n in p)+');\n'
    body+="assign s_ready=m_ready;assign m_valid=s_valid;assign m_data=s_data;assign m_keep=s_keep;assign m_strb=s_strb;assign m_user=s_user;assign m_last=s_last;\n"
    body+=f"assign identity=8'h{'c1' if variant=='mc' else 'c2'};\nendmodule\n"
    (root/f'build/{variant}/rm_medical.v').write_text(body)
    (root/'build/rm_stub.v').write_text('(* black_box *) module rm_medical(\n '+declaration(allports)+'\n);endmodule\n')
elif sys.argv[1]=='static':
    p=ports(sys.argv[2]);rp=json.loads((root/'rp_ports.json').read_text())
    wires={n:w for _,w,n in p}
    for _,w,n in rp:
        if n.startswith(('control_','memory_')):
            def canonical(v):return '' if v=='[0:0]' else v
            assert canonical(wires.get(n))==canonical(w),(n,w,wires.get(n))
    lines=['module system_top();']+[f'wire {w} {n};' for _,w,n in p]
    lines+=['wire [7:0] identity;wire rm_resetn,isolated,axis_busy;wire rm_s_ready,rm_m_valid;',
     'wire [15:0] transactions;',
     'medical_guard guard(.clk(clk),.resetn(resetn),.cfg(cfg),.control_shutdown(control_shutdown),.memory_shutdown(memory_shutdown),',
     ' .tx_valid(tx_tvalid),.tx_ready(tx_tready),.rx_valid(rx_tvalid),.rx_ready(rx_tready),.rx_last(rx_tlast),',
     ' .isolated(isolated),.busy(axis_busy),.transactions(transactions),.rm_resetn(rm_resetn));',
     'assign shutdown_request=cfg[0];',
     'assign status={transactions,(isolated?8\'h00:identity),4\'b0,memory_shutdown,control_shutdown,axis_busy,isolated};',
     'assign tx_tready=rm_s_ready&&!isolated;assign rx_tvalid=rm_m_valid&&!isolated;']
    # Some standard AXI sidebands are absent in HLS/SmartConnect's fixed boundary.
    names={n for _,_,n in rp}
    for d,w,n in p:
        if n.startswith(('control_','memory_')) and n not in names and n not in ('control_shutdown','memory_shutdown'):
            if d=='input':lines.append(f'assign {n}=0;')
    lines.append('system_ps_wrapper platform('+','.join(f'.{n}({n})' for _,_,n in p)+');')
    mapping={'resetn':'rm_resetn','s_valid':'tx_tvalid&&!isolated','s_ready':'rm_s_ready','m_valid':'rm_m_valid','m_ready':'rx_tready&&!isolated'}
    for side,prefix in [('s','tx'),('m','rx')]:
        for suffix in ('data','keep','strb','user','last'):mapping[f'{side}_{suffix}']=f'{prefix}_t{suffix}'
    lines.append('(* DONT_TOUCH="yes" *) rm_medical rp('+','.join(f'.{n}({mapping.get(n,n)})' for _,_,n in rp)+');')
    lines.append('endmodule')
    (out/'system_top.v').write_text('\n'.join(lines)+'\n')
