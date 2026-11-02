"""Bounded slice overlap: PS graph work overlaps another slice's PL execution.

The XRT backend serializes each complete convolution transaction. Only PS work
and preparation run concurrently; at most two independent slice graphs exist.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor

def infer_slices(graph,inputs,workers=1):
    if workers==1:
        for z,x in inputs:yield z,graph(x)
        return
    if workers!=2:raise ValueError('Only one or two in-flight slices are supported')
    if not getattr(graph.backend,'output_pool',False) or not hasattr(graph.backend,'execution_lock'):
        raise ValueError('Slice overlap requires the serialized, leased XRT backend')
    pending=deque()
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='ct-slice') as pool:
        try:
            for z,x in inputs:
                pending.append((z,pool.submit(graph,x)))
                if len(pending)==workers:
                    index,future=pending.popleft();yield index,future.result()
            while pending:
                index,future=pending.popleft();yield index,future.result()
        finally:
            for _,future in pending:future.cancel()
