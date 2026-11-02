"""Bounded-memory uncompressed VTK XML PolyData writer; no VTK runtime needed."""
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import numpy as np

TYPES={'f4':'Float32','f8':'Float64','i2':'Int16','i4':'Int32','i8':'Int64',
       'u1':'UInt8','u2':'UInt16','u4':'UInt32','u8':'UInt64'}

def write_vtp(path,points,faces,point_data,active='RGB'):
    points=np.asarray(points);faces=np.asarray(faces)
    if points.ndim!=2 or points.shape[1]!=3 or points.dtype.kind!='f':
        raise ValueError('Expected floating-point XYZ coordinates')
    if not np.isfinite(points).all() or faces.ndim!=2 or faces.shape[1]!=3:
        raise ValueError('Invalid surface coordinates or triangles')
    if faces.dtype.kind not in 'iu' or (faces.size and (faces.min()<0 or faces.max()>=len(points))):
        raise ValueError('Invalid triangle indices')
    if active not in point_data:raise ValueError('Missing active surface scalar')
    root=ET.Element('VTKFile',type='PolyData',version='1.0',
                    byte_order='LittleEndian',header_type='UInt64')
    data=ET.SubElement(root,'PolyData')
    piece=ET.SubElement(data,'Piece',NumberOfPoints=str(len(points)),
        NumberOfVerts='0',NumberOfLines='0',NumberOfStrips='0',NumberOfPolys=str(len(faces)))
    attrs={'Scalars':active}
    if 'Normals' in point_data:attrs['Normals']='Normals'
    pd=ET.SubElement(piece,'PointData',**attrs);arrays=[];offset=0
    def add(parent,name,value):
        nonlocal offset
        value=np.asarray(value)
        if value.ndim not in (1,2):raise ValueError('Invalid VTP array rank')
        key=value.dtype.kind+str(value.dtype.itemsize)
        if key not in TYPES:raise ValueError('Unsupported VTP component type')
        ET.SubElement(parent,'DataArray',type=TYPES[key],Name=name,
            NumberOfComponents=str(value.shape[1] if value.ndim==2 else 1),
            format='appended',offset=str(offset))
        arrays.append(value);offset+=8+value.nbytes
    for name,value in point_data.items():
        value=np.asarray(value)
        if len(value)!=len(points):raise ValueError('Attribute count differs from surface')
        if value.dtype.kind=='f' and not np.isfinite(value).all():
            raise ValueError('Non-finite surface attribute')
        add(pd,name,value)
    ET.SubElement(piece,'CellData')
    add(ET.SubElement(piece,'Points'),'Points',points)
    polys=ET.SubElement(piece,'Polys')
    add(polys,'connectivity',faces.reshape(-1))
    add(polys,'offsets',np.arange(1,len(faces)+1,dtype=np.int64)*3)
    header=ET.tostring(root,encoding='utf-8')
    assert header.endswith(b'</VTKFile>')
    with Path(path).open('xb') as stream:
        stream.write(b'<?xml version="1.0"?>\n'+header[:-10])
        stream.write(b'\n<AppendedData encoding="raw">_')
        for value in arrays:
            stream.write(struct.pack('<Q',value.nbytes))
            # A strided column is packed only one chunk at a time. No complete
            # XML string, triangle expansion, or second full-array byte copy.
            rows=max(1,262144//max(1,value.dtype.itemsize*np.prod(value.shape[1:],dtype=int)))
            for start in range(0,len(value),rows):
                chunk=np.asarray(value[start:start+rows],dtype=value.dtype.newbyteorder('<'),order='C')
                stream.write(memoryview(chunk).cast('B'))
        stream.write(b'</AppendedData>\n</VTKFile>\n')
