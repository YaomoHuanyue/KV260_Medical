"""Full AP159 domains; independent on-the-fly source and packet golden model."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def cases(native):
    rows=[]
    def add(h,w,ca,cb,fa,fb,k,mode,ci=None,invalid=False,model=-1):
        rows.append(dict(h=h,w=w,ca=ca,cb=cb,fa=fa,fb=fb,k=k,mode=mode,ci=ca+cb if ci is None else ci,invalid=invalid,model_id=model))
    for k in (1,3):
        for h,w in ((1,1),(1,7),(3,5),(8,16)):
            for ci in (1,5,8,9,31,32,63,64):add(h,w,ci,0,1,1,k,0)
    for k in (1,3):
        for ca,cb in ((1,0),(5,0),(16,0),(1,1),(7,9),(9,7),(31,33),(32,32),(63,1)):
            for fa,fb in ((1,1),(2,1),(1,2),(2,2)):add(8,12,ca,cb,fa,fb,k,1 if cb==0 else 2)
    for i,c in enumerate(native['full_model_join_cases']):
        for k in (1,3):add(**{n:c[n] for n in ('h','w','ca','cb','fa','fb')},k=k,mode=2,model=i)
    options=dict(h=8,w=12,ca=5,cb=0,fa=1,fb=1,k=1,mode=1)
    changes=[dict(h=0),dict(h=513),dict(w=0),dict(w=513),dict(k=2),dict(mode=3),dict(ca=0),dict(ca=65),
        dict(cb=1),dict(fa=0),dict(fa=3),dict(fb=0),dict(fb=4),dict(h=7,fa=2),dict(w=11,fa=2),dict(mode=2),dict(ci=6)]
    for change in changes:add(**dict(options,**change),invalid=True)
    assert len(rows)==len(native['cases'])==159
    for row,gold in zip(rows,native['cases']):
        for n in ('h','w','ca','cb','fa','fb','mode'):assert row[n]==gold[n],(n,row,gold)
        assert row['k']==gold['kernel'] and row['invalid']==(gold['status']!=0)
    return rows

def port_contract(rtl):
    params={}
    for n,expression in re.findall(r'^parameter\s+(C_\w+)\s*=\s*([^;]+);',rtl,re.M):
        assert re.fullmatch(r'[0-9 ()/+*-]+',expression),expression
        value=eval(expression,{'__builtins__':{}},{})
        assert value==int(value);params[n]=int(value)
    assert params['C_M_AXI_MEMORY_DATA_WIDTH']==256 and params['C_M_AXI_MEMORY_ADDR_WIDTH']==64
    assert params['C_M_AXI_MEMORY_ID_WIDTH']==1 and params['C_S_AXI_CONTROL_ADDR_WIDTH']==8
    mapping=[];declarations=[];connections=[]
    for direction,width,name in re.findall(r'^(input|output)\s+(\[[^\]]+\])?\s*(\w+)\s*;',rtl,re.M):
        short={'ap_clk':'clk','ap_rst_n':'resetn','interrupt':'irq'}.get(name)
        if short is None:
            for prefix,alias in [('m_axi_memory_','m_'),('s_axi_control_','c_'),('pixels_T','s_')]:
                if name.startswith(prefix):short=alias+name.removeprefix(prefix).lower();break
        assert short is not None,name
        for n,v in params.items():width=re.sub(r'\b'+re.escape(n)+r'\b',str(v),width)
        assert not re.search(r'[A-Za-z_]',width),width
        declarations.append(' '+('logic' if direction=='input' else 'wire')+' '+width+' '+short+';')
        connections.append('.'+name+'('+short+')');mapping.append(dict(port=name,signal=short,direction=direction,width=width))
    assert len(mapping)==71,len(mapping)
    return '\n'.join(declarations),',\n'.join(connections),mapping,params

def generate(out,rtl,native,mode):
    assert not out.exists() or not any(out.iterdir())
    out.mkdir(parents=True,exist_ok=True);rows=cases(native)
    declarations,connections,ports,params=port_contract(rtl.replace('\r',''))
    metadata=[]
    for i,row in enumerate(rows):
        metadata.append(f'   {i}:begin '+''.join(f'{n}={int(v)};' for n,v in row.items())+'end')
    text=(HERE/'testbench.sv.in').read_text('utf-8')
    edits={'@STALLS@':str(int(mode=='random')),'@PORT_DECLARATIONS@':declarations,
        '@PORT_CONNECTIONS@':connections,'@CASES@':'\n'.join(metadata)}
    for a,b in edits.items():assert text.count(a)==1;text=text.replace(a,b)
    assert not re.search(r'@[A-Z_]+@',text)
    with (out/'tb.sv').open('x',encoding='ascii') as f:f.write(text)
    data=[v&255 for c in native['full_model_join_cases'] for branch in c['tables'] for v in branch]
    assert len(data)==1536
    with (out/'model_lut.hex').open('x',encoding='ascii') as f:f.write('\n'.join(f'{v:02x}' for v in data)+'\n')
    contract=dict(schema='kv260.tensor_reader.full159_RTL_harness.v1',mode=mode,cases=rows,case_count=159,
        original142_valid17_invalid_domains_exact=True,full_actual_three_model_join_dimensions_and_LUTs=True,
        two_trailing_calls_and_four_actual_reset_recovery_cases=True,complete_frames_each_mode=165,
        reset_stages=['pending_AR','pending_read_response','held_AXIS','held_AXIS64cycles'],
        every_packet_data_zero_padding_keep_strb_last_checked=True,no_DDR_writes_allowed=True,
        AXI_lowDDR_alignment_4K_and_each_source_LUT_bounds_checked=True,AXI_AXIL_AXIS_hold_monitors=True,
        source_pattern_matches_original_full_AP159_bench=True,
        port_map=ports,actual_generated_top_parameters=params,
        generated_SV_SHA256=sha(out/'tb.sv'),actual_model_LUT_hex_SHA256=sha(out/'model_lut.hex'),
        simulation_only=True,whole_goal_completed=False)
    save(out/'harness_contract.json',contract);return contract
