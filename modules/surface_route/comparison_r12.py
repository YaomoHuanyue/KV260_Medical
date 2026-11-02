"""Reuse one proven root winding on the same immutable surface and exact point."""
import copy
import numpy as np
from modules.surface_route.comparison_r11 import Comparison as OriginalComparison


class RootRegion:
    def __init__(self,region,root,winding):
        self.region=region
        self.root=np.ascontiguousarray(root,dtype='<f8').tobytes()
        self.winding=copy.deepcopy(winding)
        self.reused=self.computed=0

    def __getattr__(self,name):
        return getattr(self.region,name)

    def root_winding(self,point):
        raw=np.ascontiguousarray(point,dtype='<f8')
        if raw.shape==(3,) and raw.tobytes()==self.root:
            self.reused+=1
            return copy.deepcopy(self.winding)
        self.computed+=1
        return self.region.root_winding(point)


class Comparison(OriginalComparison):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.region=RootRegion(self.region,self.c.points_lps_mm[self.raw.root],self.winding)

    def produce(self,*args,**kwargs):
        before=(self.region.reused,self.region.computed)
        whole,alternative,arrays=super().produce(*args,**kwargs)
        metrics=dict(reused_exact_same_root=self.region.reused-before[0],
            computed_other_roots=self.region.computed-before[1],
            first_root_proof_included_in_common_geometry_preparation=True,
            different_roots_or_meshes_never_reused=True)
        whole['root_winding_query_reuse']=metrics
        alternative['root_winding_query_reuse']=metrics
        return whole,alternative,arrays
