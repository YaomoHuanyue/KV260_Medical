"""Full source/159-case/config HLS package with strict direct AP program exit."""
from pathlib import Path
import ast,inspect,sys
import start_tensor_reader_HLS_20261022_r1 as parent
ROOT=parent.ROOT;HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/HLS_r1'
OUT=ROOT/'results/tensor_reader_R3_HLS_20261022_r1/axis_hls'

def main():
    assert not (OUT/'cleanup_verified_stream.json').exists()
    if sys.argv[1:]==['prepare']:
        parent.project_storage.check(8_000_000)
        for name in ('testbench.cpp','collect.py'):
            target=HERE/name;assert not target.exists();text=(ROOT/'modules/segmentation/axis_tensor_reader_r1/HLS_r1'/name).read_text()
            if name=='collect.py':
                edits=[('results/tensor_reader_HLS_20261022_r1/axis_hls','results/tensor_reader_R3_HLS_20261022_r1/axis_hls'),
                    ("('complete.json','reader.cfg','generated_members.json','csim.log','csim_receipt.json','hls.log','hls_receipt.json')",
                     "('complete.json','reader.cfg','generated_members.json','csim_cli.log','csim_cli_receipt.json','csim_direct.log','csim_direct_receipt.json','direct_AP_source_binding.json','hls.log','hls_receipt.json')"),
                    ("('complete.json','reader.cfg','csim.log','csim_receipt.json','hls.log','hls_receipt.json')",
                     "('complete.json','reader.cfg','csim_cli.log','csim_cli_receipt.json','csim_direct.log','csim_direct_receipt.json','direct_AP_source_binding.json','hls.log','hls_receipt.json')")]
                for a,b in edits:assert text.count(a)==1;text=text.replace(a,b)
                ast.parse(text)
            target.write_text(text,encoding='utf8')
    original=inspect.getsource(parent.configure);source=original
    a="  assert [r['stage'] for r in accepted['actual_stages']]==['csim','hls']"
    b="  assert [r['stage'] for r in accepted['actual_stages']]==['csim_cli','csim_direct','hls']\n  assert accepted['actual_direct_AP_Csim_root_exit0'] and accepted['CLI_failure_not_silently_overridden']\n  assert accepted['actual_stages'][1]['receipt']['exit_code']==accepted['actual_stages'][2]['receipt']['exit_code']==0"
    assert source.count(a)==1;source=source.replace(a,b);assert source.replace(b,a)==original
    parent.HERE=HERE;parent.OUT=OUT;parent.__file__=str(Path(__file__))
    exec(compile(source,str(Path(__file__))+':strict_direct_AP159_and_HLS','exec'),parent.__dict__)
    parent.main()

if __name__=='__main__':main()
