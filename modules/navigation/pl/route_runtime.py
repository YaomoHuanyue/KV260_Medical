"""AXIS navigation scene/query protocol and result adapter; no silent PS fallback."""
import ctypes
import hashlib
from pathlib import Path
import sys
import time
import json
import numpy as np

NODES=4096
POINTS=4096
OUTPUT_WORDS=2+(NODES+7)//8+POINTS*2
SCENE_MAGIC=0x4e41565343454e31
QUERY_MAGIC=0x4e41565155455231


def encode_scene(c):
    if not 1<=len(c.points_lps_mm)<=NODES or len(c.edges)>=NODES:
        raise ValueError('PL navigation supports at most 4096 centerline nodes')
    if not np.all(np.isfinite(c.points_lps_mm)) or not np.all(np.isfinite(c.distance_mm)):
        raise ValueError('Nonfinite navigation scene')
    if not np.array_equal(c.distance_mm>0,c.mask):
        raise ValueError('PL field requires positive foreground distances and zero background')
    shape=np.array(c.mask.shape);tiles=(shape+3)//4
    if max(shape)>1024 or np.prod(tiles)>65536:
        raise ValueError('PL sparse scene tile table exceeds 65536 tiles')
    # Gather occupied bricks only, avoiding two full-volume padded copies.
    occupied=np.flatnonzero(c.mask)
    foreground_voxels=len(occupied)
    row,x=np.divmod(occupied,shape[2]);z,y=np.divmod(row,shape[1])
    present=np.unique(((z//4)*tiles[1]+y//4)*tiles[2]+x//4)
    if not 1<=len(present)<=4096:raise ValueError('PL navigation supports at most 4096 nonempty 4x4x4 bricks')
    block_z,block_y,block_x=np.unravel_index(present,tuple(tiles))
    offsets=np.arange(64)
    z=block_z[:,None]*4+offsets[None,:]//16
    y=block_y[:,None]*4+(offsets[None,:]//4)%4
    x=block_x[:,None]*4+offsets[None,:]%4
    valid=(z<shape[0])&(y<shape[1])&(x<shape[2])
    bricks=np.zeros((len(present),64),np.float32)
    bricks[valid]=c.distance_mm[z[valid],y[valid],x[valid]]
    # A forest has one unique route; reachability traversal equals weighted
    # Dijkstra for endpoint/path selection. Reject cycles instead of ignoring them.
    parents=np.arange(len(c.points_lps_mm))
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for u,v in c.edges:
        if min(u,v)<0 or max(u,v)>=len(parents):raise ValueError('Invalid graph edge')
        a,b=find(u),find(v)
        if a==b:raise ValueError('PL navigation requires the verified centerline forest')
        parents[a]=b
    nt=int(np.prod(tiles));n=len(c.points_lps_mm);ne=len(c.edges)
    data=np.zeros((4+n+(ne+7)//8+(nt+31)//32+len(bricks)*4,8),np.uint64)
    pack_dims=lambda dims:sum(int(v)<<(i*16) for i,v in enumerate(dims))
    data[0]=[SCENE_MAGIC,n,ne,c.root,pack_dims(shape[::-1]),pack_dims(tiles[::-1]),nt,len(bricks)]
    floats=data.view(np.float64)
    floats[1,:3]=c.geometry.to_lps(c.offset_zyx)
    floats[1,3:6]=c.geometry.spacing_xyz;floats[1,6]=min(c.geometry.spacing_xyz);floats[1,7]=c.resolution_margin_mm
    floats[2]=np.array(c.geometry.direction)[:8];floats[3,0]=c.geometry.direction[8]
    floats[4:4+n,:3]=c.points_lps_mm;floats[4:4+n,3]=c.radii_mm
    data[4:4+n,4]=c.components
    start=4+n
    data[start:start+(ne+7)//8].ravel()[:ne]=c.edges[:,0].astype(np.uint64)|(c.edges[:,1].astype(np.uint64)<<32)
    start+=(ne+7)//8
    table=np.zeros(nt,np.uint16);table[present]=np.arange(1,len(bricks)+1,dtype=np.uint16)
    data[start:start+(nt+31)//32].view(np.uint16).ravel()[:nt]=table;start+=(nt+31)//32
    data[start:].view(np.float32).ravel()[:bricks.size]=bricks.ravel()
    token=int.from_bytes(hashlib.sha256(data.tobytes()).digest()[:8],'little')
    data[3,7]=token
    return data,token,dict(bricks=len(bricks),tile_entries=nt,input_bytes=data.nbytes,
                           foreground_voxels=foreground_voxels,field_precision='original float32, no quantization')


def encode_query(target,token,scope_diameter_mm=1.,safety_margin_mm=.2,sample_mm=.5,narrow_weight=2.,smooth=True):
    numbers=np.array([scope_diameter_mm,safety_margin_mm,sample_mm,narrow_weight,6.],np.float64)
    if not np.all(np.isfinite(numbers)) or min(numbers)<0 or sample_mm<=0:
        raise ValueError('Require finite nonnegative scope/margin/weight and positive sample step')
    points=np.asarray(target.points_lps_mm,dtype=np.float64)
    if points.ndim!=2 or points.shape[1]!=3 or not 1<=len(points)<=65536 or not np.all(np.isfinite(points)):
        raise ValueError('PL target requires 1..65536 finite LPS surface points')
    packed=np.zeros(((len(points)+1)//2,8),np.float64)
    packed[:len(points[::2]),:3]=points[::2];packed[:len(points[1::2]),3:6]=points[1::2]
    data=np.zeros((2+len(packed)*2,8),np.uint64)
    kind={'manual_point':1,'lesion_candidate':2,'endpoint':3}.get(target.kind)
    if kind is None:raise ValueError('Unsupported PL target kind')
    data[0]=[QUERY_MAGIC,token,len(points),kind,int(smooth),POINTS,0,0]
    data.view(np.float64)[1,:5]=numbers
    data[2:2+len(packed)]=packed.view(np.uint64);data[2+len(packed):]=packed.view(np.uint64)
    return data


class NativeRoute:
    """HLS algorithm on the CPU for numerical checks, never a PL benchmark."""
    def __init__(self):
        path=Path(__file__).parent/'build'/('nav_model.dll' if sys.platform=='win32' else 'libnav_model.so')
        self.lib=ctypes.CDLL(str(path))
        self.lib.nav_native_route.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint]
        self.lib.nav_native_route.restype=ctypes.c_int
    def run_route(self,data,operation):
        output=np.zeros((1 if operation==0 else OUTPUT_WORDS,8),np.uint64)
        start=time.perf_counter();status=self.lib.nav_native_route(data.ctypes.data,output.ctypes.data,len(data),len(output),operation)
        return output,dict(status=status,host_run_seconds=time.perf_counter()-start,hardware_seconds=None,kind='CPU native HLS model')
    def close(self):pass


def available(package=None):
    from .runtime import available as edt_available
    try:
        package=Path(__file__).parent/'package' if package is None else Path(package)
        manifest=json.loads((package/'manifest.json').read_text())
        return edt_available(package) and manifest.get('route_core')=='nav_route.v1'
    except (OSError,ValueError):return False


from .runtime import XRTSession


class RouteXRT(XRTSession):
    def __init__(self,package=None):
        if not available(package):raise RuntimeError('Navigation route firmware not loaded or mismatched; no XRT/MMIO access')
        super().__init__(package)
        self.lib.nav_route_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*3),
            ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),ctypes.c_char_p,ctypes.c_size_t]
        self.lib.nav_route_run.restype=ctypes.c_int
    def run_route(self,data,operation):
        if data.dtype!=np.uint64 or data.ndim!=2 or data.shape[1]!=8 or not data.flags.c_contiguous:
            raise ValueError('Invalid route AXIS packet buffer')
        output=np.empty((1 if operation==0 else OUTPUT_WORDS,8),np.uint64)
        error=ctypes.create_string_buffer(2048);hardware=ctypes.c_double();host=ctypes.c_double()
        result=self.lib.nav_route_run(self.handle,data.ctypes.data,output.ctypes.data,len(data),len(output),operation,
            ctypes.byref(hardware),ctypes.byref(host),error,len(error))
        if result<0:raise RuntimeError(error.value.decode(errors='replace'))
        return output,dict(status=result,hardware_seconds=hardware.value,host_run_seconds=host.value,kind='actual_kv260')


class RoutePlanner:
    def __init__(self,c,session):
        self.c=c;self.session=session
        start=time.perf_counter();data,self.token,self.scene_info=encode_scene(c)
        self.scene_info['pack_seconds']=time.perf_counter()-start
        output,stats=session.run_route(data,0)
        if stats['status'] or output[0,0]:raise RuntimeError('PL scene load failed: '+str(stats))
        if int(output[0,1])!=self.token:raise RuntimeError('PL scene token mismatch')
        self.scene_info['load']=stats
    def plan(self,target,**options):
        start=time.perf_counter();data=encode_query(target,self.token,**options)
        output,stats=self.session.run_route(data,1);error=int(output[0,0])|stats['status']
        if error:
            if error&8:raise ValueError('Manual target is more than 5 mm from the centerline; use a lesion candidate or a closer waypoint')
            raise RuntimeError('Navigation PL capacity/protocol error '+str(error))
        _,n,nids,desired,end,reason,reachable,smooth=map(int,output[0]);v=output.view(np.float64)
        if n>POINTS or nids>NODES:raise RuntimeError('Malformed PL route lengths')
        ids_words=(nids+7)//8 if v[1,6]==2 else (NODES+7)//8
        offset=2+ids_words
        rows=v[offset:offset+n*2].reshape(n,2,8)
        points=rows[:,0,:3].copy();radii=rows[:,0,4].astype(np.float32);arc=rows[:,0,3].copy()
        ids=output[2:offset].ravel()[:nids].astype(np.int32)
        stats.update(wire_output_words=offset+n*2,wire_output_bytes=(offset+n*2)*64,edge_cache_reused=bool(v[1,7]))
        if len(points)>2:
            diff=np.diff(points,axis=0);norm=np.linalg.norm(diff,axis=1)
            angles=np.arccos(np.clip(np.sum(diff[:-1]*diff[1:],axis=1)/np.maximum(norm[:-1]*norm[1:],1e-12),-1,1))
            curvature=float(np.max(angles/np.maximum(.5*(norm[:-1]+norm[1:]),1e-12)))
        else:curvature=0.
        reasons={0:None,1:'disconnected_target_component',2:'insufficient_root_clearance',3:'insufficient_route_clearance',4:'continuous_route_clearance_failed'}
        why=reasons[reason];status='limited_reach' if why and n>1 else ('unreachable' if why else ('airway_approach' if target.kind=='lesion_candidate' else 'route_found'))
        scope=options.get('scope_diameter_mm',1.);safety=options.get('safety_margin_mm',.2)
        required=float(v[1,4]);margin=float(v[1,5]);c=self.c
        report=dict(schema='kv260.navigation.route.v1',backend='pl_route' if stats['kind']=='actual_kv260' else 'native_route_model',status=status,reason=why,
            target_kind=target.kind,target=target.metadata,requested_endpoint_id=desired,selected_endpoint_id=end if end<len(c.points_lps_mm) else None,
            requested_endpoint_lps_mm=c.points_lps_mm[desired].tolist(),closest_centerline_gap_mm=float(v[1,2]),
            final_target_gap_mm=float(v[1,3]) if n else None,length_mm=float(v[1,0]),point_count=n,
            minimum_edt_radius_mm=float(radii.min()) if n else None,minimum_adjusted_radius_mm=float(np.maximum(0,radii-margin).min()) if n else None,
            scope_diameter_mm=scope,safety_margin_mm=safety,required_radius_mm=required,resolution_margin_mm=margin,
            reachable_centerline_points=reachable,total_centerline_points=len(c.points_lps_mm),smoothing_accepted=bool(smooth),
            max_discrete_curvature_per_mm=curvature,target_points_lps_mm=target.points_lps_mm.tolist() if target.kind!='lesion_candidate' else [],
            quality_status='experimental_geometry_only',warnings=list(c.metadata.get('warnings',[])),
            planning_mode='clearance_estimate' if required>0 else 'virtual_point_exploration',pl_job=stats,
            ps_remaining='target mask loading/components, report formatting/curvature, guidance preparation and browser display')
        if why:report['warnings'].append('Displayed route is the reachable approach only; requested endpoint was not reached')
        if target.kind=='lesion_candidate':report['warnings'].append('Route ends inside airway near candidate; it does not enter or reach an external lesion')
        route=dict(points_lps_mm=points,radius_mm=radii,arc_mm=arc,centerline_point_ids=ids)
        camera=dict(position_lps_mm=points.copy() if n>1 else np.empty((0,3)),
                    forward_lps=rows[:,0,5:8].copy() if n>1 else np.empty((0,3)),
                    up_lps=rows[:,1,:3].copy() if n>1 else np.empty((0,3)))
        report['pl_job']['plan_adapter_total_seconds']=time.perf_counter()-start
        return report,route,camera
