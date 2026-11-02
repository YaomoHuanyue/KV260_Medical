"""Expand the prior strict completion predicate to 14 originals + 2 boundaries."""
import re
def check_log(text):
    progress=[tuple(map(int,m)) for m in re.findall(r'RTL Simulation\s*:\s*(\d+)\s*/\s*(\d+)',text)]
    assert progress==[(i,16) for i in range(17)],'all 16 complete transactions required'
    assert re.search(r'\$finish called at time\s*:\s*\d+\s*ns\s*:\s*File\s+"[^"\r\n]*xlnx_uvm_package\.sv" Line 18699\b',text)
    assert '## quit' in text and 'INFO: [Common 17-206] Exiting xsim' in text
    assert not re.search(r'(?m)^\s*(?:UVM_(?:ERROR|FATAL)\b(?!\s*:\s*0\b)|(?:ERROR|FATAL)\s*[:\[])',text)
    assert not re.search(r'(?i)assertion.*(?:fail|error)|deadlock detected|segmentation|access violation',text)
    assert 'UVM Report Summary' in text
    assert all(re.search(r'UVM_'+s+r'\s*:\s*0\b',text) for s in ['ERROR','FATAL'])
    return dict(original_transactions=14,additional_maximum_capacity_transactions=2,total_completed=16,
        normal_official_UVM_finish=True,summary_checked=True,UVM_error_or_fatal_observed=False)
