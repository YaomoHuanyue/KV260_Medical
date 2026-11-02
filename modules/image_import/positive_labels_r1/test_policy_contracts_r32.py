"""Original input regressions, topology, and derived positive-label contracts."""
from pathlib import Path
import copy, json, shutil, unittest
from unittest.mock import patch
import numpy as np
import SimpleITK as sitk
from modules.image_import.positive_labels_r1 import test_importer as core
from modules.image_import.positive_labels_r1 import policy, importer, contracts


def setup(self):
    core.setup(self)
    for module in (core.full, core.partial):
        replacement=patch.object(module,'import_bundle',policy.import_bundle)
        replacement.start();self.addCleanup(replacement.stop)


class FullPolicy(core.FullCompatibility):
    setUp=setup


class PartialPolicy(core.PartialCompatibility):
    setUp=setup


class PositivePolicy(core.PositiveLabels):
    setUp=setup


class Fixture(unittest.TestCase):
    setUp=setup
    tearDown=core.full.ImportTests.tearDown
    run_spec=core.full.ImportTests.run_spec
    probability=core.full.ImportTests.probability

    def write_image(self,path,array):
        # The inherited fixture has an image instance named self.image.
        value=sitk.GetImageFromArray(array);value.CopyInformation(self.image)
        sitk.WriteImage(value,str(path),True)

    def select(self,names,positive=True):
        self.spec['images']={n:self.spec['images'][n] for n in names}
        if positive:
            for n,item in self.spec['images'].items():
                path=self.inputs/(n+'_labels.nrrd')
                self.write_image(path,np.where(self.mask,255,-3).astype(np.int16))
                item.update(selection='positive_mask',mask=dict(file=path.name,sha256=importer.sha(path)))

    def derive(self,source,leaf='derived'):
        target=self.folder/leaf
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('external_import.json'))
        pipeline=importer.read(target/'pipeline.json')
        pipeline['external_segmentation_report_sha256']=importer.sha(target/'segmentation/report.json')
        importer.write(target/'pipeline.json',pipeline)
        return target

    def change_report(self,target,change):
        path=target/'segmentation/report.json';report=importer.read(path);change(report)
        importer.write(path,report);pipeline=importer.read(target/'pipeline.json')
        pipeline['external_segmentation_report_sha256']=importer.sha(path)
        importer.write(target/'pipeline.json',pipeline)


