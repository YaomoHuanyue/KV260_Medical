"""Two-level resident scene for the independent C9 quality renderer candidate.

Directory: 32-voxel pages. Leaf: 4-voxel bricks in eight parity banks.
Signed Q5/Q6 and one target bit share each 16-bit sample; no separate atlas.
"""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT=Path(__file__).resolve().parent
SX,SY,SZ=384,320,512
MAX_BLOCKS=10240;MAX_PAGES=128
DIR_WORDS=512;LEAF_WORDS=MAX_PAGES*16;SW=MAX_BLOCKS*2
SCENE_WORDS=1+DIR_WORDS+LEAF_WORDS+SW
SCENE_MAGIC=0x53514733


def normal_matrix(geometry,bits):
    spacing=np.asarray(geometry['spacing_xyz'],float)
    direction=np.asarray(geometry['direction'],float).reshape(3,3)
    if (bits not in (5,6) or not np.isfinite(np.r_[spacing,direction.ravel()]).all() or
            np.any(spacing<=0) or not np.allclose(direction.T@direction,np.eye(3),rtol=0,atol=1e-6)):
        raise ValueError('Invalid physical normal geometry')
    value=np.rint(np.linalg.inv(direction).T@np.diag((254 if bits==5 else 127)/spacing))
    if np.any(np.abs(value)>32767):raise ValueError('Normal matrix range')
    return value.astype('<i4')


