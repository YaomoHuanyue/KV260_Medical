"""Package the independent three-IP CT layout; never programs or resets hardware."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess
import xml.etree.ElementTree as ET

IPS=[('ct_reader','ct_reader_0',0x80000000,('input',)),('ct_conv','ct_conv_0',0x80010000,('weights',)),('ct_writer','ct_writer_0',0x80020000,('output',))]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('bit',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--pl-requantization',action='store_true');ap.add_argument('--macs-per-cycle',type=int,choices=[128,256,512,768],default=128);ap.add_argument('--pointwise-streaming',action='store_true');ap.add_argument('--spatial-streaming',action='store_true');ap.add_argument('--pl-activation-lut',action='store_true');ap.add_argument('--spatial-pixels',type=int,choices=[1,2,3],default=1);ap.add_argument('--line-buffer-memory',choices=['uram','bram'],default='uram');a=ap.parse_args()
    if a.spatial_pixels>1 and (a.macs_per_cycle!=256*a.spatial_pixels or not a.spatial_streaming):ap.error('Spatial pixel count must match the MAC count and streaming architecture')
    hwh=ET.parse(a.bit.with_suffix('.hwh')).getroot()
    resets=hwh.findall(".//MODULE[@MODTYPE='proc_sys_reset']")
    assert resets and all(r.find("./PARAMETERS/PARAMETER[@NAME='C_AUX_RESET_HIGH']").get('VALUE')=='1' for r in resets)
    assert all(r.find("./PARAMETERS/PARAMETER[@NAME='C_EXT_RESET_HIGH']").get('VALUE')=='0' for r in resets)
    for name,instance,base,args in IPS:
        module=hwh.find(f".//MODULE[@INSTANCE='{instance}']")
        assert module is not None and module.get('MODTYPE')==name
        clock=module.find("./PORTS/PORT[@NAME='ap_clk']")
        assert clock is not None and 99000000<=int(clock.get('CLKFREQUENCY'))<=101000000
        ranges=hwh.findall(f".//MEMRANGE[@INSTANCE='{instance}'][@SLAVEBUSINTERFACE='s_axi_control']")
        assert ranges and all(int(r.get('BASEVALUE'),0)==base for r in ranges),(name,ranges)
    input_widths=[]
    for instance in ['ct_reader_0','ct_conv_0']:
        port=hwh.find(f".//MODULE[@INSTANCE='{instance}']/PORTS/PORT[@NAME='pixels_TDATA']")
        assert port is not None
        input_widths.append(abs(int(port.get('LEFT'))-int(port.get('RIGHT')))+1)
    assert input_widths[0]==input_widths[1] and input_widths[0] in [64,256]
    port=hwh.find(".//MODULE[@INSTANCE='ct_reader_0']/PORTS/PORT[@NAME='m_axi_memory_RDATA']")
    assert port is not None
    reader_width=abs(int(port.get('LEFT'))-int(port.get('RIGHT')))+1
    assert reader_width==input_widths[0], 'Reader DDR/AXIS width mismatch'
    bit=a.bit.read_bytes();pos=2+struct.unpack_from('>H',bit)[0]+2;payload=None
    while pos<len(bit):
        tag=bit[pos];pos+=1
        if tag==0x65:
            size=struct.unpack_from('>I',bit,pos)[0];pos+=4;payload=bit[pos:]
            assert len(payload)==size and size%4==0;break
        size=struct.unpack_from('>H',bit,pos)[0];pos+=2+size
    assert payload is not None
    a.output.mkdir(parents=True,exist_ok=True);out=a.output
    swapped=bytearray(len(payload))
    for i in range(4):swapped[i::4]=payload[3-i::4]
    (out/'ct_segmentation.bit.bin').write_bytes(swapped)
    connections=[];entries=[];kernels=[];definitions={};instances={}
    for index,(name,instance,base,args) in enumerate(IPS):
        entries.append(dict(m_type='IP_KERNEL',m_ip_control='AP_CTRL_NONE',m_int_enable='0',m_interrupt_id='0',m_base_address=hex(base),m_name=f'{name}:{instance}'))
        ports='<ports><port name="s_axi_control" mode="slave" range="0x10000" dataWidth="32" portType="addressable" base="0x0"/></ports>'
        arguments=[]
        for i,arg in enumerate(args):
            connections.append(dict(arg_index=str(i),m_ip_layout_index=str(index),mem_data_index='0'))
            arguments.append(f'<arg name="{arg}" addressQualifier="1" id="{i}" port="s_axi_control" size="0x8" offset="{hex(0x10+i*0x10)}" hostOffset="0x0" hostSize="0x8" type="void*"/>')
        definitions[name]=(ports,''.join(arguments))
        instances.setdefault(name,[]).append(f'<instance name="{instance}"><addrRemap base="{hex(base)}" port="s_axi_control"/></instance>')
    for name,(ports,args) in definitions.items():
        kernels.append(f'<kernel name="{name}" language="c" type="ip" hwControlProtocol="user_managed">{ports}<args>{args}</args><instances>{"".join(instances[name])}</instances></kernel>')

    sections={'MEM_TOPOLOGY':{'mem_topology':{'m_count':'1','m_mem_data':[dict(m_type='MEM_DDR4',m_used='1',m_sizeKB='0x200000',m_tag='bank0',m_base_address='0x0')]}},
              'IP_LAYOUT':{'ip_layout':{'m_count':str(len(entries)),'m_ip_data':entries}},
              'CONNECTIVITY':{'connectivity':{'m_count':str(len(connections)),'m_connection':connections}}}
    utility='/usr/bin/unwrapped/xclbinutil'
    if not Path(utility).is_file():utility='xclbinutil'
    existing=out/'ct_segmentation.xclbin';old_manifest=out/'package_manifest.json'
    reuse=False
    if existing.exists() and old_manifest.exists():
        previous=json.loads(old_manifest.read_text())
        reuse=hashlib.sha256(existing.read_bytes()).hexdigest()==previous.get('xclbin_sha256')
    cmd=[utility,'--force','--output',str(existing),'--key-value','SYS:mode:flat']
    for name,value in sections.items():
        path=out/(name.lower()+'.json');data=json.dumps(value,indent=2)+'\n'
        reuse=reuse and path.exists() and json.loads(path.read_text())==value
        path.write_text(data);cmd+=['--add-section',f'{name}:JSON:{path}']
    xml=out/'embedded.xml'
    xml_data='<?xml version="1.0"?><project name="ct_segmentation"><platform vendor="xilinx" boardid="kv260" name="kv260_ct" featureRomTime="0"><device name="xck26" fpgaDevice="xck26-sfvc784-2LV-c"><core name="OCL_REGION_0" type="clc_region" target="bitstream">'+''.join(kernels)+'</core></device></platform></project>'
    reuse=reuse and xml.exists() and xml.read_text()==xml_data
    xml.write_text(xml_data);cmd+=['--add-section',f'EMBEDDED_METADATA:RAW:{xml}']
    if reuse:print('Reusing identical XRT metadata and UUID; bitstream deployment is separate.')
    else:subprocess.run(cmd,check=True)
    assert (out/'ct_segmentation.xclbin').read_bytes()[:8]==b'xclbin2\0'
    (out/'shell.json').write_text('{"shell_type":"XRT_FLAT","num_slots":"1"}\n')
    (out/'package_manifest.json').write_text(json.dumps(dict(bit_sha256=hashlib.sha256(bit).hexdigest(),hwh_sha256=hashlib.sha256(a.bit.with_suffix('.hwh').read_bytes()).hexdigest(),xclbin_sha256=hashlib.sha256((out/'ct_segmentation.xclbin').read_bytes()).hexdigest(),clock_hz=100000000,conv_macs_per_cycle=a.macs_per_cycle,spatial_pixels=a.spatial_pixels,pointwise_macs_per_cycle=256 if a.pointwise_streaming else a.macs_per_cycle,pl_requantization=a.pl_requantization,pointwise_streaming=a.pointwise_streaming,spatial_streaming=a.spatial_streaming,pl_activation_lut=a.pl_activation_lut,line_buffer_memory='2 URAM',ips=entries),indent=2)+'\n')
    manifest=json.loads((out/'package_manifest.json').read_text())
    manifest['input_axis_bits']=input_widths[0]
    manifest['reader_ddr_bits']=reader_width
    manifest['line_buffer_memory']='2 BRAM line buffers' if a.line_buffer_memory=='bram' else '2 URAM'
    (out/'package_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    monitor=out/'debug_monitor.json'
    if monitor.exists():
        info=json.loads(monitor.read_text());info.update(bit_bin_sha256=hashlib.sha256(swapped).hexdigest(),pl_requantization=a.pl_requantization,pointwise_streaming=a.pointwise_streaming,spatial_streaming=a.spatial_streaming,pl_activation_lut=a.pl_activation_lut,pending_clean_boot=True,spatial_pixels=a.spatial_pixels,conv_macs_per_cycle=a.macs_per_cycle)
        info.pop('verified_boot_id',None);monitor.write_text(json.dumps(info,indent=2)+'\n')

if __name__=='__main__':main()
