"""Bounded asynchronous submission with one owner of the shared DFX session."""
from collections import deque
from concurrent.futures import Future
from queue import Full
from threading import Condition,Thread


class AsyncSession:
    """The UI submits and returns; the worker alone opens, uses and closes XRT.

    A task must own its inputs until its Future completes. Running tasks cannot
    be cancelled: their DMA buffers and session stay alive until completion.
    Futures report completion/errors; GUI callbacks must dispatch to the GUI
    event thread. This wrapper never loads a bitstream on its own.
    """
    def __init__(self,session_factory,max_pending=2):
        if not isinstance(max_pending,int) or isinstance(max_pending,bool) or max_pending<1:
            raise ValueError('Positive pending-task bound required')
        self.ready=Future();self.closed=Future()
        self.ready.set_running_or_notify_cancel();self.closed.set_running_or_notify_cancel()
        self._condition=Condition();self._pending=deque();self._closing=False
        self._failed=None;self._maximum=max_pending
        self._thread=Thread(target=self._run,args=(session_factory,),name='navigation-streaming-owner',daemon=False)
        self._thread.start()

    def submit(self,function,*args,**kwargs):
        future=Future()
        with self._condition:
            if self._closing:raise RuntimeError('Streaming session is closing')
            if self._failed is not None:raise RuntimeError('Streaming session failed') from self._failed
            if len(self._pending)>=self._maximum:raise Full('Streaming pending-task queue is full')
            self._pending.append((future,function,args,kwargs))
            self._condition.notify()
        return future

    def close(self):
        """Return immediately; drain accepted work, then restore/close session."""
        with self._condition:
            self._closing=True;self._condition.notify()
        return self.closed

    def _run(self,factory):
        failure=None
        try:
            with factory() as session:
                self.ready.set_result(True)
                while True:
                    with self._condition:
                        while not self._pending and not self._closing:self._condition.wait()
                        if not self._pending:break
                        future,function,args,kwargs=self._pending.popleft()
                    if future.set_running_or_notify_cancel():
                        try:future.set_result(function(session,*args,**kwargs))
                        except BaseException as error:future.set_exception(error)
                    # Release request/buffer references before accepting more.
                    del future,function,args,kwargs
        except BaseException as error:
            failure=error
        with self._condition:
            self._failed=failure;self._closing=True
            pending=list(self._pending);self._pending.clear()
        if failure is not None:
            if not self.ready.done():self.ready.set_exception(failure)
            for future,_,_,_ in pending:
                if future.set_running_or_notify_cancel():future.set_exception(failure)
            self.closed.set_exception(failure)
        else:self.closed.set_result(True)
