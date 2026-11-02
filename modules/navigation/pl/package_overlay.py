"""Package the independent navigation overlay without hardware access."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--route',action='store_true');args=parser.parse_args()
    pl=ROOT/'pl';base=pl/'route_candidate' if args.route else pl
    release=base/'release';out=base/'package';out.mkdir(parents=True,exist_ok=True)
    hwh=ET.parse(release/'kv260_navigation.hwh').getroot()
    modules=[('nav_reader','nav_reader_0',0x80000000,['input']),('nav_edt','nav_edt_0',0x80010000,[]),('nav_writer','nav_writer_0',0x80020000,['output'])]
    if args.route:modules=[('nav_reader_split','nav_reader_0',0x80000000,['input']),('nav_edt','nav_edt_0',0x80010000,[]),('nav_writer_merge','nav_writer_0',0x80020000,['output']),('nav_route','nav_route_0',0x80040000,[])]
    resets=hwh.findall(".//MODULE[@MODTYPE='proc_sys_reset']")
    assert resets and all(r.find("./PARAMETERS/PARAMETER[@NAME='C_AUX_RESET_HIGH']").get('VALUE')=='1' and r.find("./PARAMETERS/PARAMETER[@NAME='C_EXT_RESET_HIGH']").get('VALUE')=='0' for r in resets)
    entries=[];connections=[];kernels=[];definitions={}
    for ip_index,(name,instance,register_base,argument_names) in enumerate(modules):
        module=hwh.find(f".//MODULE[@INSTANCE='{instance}']");assert module is not None and module.get('MODTYPE')==name
        clock=int(module.find("./PORTS/PORT[@NAME='ap_clk']").get('CLKFREQUENCY'));assert abs(clock-100000000)<=2000
        ranges=hwh.findall(f".//MEMRANGE[@INSTANCE='{instance}'][@SLAVEBUSINTERFACE='s_axi_control']")
        assert ranges and all(int(r.get('BASEVALUE'),0)==register_base for r in ranges)
        entries.append(dict(m_type='IP_KERNEL',m_ip_control='AP_CTRL_NONE',m_int_enable='0',m_interrupt_id='0',m_base_address=hex(register_base),m_name=f'{name}:{instance}'))
        arguments=[]
        for i,arg in enumerate(argument_names):
            connections.append(dict(arg_index=str(i),m_ip_layout_index=str(ip_index),mem_data_index='0'))
            arguments.append(f'<arg name="{arg}" addressQualifier="1" id="{i}" port="s_axi_control" size="0x8" offset="0x10" hostOffset="0x0" hostSize="0x8" type="void*"/>')
        definition=definitions.setdefault(name,dict(arguments=arguments,instances=[]))
        assert definition['arguments']==arguments
        definition['instances'].append(f'<instance name="{instance}"><addrRemap base="{hex(register_base)}" port="s_axi_control"/></instance>')
    for name,definition in definitions.items():
        kernels.append(f'<kernel name="{name}" language="c" type="ip" hwControlProtocol="user_managed"><ports><port name="s_axi_control" mode="slave" range="0x10000" dataWidth="32" portType="addressable" base="0x0"/></ports><args>{"".join(definition["arguments"])}</args><instances>{"".join(definition["instances"])}</instances></kernel>')
    assert not hwh.findall(".//MODULE[@MODTYPE='binary_mc']") and not hwh.findall(".//MODULE[@MODTYPE='ct_conv']")
    bit=(release/'kv260_navigation.bit').read_bytes();pos=2+struct.unpack_from('>H',bit)[0]+2;payload=None
    while pos<len(bit):
        tag=bit[pos];pos+=1
        if tag==0x65:
            size=struct.unpack_from('>I',bit,pos)[0];pos+=4;payload=bit[pos:];assert len(payload)==size and size%4==0;break
        size=struct.unpack_from('>H',bit,pos)[0];pos+=2+size
    assert payload is not None
    swapped=bytearray(len(payload))
    for i in range(4):swapped[i::4]=payload[3-i::4]
    (out/'kv260_navigation.bit.bin').write_bytes(swapped)
    sections={'MEM_TOPOLOGY':{'mem_topology':{'m_count':'1','m_mem_data':[dict(m_type='MEM_DDR4',m_used='1',m_sizeKB='0x200000',m_tag='bank0',m_base_address='0x0')]}},'IP_LAYOUT':{'ip_layout':{'m_count':str(len(entries)),'m_ip_data':entries}},'CONNECTIVITY':{'connectivity':{'m_count':str(len(connections)),'m_connection':connections}}}
    utility='/usr/bin/unwrapped/xclbinutil'
    if not Path(utility).is_file():utility='xclbinutil'
    command=[utility,'--force','--output',str(out/'kv260_navigation.xclbin'),'--key-value','SYS:mode:flat']
    for name,data in sections.items():
        file=out/(name.lower()+'.json');file.write_text(json.dumps(data,indent=2)+'\n');command+=['--add-section',f'{name}:JSON:{file}']
    xml=out/'embedded.xml'
    xml.write_text('<?xml version="1.0"?><project name="kv260_navigation"><platform vendor="xilinx" boardid="kv260" name="kv260_navigation" featureRomTime="0"><device name="xck26" fpgaDevice="xck26-sfvc784-2LV-c"><core name="OCL_REGION_0" type="clc_region" target="bitstream">'+''.join(kernels)+'</core></device></platform></project>')
    command+=['--add-section',f'EMBEDDED_METADATA:RAW:{xml}'];subprocess.run(command,check=True)
    assert (out/'kv260_navigation.xclbin').read_bytes()[:8]==b'xclbin2\0'
    subprocess.run(['dtc','-@','-I','dts','-O','dtb','-o',str(out/'kv260_navigation.dtbo'),str(pl/'vivado/navigation.dts')],check=True)
    (out/'shell.json').write_text('{"shell_type":"XRT_FLAT","num_slots":"1"}\n')
    edt_lanes=re.search(r'NAV_EDT_COMPUTE_LANES=(\d+)',(pl/'hls/edt.cpp').read_text())
    assert edt_lanes and 8%int(edt_lanes[1])==0
    manifest=dict(bit_sha256=digest(release/'kv260_navigation.bit'),hwh_sha256=digest(release/'kv260_navigation.hwh'),bit_bin_sha256=digest(out/'kv260_navigation.bit.bin'),xclbin_sha256=digest(out/'kv260_navigation.xclbin'),dtbo_sha256=digest(out/'kv260_navigation.dtbo'),clock_hz=100000000,lanes=8,edt_compute_lanes=int(edt_lanes[1]),q_fraction_bits=20,ips=entries)
    if args.route:
        route_lanes=re.search(r'ROUTE_TARGET_LANES=(\d+)',(pl/'hls/route.hpp').read_text())
        assert route_lanes
        manifest.update(route_core='nav_route.v1',route_protocol='compact.v2',route_dma='shared.v1',route_target_lanes=int(route_lanes[1]),route_nodes=4096,route_points=4096,route_bricks=4096,route_field_precision='float32',route_geometry_precision='float64')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
