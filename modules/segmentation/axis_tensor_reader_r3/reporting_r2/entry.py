"""Use the unchanged qualified R3 stage, correcting only its report metadata."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))

def main():
    inputs=json.loads((HERE/'inputs.json').read_text())
    protected=json.loads((ROOT/'results/storage_cleanup_20261015/current_dependencies.json').read_text())
    for n,h in inputs['source_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h or protected.get('kv260_system/'+n)!=h:
            raise RuntimeError('Changed/unsealed R3 report adapter: '+n)
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import entry as stage,functional
    from modules.segmentation.axis_tensor_reader_r3.reporting_r2.assignment import write_report
    original=functional.run_worker
    def corrected(args,prepared,record):return write_report(args,original(args,prepared,record))
    functional.run_worker=corrected
    stage.main()

if __name__=='__main__':main()
