"""Independent original binary/analytical gold checks for 16 packed transactions."""
from pathlib import Path
import hashlib,json,struct,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'dfx/live_effects/c9_glow_lane_r6/rtl_r49'))
from full_output import FIELDS,transactions
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def verify_fixtures():
    origin=json.loads((HERE/'fixture_origin.json').read_text());oracle=json.loads((HERE/'boundary_oracle.json').read_text())
    for proof in [origin,oracle]:
        for n,h in proof['source_and_evidence_sha256'].items():assert SHA(ROOT/n)==h,n
    assert origin['original_cases']==14 and origin['total_cases']==16 and not origin['candidate_output_used_as_gold']
    assert oracle['additional_results_checked']==8705 and not oracle['candidate_model_used_as_gold']
    cases=[tuple(map(int,s.split())) for s in (HERE/'fixtures/cases.txt').read_text().splitlines()];assert len(cases)==16
    return cases

def unpack(raw):
    assert len(raw)%64==0
    return [struct.unpack('<8Q',raw[k:k+64]) for k in range(0,len(raw),64)]

def packed_original(raw,operation):
    legacy=unpack(raw);assert legacy
    if operation==0:return [list(w) for w in legacy]
    header=list(legacy[0]);assert header[3]==0x5052515545525931 and header[5:]==[0,0,0]
    count=len(legacy)-1
    if header[0]:assert count==0 and header[1]==0 and header[2]==0
    else:assert 1<=header[1]<=4096 and 1<=header[2]<=64 and header[1]*header[2]==count and count<=8705
    result=[[0]*8 for _ in range(1+(count+3)//4)];result[0]=header
    result[0][3]=0x5052515545525932;result[0][5]=count;result[0][6]=4
    for i,w in enumerate(legacy[1:]):
        assert w[1]<=0xffffffff and w[2]==i%header[1] and w[3]==i//header[1] and w[4:]==(0,0,0,0)
        record=result[1+i//4];slot=i%4;record[slot*2]=w[0];record[slot*2+1]=w[1]|(w[2]<<32)|(w[3]<<44)
    return result

def reference():
    cases=verify_fixtures();result=[]
    for i,(operation,ni,no,capacity) in enumerate(cases):
        raw=(HERE/'fixtures'/(str(i).zfill(2)+'.input.bin')).read_bytes();gold=(HERE/'fixtures'/(str(i).zfill(2)+'.expected.bin')).read_bytes()
        assert len(raw)==ni*64 and len(gold)==no*64
        wanted=packed_original(gold,operation);word_values=[int.from_bytes(struct.pack('<8Q',*w),'little') for w in wanted]
        result.append(dict(case=i,operation=operation,input_words=ni,output_words=len(wanted),capacity=1 if operation==0 else 2178,
            input_data=[int.from_bytes(raw[k:k+64],'little') for k in range(0,len(raw),64)],output_data=word_values,status=wanted[0][0]))
    assert len(result)==16 and result[15]['output_words']==2178
    return result

def fields(data,count):
    return dict(data_V=data,keep_V=[(1<<64)-1]*count,strb_V=[(1<<64)-1]*count,
        user_V=[int(i==0) for i in range(count)],last_V=[int(i+1==count) for i in range(count)])

def read(path,width):
    values=list(transactions(path,width));assert [i for i,_ in values]==list(range(16))
    return [row for _,row in values]

def generated(sim):
    sim=Path(sim);directory=sim/'tv/cdatafile';expected=reference();checked={}
    for direction,label,key in [('in','input_r_V_','input'),('out','output_r_V_','output')]:
        for field,width in [('data_V',512),('keep_V',64),('strb_V',64),('user_V',1),('last_V',1)]:
            got=read(directory/('c.nav_route.autotv'+direction+'_'+label+field+'.dat'),width)
            want=[fields(case[key+'_data'],case[key+'_words'])[field] for case in expected];assert got==want,(direction,field)
            checked[direction+'/'+field]=dict(transactions=16,all_values_exact=True)
    for name,key in [('operation','operation'),('input_count','input_words'),('output_count','capacity')]:
        assert read(directory/('c.nav_route.autotvin_'+name+'.dat'),32)==[[c[key]] for c in expected],name
    assert read(directory/'c.nav_route.autotvin_status.dat',32)==[[0] for _ in expected]
    assert read(directory/'c.nav_route.autotvout_status.dat',32)==[[c['status']] for c in expected]
    return dict(status='all_14_original_and_2_maximum_cases_independently_bound_to_generated_Cdata',cases=checked,
        transactions=16,original_cases=14,maximum_8705_case_preserved=True,input_words=sum(c['input_words'] for c in expected),output_words=sum(c['output_words'] for c in expected),
        candidate_model_gold_not_trusted=True,full_RTL_passed=False)

def actual(sim):
    sim=Path(sim)
    for name in ['.aesl_error','.exit.err']:assert not (sim/'verilog'/name).exists(),name
    err=sim/'verilog/err.log';assert not err.exists() or 'unmatched' not in err.read_text(errors='replace').lower()
    expected=reference();checked={}
    for field,width in FIELDS:
        path=sim/'tv/rtldatafile'/('rtl.nav_route.autotvout_'+field+'.dat');got=read(path,width)
        if field=='status':want=[[c['status']] for c in expected]
        else:want=[fields(c['output_data'],c['output_words'])[field[len('output_r_V_'):]] for c in expected]
        assert got==want,field
        checked[field]=dict(transactions=16,original_cases=14,maximum_8705_case_passed=True,all_bits_and_ids_exact=True,raw_sha256=SHA(path))
    return checked
