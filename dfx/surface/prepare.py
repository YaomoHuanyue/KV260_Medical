"""Sparse, geometry-preserving signed INT16 Q5 surface field and reference.

4x4x4 bricks retain original voxel centres. Missing bricks are constant
negative outside field; no voxel downsampling or airway branch deletion.
"""
from pathlib import Path
import argparse, hashlib, json
import numpy as np

ROOT=Path(__file__).resolve().parent
SX,SY,SZ=256,192,128
MAX_BLOCKS=4096; SW=MAX_BLOCKS*2; MAP_WORDS=3072; LABEL_WORDS=512
SCENE_WORDS=1+MAP_WORDS+SW+LABEL_WORDS
SCENE_MAGIC=0x53554632; OUTSIDE_Q5=-128

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def distance_field(airway,spacing_xyz):
    from scipy.ndimage import distance_transform_edt
    a=np.asarray(airway,bool);spacing=np.asarray(spacing_xyz,float)
    if not a.any() or not np.isfinite(spacing).all() or np.any(spacing<=0):
        raise ValueError('Empty airway or invalid spacing')
    sampling=spacing[::-1]
    field=distance_transform_edt(a,sampling=sampling)-distance_transform_edt(~a,sampling=sampling)
    # Only the far outside tail is saturated. Interior distances retain range.
    q=np.rint(field*32).clip(OUTSIDE_Q5,32767).astype('<i2')
    q[a]=np.maximum(q[a],1);q[~a]=np.minimum(q[~a],-1)
    return q

def normal_matrix(geometry=None):
    """Fixed-point inverse transpose: Q5/Q8 central differences to LPS RGB.

    RGB encodes [-2,2] physical gradient units; the GPU only normalizes and
    shades. Keeping magnitude avoids a PL square root and limits clipping.
    """
    geometry=geometry or dict(direction=np.eye(3).ravel(),spacing_xyz=[1,1,1])
    direction=np.asarray(geometry['direction'],float).reshape(3,3)
    spacing=np.asarray(geometry['spacing_xyz'],float)
    if not np.isfinite(np.r_[direction.ravel(),spacing]).all() or np.any(spacing<=0):raise ValueError('Invalid normal geometry')
    coefficients=np.rint(np.linalg.inv(direction).T@np.diag(254/spacing))
    if not np.isfinite(coefficients).all() or np.any(np.abs(coefficients)>32767):raise ValueError('Normal matrix exceeds fixed-point range')
    return coefficients.astype(np.int32)

