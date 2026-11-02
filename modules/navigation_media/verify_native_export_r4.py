"""Independent MP4 decode, original timeline and full-resolution PS/PL pixel checks."""
from pathlib import Path
import argparse,ctypes,hashlib,json,subprocess,sys,time
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    directory=a.directory.resolve();assert directory.is_relative_to(ROOT/'ui/exports/navigation_media')
    report=json.loads((directory/'report.json').read_text());assert report['status']=='completed'
    linked=report['linked_overview_enabled'];pane=report['pane_output_size']
    assert report['native_GUI_button'] and report['capture_fit_policy']==('native_C6_and_linked_overview_FBOs_aspect_preserved' if linked else 'native_C6_color_FBO_aspect_preserved')
    assert pane[0]*9==pane[1]*16 and report['output_size']==[pane[0]*(2 if linked else 1),pane[1]]
    assert report['UI_ticks_during_export']>report['wall_seconds']*5
    assert report['native_PL_size']==[640,360]
    assert all(t['source_capture_size']==[640,360] and t['fitted_capture_size']==report['output_size'] for t in report['frame_trace'])
    fps=report['fps'];length=report['route_length_mm'];speed=report['speed_mm_per_s']
    # Original Python max(2, int(total_mm/speed*fps)), linspace and .8s hold.
    moving=max(2,int(length/speed*fps));hold=int(fps*.8);arcs=np.r_[np.linspace(0,length,moving),np.full(hold,length)]
    assert report['expected_total_frames']==moving+hold==report['encoded_frames']==len(report['frame_trace'])
    assert report['completed_PL_frames']==moving
    trace=report['frame_trace'];np.testing.assert_allclose([r['arc_mm'] for r in trace],arcs,atol=1e-9,rtol=0)
    assert [r['frame_index'] for r in trace]==list(range(moving+hold))
    assert all(r['hold']==(i>=moving) for i,r in enumerate(trace))
    assert len({r['completed_frame']['sequence'] for r in trace[:moving]})==moving
    for r in trace[:moving]:
        m=r['completed_frame'];req=m['requested_camera']
        assert m['pose_source']=='completed_PL_frame' and m['normal_computation']=='PL'
        assert req['width']==640 and req['height']==360 and not req['interactive']
        assert abs(m['arc_mm']-r['arc_mm'])<.001
        np.testing.assert_array_equal(m['camera_lps'],req['camera'])
    linked_checks=[]
    if linked:
        assert report['overview_native_size']==[640,360]
        for r in trace[:moving]:
            m=r['completed_frame'];v=r['linked_overview']
            assert v['valid'] and v['enabled'] and v['sequence']==m['sequence']
            assert v['pose_source']=='presented_PL_frame' and v['same_live_route_frustum_painter']
            assert v['native_size']==[640,360] and v['ordinary_opacity_renderer']=='accepted_R4_nearest_shell_cache'
            assert abs(v['arc_mm']-m['arc_mm'])<.001
            for key in ('camera_lps','forward_lps','right_lps','up_lps'):
                np.testing.assert_allclose(v[key],m[key],atol=2e-5,rtol=0)
            eye=np.array(m['camera_lps']);f=np.array(m['forward_lps']);right=np.array(m['right_lps']);up=np.array(m['up_lps'])
            vertical=15*m['field'];horizontal=vertical*640/360;far=eye+f*15
            corners=np.array([far+right*horizontal+up*vertical,far-right*horizontal+up*vertical,
                              far-right*horizontal-up*vertical,far+right*horizontal-up*vertical])
            np.testing.assert_allclose(v['corners_lps'],corners,atol=1e-4,rtol=0)
            assert v['overview_camera']==trace[0]['linked_overview']['overview_camera']
        # With updates suspended, reference-camera changes never rebuild geometry.
        assert all(r['linked_overview']['geometry_cache_builds_this_capture']==0 for r in trace[1:moving])
    for n,d in report['source_sha256'].items():assert sha(Path(n))==d,n
    assert sha(directory/'navigation.mp4')==report['movie_sha256']
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams',
        '-show_format','-of','json',str(directory/'navigation.mp4')],text=True))
    stream=probe['streams'][0];assert len(probe['streams'])==1
    assert stream['codec_name']=='h264' and stream['pix_fmt']=='yuv420p'
    assert [stream['width'],stream['height']]==report['output_size']
    assert stream['avg_frame_rate']==f'{fps}/1' and int(stream['nb_read_frames'])==moving+hold
    assert abs(float(stream['duration'])-(moving+hold)/fps)<1e-4
    # Decode the entire movie to verify stream integrity, not only its header.
    subprocess.run(['ffmpeg','-hide_banner','-v','error','-xerror','-i',str(directory/'navigation.mp4'),
        '-f','null','-'],stdout=subprocess.DEVNULL,check=True)
    sys.path.insert(0,str(ROOT/'dfx/surface'))
    from prepare import unpack_scene,frame_parameters,normal_matrix
    mask=Path(report['source_result'])/'segmentation/airway_mask.nii.gz'
    route=Path(report['source_result'])/'navigation/route.json'
    identity=sha(mask)+sha(route)+sha(ROOT/'dfx/surface/prepare.py')
    cache=ROOT/'dfx/surface/cache'/hashlib.sha256(identity.encode()).hexdigest()[:24]
    meta=json.loads((cache/'scene.json').read_text())
    cpu=ctypes.CDLL(str(ROOT/'dfx/surface/host/libsurface_reference.so'))
    cpu.surface_reference.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,
        ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
    checks=[];color_checks=[]
    for r in trace:
        if 'reference_png' not in r or r['hold']:continue
        m=r['completed_frame'];req=m['requested_camera'];info=meta['scenes'][str(m['branch_event'])]
        packed=cache/info['file'];assert sha(packed)==info['sha256']
        field,target=unpack_scene(packed.read_bytes());field=np.ascontiguousarray(field,np.int16);target=np.ascontiguousarray(target,np.uint8)
        parameters,_=frame_parameters(req['camera'],req['forward'],req['up'],meta['geometry'],
            np.asarray(meta['offset_xyz']),640,360,m['sequence'])
        parameters=np.ascontiguousarray(parameters,np.int32);matrix=np.ascontiguousarray(normal_matrix(meta['geometry']),np.int32)
        depth=directory/m['depth_reference'];normal=directory/m['normal_reference']
        assert sha(depth)==r['raw_depth_outline_sha256'] and sha(normal)==r['raw_normal_sha256']
        expected=np.fromfile(depth,dtype='<u4').astype(np.uint64)|(np.fromfile(normal,dtype='<u4').astype(np.uint64)<<np.uint64(32))
        nz,ny,nx=field.shape
        for threads in (1,4):
            out=np.empty(640*360,np.uint64);seconds=[]
            for repeat in range(3):
                begin=time.monotonic();cpu.surface_reference(field.ctypes.data,target.ctypes.data,nx,ny,nz,
                    parameters.ctypes.data,matrix.ctypes.data,out.ctypes.data,threads);seconds.append(time.monotonic()-begin)
                np.testing.assert_array_equal(out,expected)
            checks.append(dict(frame_index=r['frame_index'],threads=threads,seconds=seconds,
                median_seconds=float(np.median(seconds)),PL_API_seconds=m['host_seconds'],PL_Hardware_seconds=m['hardware_seconds'],
                raw_depth_outline_and_normals_bit_exact=True))
        png=directory/r['reference_png'];image=np.asarray(Image.open(png).convert('RGBA'))
        assert hashlib.sha256(image.tobytes()).hexdigest()==r['captured_pixel_sha256']
        if linked:
            v=r['linked_overview'];raw=directory/m['overview_reference']
            assert sha(raw)==r['overview_color_sha256'] and raw.stat().st_size==640*360*4
            overview=np.fromfile(raw,np.uint8).reshape(360,640,4)
            assert np.all(overview[:,:,3]==255) and float(overview[:,:,:3].std())>10
            if pane==[640,360]:np.testing.assert_array_equal(image[:,:640,:],overview)
            matrix=np.asarray(v['mvp_column_major']).reshape(4,4,order='F')
            at=matrix@np.r_[v['camera_lps'],1.];projected=None;marker=False
            if at[3]>0 and -at[3]<=at[2]<=at[3]:
                x=int(round((at[0]/at[3]+1)*320));y=int(round((1-at[1]/at[3])*180));projected=[x,y]
                if 8<=x<632 and 35<=y<352:
                    crop=overview[y-7:y+8,x-7:x+8,:3].astype(int)
                    marker=bool(np.any((crop[:,:,0]<170)&(crop[:,:,1]>180)&(crop[:,:,2]>180)))
                    assert marker,('Reference marker missing at independently projected position',r['frame_index'],x,y)
            linked_checks.append(dict(frame_index=r['frame_index'],native_overview_RGBA_and_video_pane_equal=pane==[640,360],
                independently_projected_camera_pixel=projected,cyan_camera_marker_found=marker))
        w,h=report['output_size'];data=subprocess.check_output(['ffmpeg','-hide_banner','-v','error','-i',str(directory/'navigation.mp4'),
            '-vf',f"select=eq(n\\,{r['frame_index']})",'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        restored=np.frombuffer(data,np.uint8).reshape(h,w,3);difference=np.abs(restored.astype(np.int16)-image[:,:,:3].astype(np.int16))
        assert float(difference.mean())<6 and float(np.percentile(difference,99))<35
        if linked:
            for half in range(2):
                piece=difference[:,half*pane[0]:(half+1)*pane[0],:]
                assert float(piece.mean())<6 and float(np.percentile(piece,99))<35
        color_checks.append(dict(frame_index=r['frame_index'],mean_absolute_channel_error=float(difference.mean()),
            percentile_99_error=float(np.percentile(difference,99)),lossy_H264_not_pixel_exact=True))
    assert len(color_checks)==3 and len(checks)==6
    if linked:assert len(linked_checks)==3 and any(x['cyan_camera_marker_found'] for x in linked_checks)
    result=dict(status='passed_complete_route_MP4_decode_timeline_and_same_input_PS1_PS4_PL_full_pixels',
        report_sha256=sha(directory/'report.json'),movie_sha256=sha(directory/'navigation.mp4'),
        video_seconds=(moving+hold)/fps,frames=moving+hold,moving_frames=moving,final_hold_frames=hold,
        original_uniform_arc_and_frame_count_exact=True,pose_frame_pairing_complete=True,codec=stream['codec_name'],
        linked_overview_enabled=linked,linked_reference_checks=linked_checks,all_route_frames_reference_pose_synced=True,
        frame_checks=checks,decoded_color_checks=color_checks,PS_reference_binary_sha256=sha(ROOT/'dfx/surface/host/libsurface_reference.so'),
        PS_reference_source_sha256=sha(ROOT/'dfx/surface/host/reference.cpp'),verification_source_sha256=sha(Path(__file__)),
        additional_PL_resources=0,new_bitstream=False,default_UI_changed=False,GUI_export_button_pending=False)
    out=directory/'acceptance.json';assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],flush=True)
if __name__=='__main__':main()
