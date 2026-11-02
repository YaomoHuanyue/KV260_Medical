"""Geometry, semantics, invalid input, and third-party VTK reader acceptance."""
from pathlib import Path
import argparse,hashlib,json,sys,tempfile,unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_export.vtp import write_vtp
from modules.surface_export.readback import readback
from modules.surface_export.export import export_surfaces,generation_rgb,sha

class Tests(unittest.TestCase):
    def test_noncontiguous_exact_geometry_and_missing_probability(self):
        points=np.arange(45,dtype=np.float32).reshape(-1,3)[::3]
        faces=np.array([[0,1,2],[2,3,4]],np.uint32)
        attrs={'generation':np.array([0,1,2,7,-1],np.int16),
               'network_probability':np.array([.7,.2,-1,1,-1],np.float32)}
        attrs['RGB']=generation_rgb(attrs['generation'],np.array([1,1,1,1,0]))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            assert Path(t).resolve().is_relative_to(Path(__file__).parent.resolve())
            p=Path(t)/'mesh.vtp';write_vtp(p,points,faces,attrs)
            r=readback(p)
            np.testing.assert_array_equal(r['Points'],points)
            np.testing.assert_array_equal(r['connectivity'].reshape(-1,3),faces)
            for k,v in attrs.items():np.testing.assert_array_equal(r[k],v)
    def test_invalid_geometry_and_attributes_do_not_create_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            assert Path(t).resolve().is_relative_to(Path(__file__).parent.resolve())
            p=Path(t)/'bad.vtp';points=np.eye(3,dtype=np.float32);attrs={'RGB':np.zeros((3,3),np.uint8)}
            for faces,values in (([[0,1,3]],attrs),([[0,1,2]],{'RGB':np.zeros((2,3),np.uint8)})):
                with self.assertRaises(ValueError):write_vtp(p,points,np.array(faces,np.int32),values)
                self.assertFalse(p.exists())
    def test_incomplete_file_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            assert Path(t).resolve().is_relative_to(Path(__file__).parent.resolve())
            p=Path(t)/'bad.vtp';p.write_bytes(b'<VTKFile><AppendedData encoding="raw">_')
            with self.assertRaises(ValueError):readback(p)
    def test_wrong_CT_and_source_destination_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            assert Path(t).resolve().is_relative_to(Path(__file__).parent.resolve())
            s=Path(t)/'source';s.mkdir()
            (s/'pipeline.json').write_text(json.dumps({'status':'passed','input_sha256':'aaa'}))
            for dest,digest in ((Path(t)/'out','bbb'),(s/'out','aaa'),(Path(t),'aaa')):
                with self.assertRaises(ValueError):export_surfaces(s,dest,digest)
            self.assertFalse((s/'out').exists());self.assertFalse((Path(t)/'out').exists())

def verify_bundle(source,bundle,ui_attributes=None,require_vtk=False):
    source=Path(source);bundle=Path(bundle)
    report=json.loads((bundle/'report.json').read_text(encoding='utf-8'))
    assert report['status']=='completed' and report['schema']=='kv260.surface_export.v1'
    for n,d in report['source_files_sha256'].items():assert sha(source/n)==d
    for n,d in report['files'].items():assert sha(bundle/n)==d
    vtk=None
    if require_vtk:
        from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
        from vtkmodules.util.numpy_support import vtk_to_numpy
        vtk=(vtkXMLPolyDataReader,vtk_to_numpy)
    checks={}
    for name,info in report['structures'].items():
        r=readback(bundle/info['file'])
        with np.load(source/'reconstruction'/(name+'.npz'),allow_pickle=False) as mesh:
            np.testing.assert_array_equal(r['Points'],mesh['points'])
            np.testing.assert_array_equal(r['Normals'],mesh['normals'])
            np.testing.assert_array_equal(r['connectivity'].reshape(-1,3),mesh['faces'])
            faces=mesh['faces']
        if vtk:
            reader=vtk[0]();errors=[]
            reader.AddObserver('ErrorEvent',lambda *args:errors.append(True))
            reader.SetFileName(str(bundle/info['file']));reader.Update()
            poly=reader.GetOutput();assert not errors and reader.GetErrorCode()==0
            assert poly.GetNumberOfPoints()==info['points'] and poly.GetNumberOfPolys()==info['triangles']
            np.testing.assert_array_equal(vtk[1](poly.GetPoints().GetData()),r['Points'])
            np.testing.assert_array_equal(vtk[1](poly.GetPolys().GetConnectivityArray()),r['connectivity'])
            for key in info['point_arrays']:
                np.testing.assert_array_equal(vtk[1](poly.GetPointData().GetArray(key)),r[key])
            assert poly.GetPointData().GetScalars().GetName()=='RGB'
        ui_exact=None
        if name=='airway':
            assert set(r['generation'])<=set(range(8))|{-1}
            assert np.all((r['network_probability']==-1)|((r['network_probability']>=0)&(r['network_probability']<=1)))
            np.testing.assert_array_equal(r['RGB'],generation_rgb(r['generation'],r['connected_to_root']))
            if ui_attributes:
                ui=np.fromfile(ui_attributes,'<f4').reshape(-1,4)
                index=faces.reshape(-1)
                actual=np.column_stack([r[k][index] for k in (
                    'generation','radius_mm','network_probability','connected_to_root')])
                np.testing.assert_array_equal(actual,ui);ui_exact=True
        checks[name]=dict(points=info['points'],triangles=info['triangles'],
            source_coordinates_normals_and_triangles_exact=True,
            third_party_VTK_reader_exact=bool(vtk),all_attribute_arrays_exact=bool(vtk),
            original_UI_expanded_attributes_exact=ui_exact)
    return checks

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--bundle',type=Path)
    p.add_argument('--ui-attributes',type=Path);p.add_argument('--require-vtk',action='store_true')
    p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    assert not a.receipt.exists()
    run=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    assert run.wasSuccessful()
    checks=verify_bundle(a.source,a.bundle,a.ui_attributes,a.require_vtk) if a.source else {}
    paths=[Path(__file__),Path(__file__).with_name('readback.py'),
           Path(__file__).with_name('export.py'),Path(__file__).with_name('vtp.py'),ROOT/'ui/features/analysis.py']
    record=dict(status='surface_export_strict_roundtrip_passed',unit_tests=run.testsRun,
        structures=checks,third_party_VTK_required=a.require_vtk,
        source_sha256={str(n.relative_to(ROOT)):sha(n) for n in paths},
        bundle_report_sha256=sha(a.bundle/'report.json') if a.bundle else None,
        additional_PL_resources=0,existing_UI_unchanged=True)
    if a.ui_attributes:record['UI_attribute_file_sha256']=sha(a.ui_attributes)
    a.receipt.parent.mkdir(parents=True,exist_ok=True)
    a.receipt.write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'],checks)

if __name__=='__main__':main()