def pack_scene(field,selected,token,geometry=None):
    q=np.asarray(field);s=np.asarray(selected,bool)
    if q.dtype!=np.dtype('<i2') or q.ndim!=3 or q.shape!=s.shape:
        raise ValueError('INT16 field and matching target required')
    nz,ny,nx=q.shape
    if not(2<=nx<=SX and 2<=ny<=SY and 2<=nz<=SZ):raise ValueError('Scene exceeds bbox')
    if np.any(q<OUTSIDE_Q5) or np.any(s & (q<=0)):raise ValueError('Invalid saturated field/target')
    pad=tuple((0,(-n)%4) for n in q.shape)
    qp=np.pad(q,pad,constant_values=OUTSIDE_Q5);sp=np.pad(s,pad)
    hz,hy,hx=np.array(qp.shape)//4
    active=(qp!=OUTSIDE_Q5).reshape(hz,4,hy,4,hx,4).any((1,3,5))
    bricks=np.argwhere(active)
    if len(bricks)>MAX_BLOCKS:raise ValueError(f'{len(bricks)} bricks exceed {MAX_BLOCKS}; no implicit resampling')
    ids=np.zeros((hz,hy,hx),np.uint16)
    if len(bricks):ids[tuple(bricks.T)]=np.arange(1,len(bricks)+1,dtype=np.uint16)
    maps=np.zeros((MAP_WORDS,8),'<u8');data=np.zeros((SW,8),'<u8');labels=np.zeros((LABEL_WORDS,8),'<u8')
    map_y=(hx+1)//2;map_z=map_y*((hy+1)//2)
    if len(bricks):
        bz,by,bx=bricks.T;bid=np.arange(len(bricks))
        bank=(bx&1)+2*(by&1)+4*(bz&1);index=(bz//2)*map_z+(by//2)*map_y+bx//2
        np.bitwise_or.at(maps.reshape(-1),(index//4)*8+bank,(bid+1).astype(np.uint64)<<((index&3)*16).astype(np.uint64))
        local=np.arange(8);iz=(local>>2)*2;iy=((local>>1)&1)*2;ix=(local&1)*2
        shifts=np.arange(4,dtype=np.uint64)*16;label_shifts=np.arange(8,dtype=np.uint64)*8
        for bank in range(8):
            z=bz[:,None]*4+((bank>>2)&1)+iz;y=by[:,None]*4+((bank>>1)&1)+iy;x=bx[:,None]*4+(bank&1)+ix
            values=qp[z,y,x].view(np.uint16).astype(np.uint64)
            data[bid*2,bank]=np.sum(values[:,:4]<<shifts,axis=1,dtype=np.uint64)
            data[bid*2+1,bank]=np.sum(values[:,4:]<<shifts,axis=1,dtype=np.uint64)
            byte=np.sum(sp[z,y,x].astype(np.uint64)<<local.astype(np.uint64),axis=1,dtype=np.uint64)
            padded=np.pad(byte,(0,(-len(byte))%8));words=np.sum(padded.reshape(-1,8)<<label_shifts,axis=1,dtype=np.uint64)
            labels[:len(words),bank]=words
    header=np.zeros(16,'<i4');header[:6]=[nx,ny,nz,token,SCENE_MAGIC,len(bricks)]
    header[6:15]=normal_matrix(geometry).ravel()
    return header.tobytes()+maps.tobytes()+data.tobytes()+labels.tobytes(),dict(bricks=len(bricks),cached_voxels=len(bricks)*64,shape_xyz=[nx,ny,nz],distance_scale_mm=1/32,outside_saturation_mm=-4)

def unpack_scene(blob):
    if len(blob)!=SCENE_WORDS*64:raise ValueError('Sparse packet length')
    header=np.frombuffer(blob[:64],'<i4');nx,ny,nz=map(int,header[:3]);count=int(header[5])
    if int(header[4])!=SCENE_MAGIC or not(2<=nx<=SX and 2<=ny<=SY and 2<=nz<=SZ and 0<=count<=MAX_BLOCKS) or np.any(np.abs(header[6:15].astype(np.int64))>32767):raise ValueError('Sparse packet header')
    words=np.frombuffer(blob[64:],'<u8').reshape(-1,8);maps=words[:MAP_WORDS];data=words[MAP_WORDS:MAP_WORDS+SW];labels=words[MAP_WORDS+SW:]
    hx,hy,hz=(nx+3)//4,(ny+3)//4,(nz+3)//4;z,y,x=np.indices((hz,hy,hx))
    bank=(x&1)+2*(y&1)+4*(z&1);index=((z//2)*((hy+1)//2)+y//2)*((hx+1)//2)+x//2
    ids=((maps[index//4,bank]>>((index&3)*16).astype(np.uint64))&65535).astype(np.int32)
    if np.any(ids>count):raise ValueError('Sparse brick ID out of bounds')
    bz,by,bx=np.nonzero(ids);bid=ids[bz,by,bx]-1
    field=np.full((nz,ny,nx),OUTSIDE_Q5,np.int16);selected=np.zeros(field.shape,bool)
    local=np.arange(8);iz=(local>>2)*2;iy=((local>>1)&1)*2;ix=(local&1)*2
    for bank in range(8):
        z=bz[:,None]*4+((bank>>2)&1)+iz;y=by[:,None]*4+((bank>>1)&1)+iy;x=bx[:,None]*4+(bank&1)+ix
        valid=(z<nz)&(y<ny)&(x<nx);index=bid[:,None]*8+local
        value=((data[index//4,bank]>>((index&3)*16).astype(np.uint64))&65535).astype(np.uint16).view(np.int16)
        target=((labels[bid[:,None]//8,bank]>>((bid[:,None]&7)*8+local).astype(np.uint64))&1).astype(bool)
        field[z[valid],y[valid],x[valid]]=value[valid];selected[z[valid],y[valid],x[valid]]=target[valid]
    return field,selected

def frame_parameters(camera,forward,up,geometry,offset_xyz,width,height,sequence=1):
    if width%16 or not 16<=width<=640 or not 4<=height<=512:raise ValueError('Invalid viewport')
    direction=np.asarray(geometry['direction']).reshape(3,3);spacing=np.array(geometry['spacing_xyz'])
    if not np.isfinite(np.r_[camera,forward,up,direction.ravel(),spacing]).all() or np.any(spacing<=0):raise ValueError('Nonfinite camera/geometry')
    inv=np.diag(1/spacing)@np.linalg.inv(direction)
    f=np.asarray(forward,float);u=np.asarray(up,float)
    if np.linalg.norm(f)<1e-8:raise ValueError('Zero forward vector')
    f/=np.linalg.norm(f);right=np.cross(f,u)
    if np.linalg.norm(right)<1e-8:raise ValueError('Collinear camera axes')
    right/=np.linalg.norm(right);u=np.cross(right,f)
    field=np.tan(np.deg2rad(75/2));aspect=width/height
    step=float(spacing.min()*.35/np.sqrt(1+field*field*(1+aspect*aspect)))
    origin=inv@(np.asarray(camera)-np.asarray(geometry['origin_lps_mm']))-offset_xyz
    d0=inv@(f+right*((1/width-1)*aspect*field)+u*((1-1/height)*field))*step
    dx=inv@right*(2*aspect*field/width)*step;dy=inv@u*(-2*field/height)*step
    params=np.zeros(16,'<i4');params[:4]=[width,height,1023,sequence]
    encoded=np.rint(np.r_[origin,d0,dx,dy]*65536)
    if not np.isfinite(encoded).all() or np.any(encoded<np.iinfo(np.int32).min) or np.any(encoded>np.iinfo(np.int32).max):raise ValueError('Camera/ray coordinates exceed Q16 range')
    params[4:]=encoded.astype('<i4')
    return params,dict(step_mm=step,field=field,width=width,height=height,sequence=sequence,
        ray_origin_index=(params[4:7]/65536).tolist(),ray00_index=(params[7:10]/65536).tolist(),raydx_index=(params[10:13]/65536).tolist(),raydy_index=(params[13:16]/65536).tolist(),forward_lps=f.tolist(),right_lps=right.tolist(),up_lps=u.tolist())

def sample(field,selected,pos):
    nz,ny,nx=field.shape
    xyz=np.asarray(pos,np.int64)>>16;frac=(np.asarray(pos,np.int64)>>8)&255
    a=np.zeros((len(pos),8),np.int64);b=a.copy()
    for k in range(8):
        offset=np.array([k&1,(k>>1)&1,(k>>2)&1]);q=xyz+offset
        valid=np.all((q>=0)&(q<[nx,ny,nz]),axis=1)
        a[:,k]=OUTSIDE_Q5
        x,y,z=q[valid].T;a[valid,k]=field[z,y,x];b[valid,k]=selected[z,y,x]
    fx,fy,fz=frac.T
    def interp(v):
        x=v[:,::2]*(256-fx[:,None])+v[:,1::2]*fx[:,None]
        y=(x[:,::2]*(256-fy[:,None])+x[:,1::2]*fy[:,None])>>8
        return (y[:,0]*(256-fz)+y[:,1]*fz)>>8
    bx=b[:,::2]*(256-fx[:,None])+b[:,1::2]*fx[:,None]
    by=bx[:,::2]*(256-fy[:,None])+bx[:,1::2]*fy[:,None]
    target=(by[:,0]*(256-fz)+by[:,1]*fz)>>8
    return interp(a),target

def contour(depth,mask):
    h,w=mask.shape;mask=mask.astype(np.uint32);pad=np.pad(mask,3,mode='edge')
    hi=np.zeros_like(mask);lo=np.ones_like(mask);outer=np.zeros_like(mask);total=np.zeros_like(mask)
    for j in range(7):
        for k in range(7):
            v=pad[j:j+h,k:k+w];outer|=v
            if 1<=j<=5 and 1<=k<=5:hi|=v;lo&=v
            if 2<=j<=4 and 2<=k<=4:total+=v*(2 if j==3 else 1)*(2 if k==3 else 1)
    coverage=(total*255+8)//16;edge=np.where(hi&~lo,255,np.where(outer&~hi,128,0)).astype(np.uint32)
    return depth|(coverage<<16)|(edge<<24)

def smooth_normals(depth,normals):
    """Depth-aware screen filter, without modifying wall or target pixels."""
    h,w=depth.shape
    d=np.pad(depth,1,mode='edge').astype(np.int32)
    n=np.pad(normals,((1,1),(1,1),(0,0)),mode='edge')
    weights=np.zeros((h,w),np.uint32);total=np.zeros((h,w,3),np.uint32)
    for j in range(3):
        for k in range(3):
            near=n[j:j+h,k:k+w];difference=d[j:j+h,k:k+w]-depth.astype(np.int32)
            weight=((near[:,:,3]==255)&(np.abs(difference)<=128)).astype(np.uint32)*(2 if j==1 else 1)*(2 if k==1 else 1)
            weights+=weight;total+=near[:,:,:3].astype(np.uint32)*weight[:,:,None]
    hit=depth!=65535;out=np.zeros_like(normals)
    out[hit,:3]=((total[hit]+weights[hit,None]//2)//weights[hit,None]).astype(np.uint8)
    out[hit,3]=255
    return out

def reference(field,selected,p,matrix=None):
    width,height,steps=map(int,p[:3]);count=width*height;ids=np.arange(count)
    delta=p[7:10].astype(np.int64)+(ids%width)[:,None]*p[10:13]+(ids//width)[:,None]*p[13:16]
    pos=np.broadcast_to(p[4:7],(count,3)).astype(np.int64).copy()
    active=np.ones(count,bool);inside=np.zeros(count,bool);reached=np.zeros(count,bool)
    depth=np.full(count,65535,np.uint32);normals=np.zeros((count,4),np.uint8)
    matrix=normal_matrix() if matrix is None else np.asarray(matrix,np.int64).reshape(3,3)
    for step in range(steps+1):
        ids=np.flatnonzero(active)
        if not len(ids):break
        value,target=sample(field,selected,pos[ids]);state=value>0
        if not step:inside[ids]=state
        else:
            hit=state!=inside[ids];idx=ids[hit]
            if len(idx):
                base=pos[idx]-delta[idx];low=np.zeros(len(idx),np.int64);high=np.full(len(idx),64,np.int64)
                for _ in range(6):
                    middle=(low+high)//2;q=base+((delta[idx]*middle[:,None])>>6)
                    v,_=sample(field,selected,q);same=(v>0)==inside[idx]
                    low=np.where(same,middle,low);high=np.where(same,high,middle)
                depth[idx]=(step-1)*64+high;active[idx]=False
                hit_pos=base+((delta[idx]*high[:,None])>>6)
                gradients=np.empty((len(idx),3),np.int64)
                for axis in range(3):
                    offset=np.zeros(3,np.int64);offset[axis]=65536
                    positive,_=sample(field,selected,hit_pos+offset)
                    negative,_=sample(field,selected,hit_pos-offset)
                    gradients[:,axis]=positive-negative
                normals[idx,:3]=((gradients@matrix.T>>16).clip(-127,127)+128).astype(np.uint8)
                normals[idx,3]=255
        reached[ids]|=active[ids]&inside[ids]&(target>42598)
        pos[ids]+=delta[ids]
    low=contour(depth.reshape(height,width),(reached&inside).reshape(height,width))
    normals=smooth_normals(depth.reshape(height,width),normals.reshape(height,width,4))
    high=normals.copy().view('<u4').reshape(height,width)
    return low.astype(np.uint64)|(high.astype(np.uint64)<<32)

def fixtures():
    folder=ROOT/'fixtures';folder.mkdir(exist_ok=True)
    z,y,x=np.indices((24,24,32));a=((y-12)**2+(z-12)**2<36)&(x>1)&(x<30);s=a&(x>=16)&(y>=12)
    cases=[]
    for name,mask,target in [('tube',a,s),('blocked',a&(x!=12),s&(x!=12)),('filled',a,a),('empty',a,np.zeros_like(a))]:
        q=distance_field(mask,[1,1,1]);packed,stats=pack_scene(q,target,123)
        (folder/f'{name}.scene.bin').write_bytes(packed)
        p=np.zeros(16,'<i4');p[:4]=[32,16,160,7];p[4:7]=np.array([6,12,12])*65536
        p[7:10]=[16384,-6200,3200];p[10:13]=[0,400,0];p[13:16]=[0,0,-420]
        p.tofile(folder/f'{name}.request.bin');r=reference(q,target,p);r.astype('<u8').tofile(folder/f'{name}.expected.bin')
        cases.append(dict(name=name,**stats,selected_pixels=int(np.count_nonzero((r>>16)&255)),outline_pixels=int(np.count_nonzero((r>>24)&255))))
    assert cases[0]['selected_pixels']>0 and cases[1]['selected_pixels']==0
    assert cases[2]['outline_pixels']==0 and cases[3]['selected_pixels']==0
    # Rotated anisotropic physical coordinates, independently encoded normals.
    spacing=np.array([.6,1.3,2.2]);angle=np.deg2rad(37)
    direction=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    geometry=dict(direction=direction.ravel(),spacing_xyz=spacing)
    center=np.array([15.3,11.8,12.1]);signed=5.5-np.linalg.norm((np.stack((x,y,z),axis=-1)-center)*spacing,axis=-1)
    q=np.rint(signed*32).clip(OUTSIDE_Q5,32767).astype('<i2');target=np.zeros_like(q,bool)
    packed,stats=pack_scene(q,target,123,geometry)
    for name,matrix,scene in [('anisotropic',normal_matrix(geometry),packed),('zero_normal',np.zeros((3,3),np.int32),packed)]:
        scene=bytearray(scene);np.frombuffer(scene,'<i4',count=16)[6:15]=matrix.ravel()
        (folder/f'{name}.scene.bin').write_bytes(scene)
        p=np.zeros(16,'<i4');p[:4]=[32,16,160,7];p[4:7]=np.rint(center*65536)
        p[7:10]=[16384,-4200,1200];p[10:13]=[0,200,0];p[13:16]=[0,0,-130]
        p.tofile(folder/f'{name}.request.bin');reference(q,target,p,matrix).astype('<u8').tofile(folder/f'{name}.expected.bin')
    write_json(folder/'reference.json',dict(cases=cases,algorithm='sparse signed INT16 Q5, Q16/Q8 interpolation, six bisections, first-wall target visibility'))
    print(cases)

def boundary_fixtures():
    """Exercise the final map/cache address and the zero-brick scene on board."""
    folder=ROOT/'fixtures';folder.mkdir(exist_ok=True)
    q=np.full((SZ,SY,SX),OUTSIDE_Q5,np.int16);q[-4:,-4:,-4:]=32;s=q>0
    blob,_=pack_scene(q,s,123);packet=bytearray(blob);header=np.frombuffer(packet,'<i4',count=16)
    words=np.frombuffer(packet,offset=64,dtype='<u8').reshape(-1,8)
    maps=words[:MAP_WORDS];data=words[MAP_WORDS:MAP_WORDS+SW];targets=words[MAP_WORDS+SW:]
    # The only occupied brick is deliberately assigned the highest legal ID.
    maps[-1,-1]=np.uint64(MAX_BLOCKS)<<np.uint64(48);data[-2:]=data[:2];targets[-1]=targets[0]<<np.uint64(56);header[5]=MAX_BLOCKS
    p=np.zeros(16,'<i4');p[:4]=[32,16,64,7];p[4:7]=np.rint(np.array([254.5,190.5,126.5])*65536)
    p[7:10]=[8192,-4096,2048];p[10:13]=[0,256,0];p[13:16]=[0,0,-256]
    for name,scene in [('lastbrick',bytes(packet)),('outside',pack_scene(np.full_like(q,OUTSIDE_Q5),np.zeros_like(s),123)[0])]:
        field,target=unpack_scene(scene)
        if name=='lastbrick':np.testing.assert_array_equal(field,q);np.testing.assert_array_equal(target,s)
        (folder/f'{name}.scene.bin').write_bytes(scene);p.tofile(folder/f'{name}.request.bin')
        reference(field,target,p).astype('<u8').tofile(folder/f'{name}.expected.bin')

def prepare_case(result,output):
    """Prepare one immutable own-CT surface scene, with original grid geometry."""
    import base64,gzip
    import SimpleITK as sitk
    result=Path(result).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    pipeline=json.loads((result/'pipeline.json').read_text(encoding='utf-8'))
    if pipeline['status']!='passed':raise ValueError('Incomplete source result')
    image=sitk.ReadImage(str(result/'segmentation/airway_mask.nii.gz'));full=sitk.GetArrayFromImage(image)!=0
    vox=np.argwhere(full)
    if not len(vox):raise ValueError('Empty source airway')
    lo=np.maximum(0,vox.min(0)-2);hi=np.minimum(full.shape,vox.max(0)+3)
    a=full[tuple(slice(l,h) for l,h in zip(lo,hi))].copy()
    del full,vox
    q=distance_field(a,image.GetSpacing())
    geometry=dict(direction=list(image.GetDirection()),spacing_xyz=list(image.GetSpacing()),origin_lps_mm=list(image.GetOrigin()))
    # Only distance preparation/packing remain on PS; resident PL samples normals.
    nz,ny,nx=a.shape
    report=json.loads((result/'navigation/route.json').read_text(encoding='utf-8'));scenes={}
    for event in [None]+report['branch_guidance']['events']:
        selected=np.zeros_like(a);key=-1 if event is None else event['id'];lumen=None if event is None else event.get('lumen')
        if lumen:
            coverage=np.frombuffer(gzip.decompress(base64.b64decode(lumen['mask_gzip'])),np.uint8).reshape(lumen['shape_xyz'][::-1])
            absolute=np.array(image.TransformPhysicalPointToContinuousIndex(lumen['origin_lps_mm']))[::-1]
            if not np.allclose(absolute,np.rint(absolute),atol=1e-4):raise ValueError('Target grid mismatch')
            low=np.rint(absolute).astype(int)-lo;high=low+coverage.shape
            if np.any(low<0) or np.any(high>np.array(a.shape)):raise ValueError('Target outside crop')
            selected[tuple(slice(l,h) for l,h in zip(low,high))]=coverage>165
            selected&=a
        token=key+1000;packed,stats=pack_scene(q,selected,token,geometry);path=output/f'scene_{key}.bin';path.write_bytes(packed)
        scenes[str(key)]=dict(file=path.name,sha256=sha(path),token=token,**stats)
    np.savez_compressed(output/'reference.npz',field=q,airway=a,offset_zyx=lo)
    meta=dict(schema='kv260.surface.scene.v2',packing='sparse_4x4x4_parity_bricks',result=str(result),input_sha256=pipeline['input_sha256'],airway_sha256=sha(result/'segmentation/airway_mask.nii.gz'),geometry=geometry,offset_xyz=lo[::-1].tolist(),shape_xyz=[nx,ny,nz],normal_computation='PL central differences and depth-aware screen filter',normal_matrix=normal_matrix(geometry).tolist(),scenes=scenes,events=report['branch_guidance']['events'],distance_quantization_mm=1/32,source_voxel_grid_preserved=True)
    write_json(output/'scene.json',meta);print(output/'scene.json')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixtures',action='store_true');p.add_argument('--result',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    if args.fixtures:fixtures();boundary_fixtures()
    elif args.result and args.output:prepare_case(args.result,args.output)
