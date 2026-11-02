"""Passive handshake/counter snapshot; counter page selection never controls DMA."""
import argparse,hashlib,json,mmap,os,struct,time
from pathlib import Path

NAMES='reader_arvalid reader_arready reader_rvalid reader_rready conv_arvalid conv_arready conv_rvalid conv_rready writer_awvalid writer_awready writer_wvalid writer_wready writer_bvalid writer_bready reader_tvalid reader_tready conv_input_tvalid conv_input_tready conv_output_tvalid conv_output_tready writer_tvalid writer_tready ps_arvalid ps_arready ps_rvalid ps_rready ps_awvalid ps_awready ps_wvalid ps_wready ps_bvalid ps_bready'.split()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--include-control',action='store_true',help='Only when no completion polling is active; HLS control reads clear DONE');a=p.parse_args()
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'package/debug_monitor.json').read_text());expected=manifest['bit_bin_sha256']
    loaded=Path('/run/kv260-ct-loaded.sha256').read_text().strip()
    if loaded!=expected:raise RuntimeError('This boot has not loaded the verified diagnostic bit; refusing MMIO')
    firmware=Path('/lib/firmware/xilinx/kv260-ct-segmentation/ct_segmentation.bit.bin')
    if hashlib.sha256(firmware.read_bytes()).hexdigest()!=expected:raise RuntimeError('Firmware file does not match debug manifest')
    result={'time_unix':time.time(),'loaded_bit_bin_sha256':loaded,'ips':{}}
    history=manifest.get('traffic_history',False)
    fd=os.open('/dev/mem',(os.O_RDWR if history else os.O_RDONLY)|os.O_SYNC)
    try:
        for name,base in ([('reader',0x80000000),('conv',0x80010000),('writer',0x80020000)] if a.include_control else []):
            with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=base) as m:
                result['ips'][name]={hex(off):hex(struct.unpack_from('<I',m,off)[0]) for off in [0,0x10,0x14,0x20,0x28,0x30,0x38,0x40,0x48]}
        samples=[]
        with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|(mmap.PROT_WRITE if history else 0),offset=0x80030000) as m:
            for _ in range(5):
                word=struct.unpack_from('<I',m,0)[0]
                samples.append({'word':hex(word),'signals':{n:(word>>i)&1 for i,n in enumerate(NAMES)}})
                time.sleep(.01)
            if history:
                # Keep every physical channel-1 pin input-only. Only the internal
                # output latch selects a page; no accelerator controls are written.
                assert struct.unpack_from('<I',m,4)[0]==0xffffffff
                counts={}
                for page,name in enumerate(['clock_cycles']+[NAMES[i*2].replace('valid','transfers') for i in range(16)]):
                    struct.pack_into('<I',m,0,page)
                    counts[name]=struct.unpack_from('<I',m,8)[0]
                result['counters']=counts
                struct.pack_into('<I',m,0,0)
        result['handshake_samples']=samples
    finally:os.close(fd)
    text=json.dumps(result,indent=2)
    if a.output:a.output.write_text(text+'\n')
    print(text)

if __name__=='__main__':main()
