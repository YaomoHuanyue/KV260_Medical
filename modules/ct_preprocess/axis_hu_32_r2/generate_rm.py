"""Bind the real synthesized HLS ports to the unchanged medical DFX boundary.

No new top-level debug signals and no stream passthrough are added. Generation
does not prove full PR compatibility; that still requires actual Vivado checks.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(top, out):
    top = Path(top).resolve()
    out = Path(out).resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    boundary_file = ROOT / 'dfx/medical/build/rp_ports.json'
    ports = json.loads(boundary_file.read_text())
    assert len(ports) == 67 and len({p[2] for p in ports}) == 67
    text = top.read_text()
    assert re.search(r'\bmodule\s+ct_hu_axis\b', text)
    parameters = {}

    def constant(expr):
        node = ast.parse(expr.strip(), mode='eval').body

        def value(n):
            if isinstance(n, ast.Constant) and type(n.value) is int:
                return n.value
            if isinstance(n, ast.Name):
                return parameters[n.id]
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                left, right = value(n.left), value(n.right)
                if isinstance(n.op, ast.Add): return left + right
                if isinstance(n.op, ast.Sub): return left - right
                if isinstance(n.op, ast.Mult): return left * right
                assert right and left % right == 0
                return left // right
            raise ValueError('Unsupported HLS constant expression: ' + expr)

        return value(node)

    for name, expr in re.findall(r'^parameter\s+(C_\w+)\s*=\s*([^;]+);', text, re.M):
        assert name not in parameters
        parameters[name] = constant(expr)
    raw = re.findall(r'^\s*(input|output)\s*(?:wire\s*)?(\[[^\]]+\])?\s*(\w+)\s*;', text, re.M)
    generated = []
    for d, w, n in raw:
        if w:
            hi, lo = map(constant, w[1:-1].split(':'))
            assert lo == 0 and hi >= 0
            w = f'[{hi}:0]'
        generated.append((d, w, n))
    header = re.search(r'\bmodule\s+ct_hu_axis\s*\((.*?)\);', text, re.S).group(1)
    assert set(re.findall(r'\b\w+\b', header)) == {p[2] for p in generated}
    assert generated and len({p[2] for p in generated}) == len(generated)
    known = {n: (d, w) for d, w, n in ports}
    lines = ['module rm_medical(\n ' + ',\n '.join(f'{d} wire {w} {n}' for d, w, n in ports) + '\n);',
             "assign identity=8'hd6;"]
    mapping = {}
    tied = {}
    wired = set()

    def width(spec):
        return int(re.search(r'\d+', spec).group()) + 1 if spec else 1

    for direction, w, name in generated:
        if name in ('ap_clk', 'ap_rst_n'):
            connection = 'clk' if name == 'ap_clk' else 'resetn'
        elif name == 'interrupt':
            assert direction == 'output'
            connection = ''
        elif name.startswith(('input_r_T', 'output_r_T')):
            prefix = 's' if name.startswith('input_r_') else 'm'
            suffix = name.split('_T')[-1].lower()
            connection = prefix + '_' + suffix
            assert known[connection][0] == direction and width(known[connection][1]) == width(w)
            wired.add(connection)
        elif name.startswith('s_axi_control_'):
            connection = 'control_' + name[len('s_axi_control_'):].lower()
            assert known[connection][0] == direction
            if connection.endswith(('araddr', 'awaddr')):
                assert width(w) <= 16 and direction == 'input'
                connection += f'[{width(w)-1}:0]'
            else:
                assert width(known[connection][1]) == width(w)
            wired.add(connection.split('[')[0])
        elif name.startswith('m_axi_memory_'):
            suffix = name[len('m_axi_memory_'):].lower()
            connection = 'memory_' + suffix
            if connection in known:
                assert known[connection][0] == direction
                expected_width = width(known[connection][1])
                if expected_width != width(w):
                    assert direction == 'output' and suffix in ('araddr', 'awaddr', 'arlock', 'awlock')
                    assert width(w) >= expected_width
                    connection = 'core_' + suffix
                    lines.append(f'wire {w} {connection};')
                    lines.append(f'assign memory_{suffix}={connection}[{expected_width-1}:0];')
                wired.add('memory_' + suffix)
            else:
                assert suffix in ('arid', 'aruser', 'arregion', 'awid', 'awuser', 'awregion',
                                  'wid', 'wuser', 'bid', 'buser', 'rid', 'ruser'), name
                connection = '' if direction == 'output' else f"{width(w)}'d0"
                tied[name] = connection
        else:
            raise ValueError('Unexpected actual HLS port: ' + name)
        mapping[name] = connection
    assert wired == set(known) - {'clk', 'resetn', 'identity'}, sorted(set(known)-wired)
    lines.append('ct_hu_axis algorithm(\n ' + ',\n '.join(f'.{n}({v})' for n, v in mapping.items()) + '\n);\nendmodule\n')
    out.mkdir()
    (out / 'rm_medical.v').write_text('\n'.join(lines))
    (out / 'clock.xdc').write_text('create_clock -period 10.000 -name clk [get_ports clk]\n')
    port_bits = []
    directions = {}
    for d, w, n in ports:
        bits = [n] if not w else [f'{n}[{i}]' for i in range(width(w))]
        port_bits.extend(bits)
        directions.update({b: ('IN' if d == 'input' else 'OUT') for b in bits})
    assert len(port_bits) == 1830
    (out / 'rp_port_bits.txt').write_text('\n'.join(sorted(port_bits)) + '\n')
    (out / 'rp_port_directions.txt').write_text('\n'.join(f'{n} {directions[n]}' for n in sorted(directions)) + '\n')
    proof = dict(schema='kv260.ct_preprocess.DFX_boundary.v1', identity=0xd6,
                 RP_declarations=67, RP_bits=1830, boundary_SHA256=sha(boundary_file),
                 generated_HLS_top=top.relative_to(ROOT).as_posix(), HLS_top_SHA256=sha(top),
                 wrapper_SHA256=sha(out/'rm_medical.v'), generator_SHA256=sha(__file__),
                 no_AXIS_passthrough=True, data_AXIS_512=True, model_and_status_AXI_MM_128=True,
                 input_sample_bits=16, output_sample_bits=8, logical_tail_zero_padded=True,
                 new_static_shell_required=False, tied_optional_HLS_signals=tied,
                 actual_RM_synthesis_passed=False, full_PR_passed=False, PL_accessed=False,
                 production_promoted=False)
    (out / 'boundary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('top',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(generate(a.top,a.output),indent=2))