class ProbabilityPolicy(Fixture):
    def test_malformed_manifests_are_value_errors_without_output(self):
        variants=[[],None,dict(self.spec,images=[]),dict(self.spec,images=None),
                  dict(self.spec,images={'airway':[]}),dict(self.spec,images={'airway':None})]
        for index,value in enumerate(variants):
            importer.write(self.manifest,value);target=self.folder/('malformed'+str(index))
            with self.assertRaises(ValueError):policy.import_bundle(self.ct,self.manifest,target)
            self.assertFalse(target.exists())
        self.assertFalse(list(self.folder.glob('.*.airway_policy_*')))

    def test_existing_output_and_input_directory_are_immutable(self):
        values=np.ones(self.array.shape,np.float32);self.probability(values)
        self.spec['images']['airway']['selection']='probability_threshold';importer.write(self.manifest,self.spec)
        target=self.folder/'existing';target.mkdir();marker=target/'retained.txt';marker.write_text('retained')
        with self.assertRaises(FileExistsError):policy.import_bundle(self.ct,self.manifest,target)
        self.assertEqual(marker.read_text(),'retained')
        with self.assertRaises(ValueError):policy.import_bundle(self.ct,self.manifest,self.inputs/'nested_output')
        self.assertFalse((self.inputs/'nested_output').exists())

    def run_probability(self,values,expected,name='airway',provided=False):
        self.spec['images']={name:self.spec['images'][name]}
        path=self.inputs/'values.nrrd';self.write_image(path,values)
        item=dict(selection='probability_threshold',probability=dict(file=path.name,sha256=importer.sha(path),threshold=.5))
        if provided:item['mask']=copy.deepcopy(self.spec['images'][name]['mask'])
        self.spec['images'][name]=item
        before=importer.sha(path);folder,report=self.run_spec()
        actual=sitk.ReadImage(str(folder/'segmentation'/f'{name}_mask.nii.gz'))
        np.testing.assert_array_equal(sitk.GetArrayFromImage(actual),expected)
        self.assertTrue(importer.same_geometry(importer.geometry(actual),importer.geometry(self.image)))
        saved=sitk.GetArrayFromImage(sitk.ReadImage(str(folder/'segmentation'/f'{name}_probability.nrrd')))
        self.assertEqual(saved.dtype,values.dtype);self.assertEqual(saved.tobytes(),values.tobytes())
        self.assertEqual(importer.sha(path),before)
        report2,inputs=contracts.validate_selected_masks(self.ct,folder)
        self.assertEqual(inputs[name]['foreground_voxels'],int(np.count_nonzero(expected)))
        self.assertEqual(report2['images'][name]['selection'],'probability_threshold')
        derived=self.derive(folder);contracts.validate_selected_masks(self.ct,derived)
        return folder,report

    def test_islands_removed_and_raw_probability_bits_preserved(self):
        values=np.full(self.array.shape,.1,np.float64);values[2:5,3:6,3:6]=.9;values[6,7,8]=.8
        expected=self.mask.copy();_,report=self.run_probability(values,expected,provided=True)
        row=report['images']['airway']['postprocessing']
        self.assertEqual((row['raw_threshold_voxels'],row['kept_voxels'],row['removed_voxels']),(28,27,1))
        self.assertTrue(row['raw_probability_bits_preserved'] and row['no_added_voxels_or_bridges'])

    def test_diagonal_26_and_exact_float64_threshold(self):
        values=np.zeros(self.array.shape,np.float64)
        values[1,1,1]=np.nextafter(.5,0);values[2,2,2]=.5;values[3,3,3]=np.nextafter(.5,1)
        values[6,7,8]=1;expected=np.zeros(self.array.shape,np.uint8);expected[2,2,2]=expected[3,3,3]=1
        self.run_probability(values,expected)

    def test_equal_components_keep_the_existing_stable_first_policy(self):
        values=np.zeros(self.array.shape,np.float32);values[1,1,1]=values[6,7,8]=1
        expected=np.zeros(self.array.shape,np.uint8);expected[1,1,1]=1
        self.run_probability(values,expected)

    def test_empty_probability_adds_no_foreground(self):
        self.run_probability(np.zeros(self.array.shape,np.float32),np.zeros(self.array.shape,np.uint8))

    def test_lung_probability_is_not_airway_filtered(self):
        values=np.zeros(self.array.shape,np.float32);values[1,1,1]=values[6,7,8]=1
        _,report=self.run_probability(values,(values>=.5).astype(np.uint8),name='lung')
        self.assertNotIn('postprocessing',report['images']['lung'])

    def test_nodule_probability_is_not_airway_filtered(self):
        values=np.zeros(self.array.shape,np.float32);values[1,1,1]=values[6,7,8]=1
        _,report=self.run_probability(values,(values>=.5).astype(np.uint8),name='nodule')
        self.assertNotIn('postprocessing',report['images']['nodule'])

    def test_bad_probability_and_wrong_CT_leave_no_output_or_policy_scratch(self):
        self.spec['images']={'airway':self.spec['images']['airway']}
        for number,value in enumerate((np.nan,np.inf,-.01,1.01)):
            values=np.zeros(self.array.shape,np.float64);values[1,1,1]=value;self.probability(values)
            self.spec['images']['airway']['selection']='probability_threshold'
            with self.assertRaises(ValueError):self.run_spec(output='bad'+str(number))
            self.assertFalse((self.folder/('bad'+str(number))).exists())
        self.probability(np.ones(self.array.shape,np.float64));self.spec['ct_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CT SHA256'):self.run_spec(output='wrong')
        self.assertFalse(list(self.folder.glob('.*.airway_policy_*')))


