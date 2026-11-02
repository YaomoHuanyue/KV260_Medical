import re
BUDGET=dict(LUT=88320,FF=176640,DSP=960,BRAM36_equivalent=132,URAM=64)
def resource_row(text,instance):
    header=None
    for line in text.splitlines():
        fields=[v.strip() for v in line.split('|')[1:-1]]
        if fields and fields[0]=='Instance' and 'Total LUTs' in fields:header=fields
        if header and fields and fields[0]==instance:
            row=dict(zip(header,fields));integer=lambda name:int(row[name].replace(',',''))
            return dict(LUT=integer('Total LUTs'),FF=integer('FFs'),DSP=integer('DSP Blocks'),
                BRAM36=integer('RAMB36'),BRAM18=integer('RAMB18'),URAM=integer('URAM'))
    raise AssertionError('Missing actual routed '+instance)

def reports(timing,drc,pr,util):
    match=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+[-\d.]+\s+\d+\s+\d+\s+([-\d.]+)',timing,re.S)
    assert match;wns,whs=map(float,match.groups())
    assert wns>=0 and whs>=0 and 'All user specified timing constraints are met.' in timing
    for clock in ['clk_pl_0','clk_pl_1']:
        assert re.search(r'^'+clock+r'\s+\{0\.000 5\.000\}\s+10\.000\s+100\.000\s*$',timing,re.M),clock
    for check in ['no_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops']:
        assert re.search(r'checking '+check+r' \(0\)',timing),check
    assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',drc,re.I)
    assert re.search(r'PR_VERIFY: check points .*config_smooth\.dcp and .*config_smooth_shared_fma2_r1\.dcp are compatible',pr)
    assert not re.search(r'(?m)^\s*(?:ERROR|FATAL)\s*[:\[]',pr)
    whole=resource_row(util,'system_top');rp=resource_row(util,'rp')
    used=dict(LUT=rp['LUT'],FF=rp['FF'],DSP=rp['DSP'],BRAM36_equivalent=rp['BRAM36']+.5*rp['BRAM18'],URAM=rp['URAM'])
    assert all(used[k]<=v for k,v in BUDGET.items())
    return dict(clock_MHz=100,WNS_ns=wns,WHS_ns=whs,whole_resources=whole,RP_resources=rp,
        remaining_RP={k:v-used[k] for k,v in BUDGET.items()},timing_constraints_and_DRC_and_full_PR_checked=True)