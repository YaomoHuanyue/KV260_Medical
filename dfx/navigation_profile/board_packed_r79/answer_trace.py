"""Persist actual complete outputs after timing, with no answer reuse."""
from pathlib import Path
from release import HERE,ROOT,SHA
class Trace:
    def __init__(self,host,contract):
        self.directory=HERE/('contract_trace_r79d_'+host) if contract else HERE/'board/trace_r79d'
        assert not self.directory.exists();self.directory.mkdir(parents=True);self.bindings={}
    def save(self,name,array):
        path=(self.directory/name).resolve();assert path.is_relative_to(self.directory.resolve())
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(array.tobytes(order='C'))
        assert path.stat().st_size==array.nbytes
        relative=path.relative_to(ROOT).as_posix();self.bindings[relative]=SHA(path)
        return dict(path=relative,sha256=self.bindings[relative],bytes=array.nbytes)
    def raw(self,policy,index,array):return self.save(f'raw/policy_{policy}/case_{index:02d}.bin',array)
    def answers(self,repeat,provider,distances,parents):
        name='PS'+str(provider) if isinstance(provider,int) else provider
        return dict(distances=self.save(f'answers/round_{repeat:02d}/{name}.f64',distances),
            parents=self.save(f'answers/round_{repeat:02d}/{name}.i32',parents))
