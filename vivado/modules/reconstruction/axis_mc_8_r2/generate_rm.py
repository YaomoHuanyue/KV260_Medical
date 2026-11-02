"""Connect actual algorithm AXIS ports to the existing 67-port DFX boundary."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(top,out):
    top=Path(top).resolve();out=Path(out).resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    boundary=ROOT/'dfx/medical/build/rp_ports.json'
    ports=json.loads(boundary.read_text());assert len(ports)==67
    known={n:(d,w) for d,w,n in ports};assert len(known)==67
    text=top.read_text();parameters={}

    def constant(expression):
        def value(n):
            if isinstance(n,ast.Constant) and type(n.value) is int:return n.value
            if isinstance(n,ast.Name):return parameters[n.id]
            if isinstance(n,ast.BinOp):
                a,b=value(n.left),value(n.right)
                if isinstance(n.op,ast.Add):return a+b
                if isinstance(n.op,ast.Sub):return a-b
                if isinstance(n.op,ast.Mult):return a*b
                if isinstance(n.op,ast.Div) and b and a%b==0:return a//b
            raise ValueError('Unsupported HLS width: '+expression)
        return value(ast.parse(expression.strip(),mode='eval').body)

    def width(w):return int(re.search(r'\d+',w).group())+1 if w else 1

    for name,expr in re.findall(r'^parameter\s+(C_\w+)\s*=\s*([^;]+);',text,re.M):
        assert name not in parameters;parameters[name]=constant(expr)
    actual=[]
    for d,w,n in re.findall(r'^\s*(input|output)\s*(?:wire\s*)?(\[[^\]]+\])?\s*(\w+)\s*;',text,re.M):
        if w:
            hi,lo=map(constant,w[1:-1].split(':'));assert lo==0 and hi>=0;w=f'[{hi}:0]'
        actual.append((d,w,n))
    header=re.search(r'\bmodule\s+binary_mc_axis\s*\((.*?)\);',text,re.S).group(1)
    assert {p[2] for p in actual}==set(re.findall(r'\b\w+\b',header))
    mapping={};wired={'clk','resetn','identity'};idle={}
    lines=['module rm_medical(\n '+',\n '.join(f'{d} wire {w} {n}' for d,w,n in ports)+'\n);',
           "assign identity=8'hd7;"]
    for d,w,n in actual:
        if n in ('ap_clk','ap_rst_n'):connection='clk' if n=='ap_clk' else 'resetn'
        elif n=='interrupt':assert d=='output';connection=''
        elif n.startswith(('input_r_T','output_r_T')):
            connection=('s' if n.startswith('input_r_') else 'm')+'_'+n.split('_T')[-1].lower()
            assert known[connection][0]==d and width(known[connection][1])==width(w)
            wired.add(connection)
        elif n.startswith('s_axi_control_'):
            connection='control_'+n[len('s_axi_control_'):].lower();assert known[connection][0]==d
            wired.add(connection)
            if connection.endswith(('awaddr','araddr')):
                assert d=='input' and width(w)<=16;connection+=f'[{width(w)-1}:0]'
            else:assert width(known[connection][1])==width(w)
        else:raise ValueError('Unexpected actual MC HLS port: '+n)
        mapping[n]=connection
    for d,w,n in ports:
        if n.startswith('memory_'):
            assert n not in wired
            if d=='output':
                idle[n]=f"{width(w)}'d0";lines.append(f'assign {n}={idle[n]};')
            wired.add(n)
    assert wired==set(known),sorted(set(known)-wired)
    assert len(mapping)==len(actual)
    bits=[]
    directions={}
    for d,w,n in ports:
        names=[n] if not w else [f'{n}[{i}]' for i in range(width(w))]
        bits+=names;directions.update({b:'IN' if d=='input' else 'OUT' for b in names})
    assert len(bits)==1830
    lines.append('binary_mc_axis algorithm(\n '+',\n '.join(f'.{n}({v})' for n,v in mapping.items())+'\n);\nendmodule\n')
    out.mkdir()
    (out/'rm_medical.v').write_text('\n'.join(lines))
    (out/'clock.xdc').write_text('create_clock -period 10.000 -name clk [get_ports clk]\n')
    (out/'rp_port_bits.txt').write_text('\n'.join(sorted(bits))+'\n')
    (out/'rp_port_directions.txt').write_text('\n'.join(f'{n} {directions[n]}' for n in sorted(bits))+'\n')
    proof=dict(schema='kv260.mc_AXIS.DFX_boundary.v1',identity=0xd7,
        RP_declarations=67,RP_bits=1830,boundary_SHA256=sha(boundary),
        generated_HLS_top=top.relative_to(ROOT).as_posix(),HLS_top_SHA256=sha(top),
        generator_SHA256=sha(__file__),wrapper_SHA256=sha(out/'rm_medical.v'),
        port_map=mapping,idle_memory_outputs=idle,no_bulk_AXI_MM=True,
        no_AXIS_passthrough=True,data_AXIS_512=True,new_static_shell_required=False,
        actual_RM_synthesis_passed=False,full_PR_passed=False,PL_accessed=False,production_promoted=False)
    (out/'boundary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('top',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();print(json.dumps(generate(a.top,a.out),indent=2))
