"""Small control/footer ABI; bulk vertices remain a zero-copy buffer view."""
from dataclasses import dataclass
import operator
import struct

MAGIC=0x3141434d
MAX_DIM=512
MAX_TRIANGLES=9*511**3
MAX_INPUT_WORDS=512**3//64


def uint(value,name):
    if isinstance(value,bool):raise ValueError(name+' must be an integer, not bool')
    try:n=operator.index(value)
    except TypeError as e:raise ValueError(name+' must be an integer') from e
    if not 0<=n<=0xffffffff:raise ValueError(name+' is outside uint32')
    return n


@dataclass(frozen=True)
class Plan:
    nx:int
    ny:int
    nz:int
    capacity:int
    count_only:bool
    expected:int
    input_words:int
    output_words:int

    @property
    def input_bytes(self):return self.input_words*64
    @property
    def output_bytes(self):return self.output_words*64
    @property
    def voxels(self):return self.nx*self.ny*self.nz
    @property
    def arguments(self):
        return ((0x10,self.nx),(0x18,self.ny),(0x20,self.nz),(0x28,self.capacity),
                (0x30,int(self.count_only)),(0x38,self.expected),(0x40,self.input_words))


def plan(dimensions_xyz,*,count_only=True,capacity=0,expected=0,max_output_bytes=512*1024**2):
    if type(count_only) is not bool:raise ValueError('count_only must be bool')
    dimensions=tuple(dimensions_xyz)
    if len(dimensions)!=3:raise ValueError('Three XYZ dimensions required')
    nx,ny,nz=(uint(v,'dimension') for v in dimensions)
    if min(nx,ny,nz)<2 or max(nx,ny,nz)>MAX_DIM:raise ValueError('Dimensions must be in [2,512]')
    capacity=uint(capacity,'capacity');expected=uint(expected,'expected')
    if expected>9*(nx-1)*(ny-1)*(nz-1):raise ValueError('Expected count exceeds geometric bound')
    if count_only and (capacity or expected):raise ValueError('Count pass has no vertex allocation')
    if not count_only and capacity!=expected:raise ValueError('Production requires the exact successful count')
    if isinstance(max_output_bytes,bool) or operator.index(max_output_bytes)<64:raise ValueError('Invalid output budget')
    target=0 if count_only else capacity*3
    output_words=(target+7)//8+1
    if output_words*64>max_output_bytes:raise ValueError('MC output exceeds explicit allocation budget')
    return Plan(nx,ny,nz,capacity,count_only,expected,(nx*ny*nz+63)//64,output_words)


class FrameError(ValueError):
    def __init__(self,status,required,written):
        super().__init__(f'MC rejected output: status=0x{status:x}, required={required}, written={written}')
        self.status=status;self.required=required;self.written=written


@dataclass(frozen=True)
class Result:
    required:int
    written:int
    vertices:memoryview


def decode(payload,configuration):
    # Require the canonical validated plan, including the explicit memory bound.
    p=configuration
    if not isinstance(p,Plan):raise ValueError('Validated MC plan required')
    if p!=plan((p.nx,p.ny,p.nz),count_only=p.count_only,capacity=p.capacity,
               expected=p.expected,max_output_bytes=p.output_bytes):raise ValueError('Forged transfer plan')
    try:data=memoryview(payload).cast('B')
    except (TypeError,ValueError) as e:raise ValueError('Contiguous output bytes required') from e
    if len(data)!=p.output_bytes:raise ValueError('MC DMA byte count mismatch')
    f=struct.unpack_from('<16I',data,len(data)-64)
    if f[:2]!=(MAGIC,1) or f[14:]!=(0,0):raise ValueError('MC footer version/reserved mismatch')
    if f[5:13]!=(p.nx,p.ny,p.nz,p.input_words,p.output_words,p.capacity,int(p.count_only),p.expected):
        raise ValueError('MC footer/configuration mismatch')
    error,required,written=f[2:5]
    if required>9*(p.nx-1)*(p.ny-1)*(p.nz-1) or written>required or f[13]!=written*3:
        raise ValueError('MC count bound mismatch')
    if error:raise FrameError(error,required,written)
    if (p.count_only and written) or (not p.count_only and (required!=p.expected or written!=p.expected)):
        raise ValueError('MC successful footer has inconsistent counts')
    vertex_bytes=written*24
    # At most 56 bytes: do not scan/copy a large vertex volume in Python.
    if any(data[vertex_bytes:len(data)-64]):raise ValueError('MC nonzero logical output tail')
    return Result(required,written,data[:vertex_bytes].toreadonly())