class DerivedContracts(Fixture):
    def test_each_partial_and_all_structures_preserve_positive_selection(self):
        original=copy.deepcopy(self.spec)
        for index,names in enumerate([['lung'],['airway'],['nodule'],['airway','nodule'],['lung','airway','nodule']]):
            self.spec=copy.deepcopy(original);self.select(names)
            folder,_=self.run_spec(output='input'+str(index));derived=self.derive(folder,'derived'+str(index))
            for target in [folder,derived]:
                report,inputs=contracts.validate_selected_masks(self.ct,target)
                self.assertEqual(list(inputs),names)
                for n in names:
                    self.assertEqual(report['images'][n]['selection'],'positive_mask')
                    self.assertEqual(inputs[n]['foreground_voxels'],27)
                for n in {'lung','airway','nodule'}-set(names):
                    self.assertFalse((target/'segmentation'/f'{n}_mask.nii.gz').exists())
                if {'airway','nodule'}.issubset(names):contracts.require_navigation(self.ct,target)

    def test_old_derived_gap_reproduced_and_candidate_accepts_canonical_mask(self):
        self.select(['airway']);folder,_=self.run_spec();derived=self.derive(folder)
        from modules.image_import.partial_r1 import contracts as old
        with self.assertRaisesRegex(ValueError,'Invalid partial selection'):old.validate_selected_masks(self.ct,derived)
        contracts.validate_selected_masks(self.ct,derived)

    def test_positive_conversion_fields_cannot_change(self):
        self.select(['airway']);folder,_=self.run_spec()
        for index,(field,value) in enumerate([('rule','nonzero'),('explicitly_selected',False),('negative_values','foreground'),('source_dtype',None)]):
            derived=self.derive(folder,'bad'+str(index))
            self.change_report(derived,lambda r:r['images']['airway']['mask_conversion'].__setitem__(field,value))
            with self.assertRaisesRegex(ValueError,'conversion changed'):contracts.validate_selected_masks(self.ct,derived)

    def test_binary_selection_cannot_claim_undeclared_conversion(self):
        self.select(['airway'],positive=False);folder,_=self.run_spec();derived=self.derive(folder)
        self.change_report(derived,lambda r:r['images']['airway'].__setitem__('mask_conversion',dict(rule='greater_than_zero')))
        with self.assertRaisesRegex(ValueError,'Undeclared'):contracts.validate_selected_masks(self.ct,derived)

    def test_wrong_CT_report_inventory_and_availability_are_rejected(self):
        self.select(['airway']);folder,_=self.run_spec()
        for index,field in enumerate(['input_sha256','external_segmentation_report_sha256','available_structures']):
            derived=self.derive(folder,'bad'+str(index));p=derived/'pipeline.json';data=importer.read(p)
            data[field]=['lung'] if field=='available_structures' else '0'*64;importer.write(p,data)
            with self.assertRaises(ValueError):contracts.validate_selected_masks(self.ct,derived)
        derived=self.derive(folder,'inventory')
        self.change_report(derived,lambda r:r['files'].__setitem__('segmentation/unknown.nrrd','0'*64))
        with self.assertRaisesRegex(ValueError,'inventory'):contracts.validate_selected_masks(self.ct,derived)

    def test_binary_data_geometry_and_foreground_count_are_checked(self):
        self.select(['airway']);folder,_=self.run_spec()
        for index,kind in enumerate(['nonbinary','geometry','count']):
            derived=self.derive(folder,'bad'+str(index));path=derived/'segmentation/airway_mask.nii.gz'
            if kind!='count':
                image=sitk.ReadImage(str(path))
                if kind=='nonbinary':
                    a=sitk.GetArrayFromImage(image);a[1,1,1]=2;value=sitk.GetImageFromArray(a);value.CopyInformation(image);image=value
                else:image.SetOrigin((111.,-70.,35.))
                sitk.WriteImage(image,str(path),True)
                self.change_report(derived,lambda r:r['files'].__setitem__('segmentation/airway_mask.nii.gz',importer.sha(path)))
            else:self.change_report(derived,lambda r:r['images']['airway'].__setitem__('foreground_voxels',28))
            with self.assertRaises(ValueError):contracts.validate_selected_masks(self.ct,derived)

    def test_missing_or_empty_navigation_structures_are_refused(self):
        original=copy.deepcopy(self.spec)
        for index,names in enumerate([['airway'],['nodule'],['airway','nodule'],['airway','nodule']]):
            self.spec=copy.deepcopy(original);self.select(names)
            if index>=2:
                n='airway' if index==2 else 'nodule';path=self.inputs/(n+'_empty.nrrd')
                self.write_image(path,np.full(self.array.shape,-1,np.int16))
                self.spec['images'][n]['mask']=dict(file=path.name,sha256=importer.sha(path))
            folder,_=self.run_spec(output='input'+str(index));derived=self.derive(folder,'derived'+str(index))
            with self.assertRaises(ValueError):contracts.require_navigation(self.ct,derived)

    def test_undeclared_mask_file_is_refused(self):
        self.select(['airway']);folder,_=self.run_spec();derived=self.derive(folder)
        shutil.copyfile(derived/'segmentation/airway_mask.nii.gz',derived/'segmentation/lung_mask.nii.gz')
        with self.assertRaisesRegex(ValueError,'Unexpected undeclared'):contracts.validate_selected_masks(self.ct,derived)

    def test_derived_bundle_does_not_require_external_producer_files(self):
        self.select(['airway','nodule']);folder,_=self.run_spec();derived=self.derive(folder)
        shutil.rmtree(self.inputs);contracts.require_navigation(self.ct,derived)


if __name__=='__main__':unittest.main()