def pack_scene(field,selected,token,geometry,*,bits=5):
    q=np.asarray(field);selected=np.asarray(selected)
    if (q.ndim!=3 or q.dtype!=np.dtype('<i2') or selected.dtype!=np.dtype(bool) or selected.shape!=q.shape or
            bits not in (5,6) or not isinstance(token,int) or not 0<=token<=0x7fffffff):
        raise ValueError('INT16 field, boolean target, Q5/Q6 and token required')
    z,y,x=q.shape;outside=-(4<<bits)
    if not (2<=x<=SX and 2<=y<=SY and 2<=z<=SZ):raise ValueError('Quality scene exceeds physical grid limits')
    if np.any(q<outside) or np.any(q>4095) or np.any(selected&(q<=0)):
        raise ValueError('Signed 13-bit saturated field/positive target required')
    padding=tuple((0,(-n)%4) for n in q.shape)
    qp=np.pad(q,padding,constant_values=outside);sp=np.pad(selected,padding)
    hz,hy,hx=np.asarray(qp.shape)//4
    active=(qp!=outside).reshape(hz,4,hy,4,hx,4).any((1,3,5));bricks=np.argwhere(active)
    if len(bricks)>MAX_BLOCKS:raise ValueError('Quality brick cache exceeded; no implicit downsampling')
    pages=np.unique(bricks//8,axis=0)
    if len(pages)>MAX_PAGES:raise ValueError('Quality directory leaf cache exceeded')
    page_z,page_y,page_x=(np.asarray(q.shape)+31)//32
    page_ids=np.zeros((page_z,page_y,page_x),np.uint16)
    if len(pages):page_ids[tuple(pages.T)]=np.arange(1,len(pages)+1,dtype=np.uint16)
    directory=np.zeros(DIR_WORDS*4,'<u2');directory[:page_ids.size]=page_ids.ravel()
    directory=np.repeat(directory.view('<u8')[:,None],8,axis=1)
    leaves=np.zeros((LEAF_WORDS*4,8),'<u2');data=np.zeros((SW,8),'<u8')
    if len(bricks):
        bz,by,bx=bricks.T;ids=np.arange(1,len(bricks)+1,dtype=np.uint16)
        page=page_ids[bz//8,by//8,bx//8].astype(np.int64)-1
        local=((bz&7)//2)*16+((by&7)//2)*4+(bx&7)//2
        bank=(bx&1)+2*(by&1)+4*(bz&1)
        leaves[page*64+local,bank]=ids
        local=np.arange(8);iz=(local>>2)*2;iy=((local>>1)&1)*2;ix=(local&1)*2
        shifts=np.arange(4,dtype=np.uint64)*16
        for bank in range(8):
            zz=bz[:,None]*4+((bank>>2)&1)+iz;yy=by[:,None]*4+((bank>>1)&1)+iy;xx=bx[:,None]*4+(bank&1)+ix
            words=(qp[zz,yy,xx].astype(np.int32)&8191).astype(np.uint64)|(sp[zz,yy,xx].astype(np.uint64)<<13)
            data[np.arange(len(bricks))*2,bank]=np.sum(words[:,:4]<<shifts,axis=1,dtype=np.uint64)
            data[np.arange(len(bricks))*2+1,bank]=np.sum(words[:,4:]<<shifts,axis=1,dtype=np.uint64)
    leaves=leaves.T.copy().view('<u8').T.copy()
    header=np.zeros(16,'<i4');header[:6]=[x,y,z,token,SCENE_MAGIC,len(bricks)]
    header[6:15]=normal_matrix(geometry,bits).ravel();header[15]=len(pages)|(bits<<8)
    return header.tobytes()+directory.tobytes()+leaves.tobytes()+data.tobytes(),dict(
        bricks=len(bricks),pages=len(pages),shape_xyz=[x,y,z],fraction_bits=bits,
        field_scale_mm=1/(1<<bits),packet_bytes=SCENE_WORDS*64,
        source_grid_preserved=True,selected_bits_embedded=True,production_promoted=False)


def unpack_scene(blob):
    if len(blob)!=SCENE_WORDS*64:raise ValueError('Quality packet length')
    h=np.frombuffer(blob[:64],'<i4');x,y,z=map(int,h[:3]);count=int(h[5]);pages=int(h[15])&255;bits=(int(h[15])>>8)&255
    if (int(h[4])!=SCENE_MAGIC or not (2<=x<=SX and 2<=y<=SY and 2<=z<=SZ) or
            not 0<=count<=MAX_BLOCKS or not 0<=pages<=MAX_PAGES or bits not in (5,6) or int(h[15])>>16 or
            np.any(np.abs(h[6:15].astype(np.int64))>32767)):
        raise ValueError('Quality packet header')
    words=np.frombuffer(blob[64:],'<u8').reshape(-1,8)
    directory=words[:DIR_WORDS];leaves=words[DIR_WORDS:DIR_WORDS+LEAF_WORDS];data=words[DIR_WORDS+LEAF_WORDS:]
    if not np.all(directory==directory[:,0,None]):raise ValueError('Divergent directory banks')
    directory=directory[:,0].copy().view('<u2')
    entries=leaves.T.copy().view('<u2').T
    if np.any(directory>pages) or np.any(entries>count):raise ValueError('Out-of-range page/brick ID')
    samples=data.T.copy().view('<u2')
    signed=(samples.astype(np.int32)&8191);signed=np.where(signed&4096,signed-8192,signed)
    if np.any(samples&49152) or np.any(signed<-(4<<bits)) or np.any((samples&8192)!=0)&np.any(signed[(samples&8192)!=0]<=0):
        raise ValueError('Invalid packed signed field/target')
    hz,hy,hx=(z+3)//4,(y+3)//4,(x+3)//4
    bz,by,bx=np.indices((hz,hy,hx));px,py=(x+31)//32,(y+31)//32
    page=directory[((bz//8)*py+by//8)*px+bx//8].astype(np.int32)
    bank=(bx&1)+2*(by&1)+4*(bz&1)
    local=((bz&7)//2)*16+((by&7)//2)*4+(bx&7)//2
    index=np.maximum(page-1,0)*64+local
    ids=((leaves[index//4,bank]>>((index&3)*16).astype(np.uint64))&65535).astype(np.int32)
    ids[page==0]=0
    bz,by,bx=np.nonzero(ids);bid=ids[bz,by,bx]-1
    field=np.full((z,y,x),-(4<<bits),np.int16);target=np.zeros(field.shape,bool)
    local=np.arange(8);iz=(local>>2)*2;iy=((local>>1)&1)*2;ix=(local&1)*2
    for bank in range(8):
        zz=bz[:,None]*4+((bank>>2)&1)+iz;yy=by[:,None]*4+((bank>>1)&1)+iy;xx=bx[:,None]*4+(bank&1)+ix
        valid=(zz<z)&(yy<y)&(xx<x);index=bid[:,None]*8+local
        value=((data[index//4,bank]>>((index&3)*16).astype(np.uint64))&65535).astype(np.int32)
        q=value&8191;q=np.where(q&4096,q-8192,q).astype(np.int16)
        field[zz[valid],yy[valid],xx[valid]]=q[valid]
        target[zz[valid],yy[valid],xx[valid]]=(value[valid]&8192)!=0
    return field,target
