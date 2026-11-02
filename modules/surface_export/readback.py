"""Independent strict raw-appended VTP decoder for byte-level export acceptance."""
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import numpy as np

DTYPES={'Float32':'<f4','Float64':'<f8','Int16':'<i2','Int32':'<i4','Int64':'<i8',
        'UInt8':'u1','UInt16':'<u2','UInt32':'<u4','UInt64':'<u8'}

def readback(path):
    raw=Path(path).read_bytes();marker=b'<AppendedData encoding="raw">_'
    prefix,sep,payload=raw.partition(marker)
    if not sep or not payload.endswith(b'</AppendedData>\n</VTKFile>\n'):
        raise ValueError('Incomplete raw-appended VTP')
    root=ET.fromstring(prefix+b'</VTKFile>')
    if root.attrib.get('type')!='PolyData' or root.attrib.get('header_type')!='UInt64':
        raise ValueError('Unsupported file type or header')
    if root.attrib.get('byte_order')!='LittleEndian':raise ValueError('Unsupported byte order')
    piece=root.find('PolyData/Piece');n=int(piece.attrib['NumberOfPoints']);nf=int(piece.attrib['NumberOfPolys'])
    result={};cursor=0
    for node in root.findall('.//DataArray'):
        if node.attrib.get('format')!='appended' or int(node.attrib['offset'])!=cursor:
            raise ValueError('Noncontiguous or invalid VTP data offset')
        size=struct.unpack_from('<Q',payload,cursor)[0];start=cursor+8;end=start+size
        data=np.frombuffer(payload[start:end],dtype=DTYPES[node.attrib['type']]).copy()
        count=int(node.attrib['NumberOfComponents'])
        if count>1:data=data.reshape(-1,count)
        key=node.attrib['Name']
        if key in result:raise ValueError('Duplicate VTP array')
        result[key]=data;cursor=end
    if payload[cursor:]!=b'</AppendedData>\n</VTKFile>\n':raise ValueError('Unaccounted VTP payload bytes')
    if result['Points'].shape!=(n,3) or result['connectivity'].shape!=(nf*3,):
        raise ValueError('Geometry cardinality mismatch')
    if not np.array_equal(result['offsets'],np.arange(1,nf+1)*3):raise ValueError('Triangle offsets mismatch')
    for node in piece.findall('PointData/DataArray'):
        if len(result[node.attrib['Name']])!=n:raise ValueError('Point attribute cardinality mismatch')
    return result
