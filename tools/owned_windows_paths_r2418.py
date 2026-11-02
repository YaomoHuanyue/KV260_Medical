"""Extended filesystem paths inside one owned job, with normal logical names.

No registry, system preference, installed file, or other process is changed.
Only pathlib's class binding in this Python process is replaced. Native tool
arguments still use ordinary str()/as_posix() names; their short paths do not
need the filesystem-only prefix.
"""
import os,pathlib

OriginalWindowsPath=pathlib.WindowsPath


def install(owned_root):
    if os.name!='nt':raise RuntimeError('Windows-only owned path adapter')
    anchor=os.path.normcase(os.path.abspath(str(owned_root))).rstrip('\\/')
    if not os.path.isabs(anchor) or len(anchor)<10:raise ValueError('Explicit owned absolute root required')
    def normal(value):
        text=str(value)
        if text.startswith('\\\\?\\') and len(text)>6 and text[5]==':':
            candidate=text[4:]
            absolute=os.path.normcase(os.path.abspath(candidate))
            if absolute==anchor or absolute.startswith(anchor+'\\'):return candidate
        return text
    def native(value,force=False):
        text=normal(value);absolute=os.path.abspath(text)
        folded=os.path.normcase(absolute)
        inside=folded==anchor or folded.startswith(anchor+'\\')
        if inside and (force or len(absolute)>=240):return '\\\\?\\'+absolute
        return text
    class OwnedPath(OriginalWindowsPath):
        __slots__=()
        def __new__(cls,*args,**kwargs):return object.__new__(cls)
        def __init__(self,*args):
            OriginalWindowsPath.__init__(self,*(normal(p) if isinstance(p,(str,os.PathLike)) else p for p in args))
        def __fspath__(self):return native(str(self))
        def _tree_result(self,p):
            text=normal(p)
            if not self.is_absolute() and os.path.isabs(text):text=os.path.relpath(text,os.getcwd())
            return type(self)(text)
        def iterdir(self):
            for p in OriginalWindowsPath(native(str(self),True)).iterdir():yield self._tree_result(p)
        def glob(self,pattern,**kwargs):
            for p in OriginalWindowsPath(native(str(self),True)).glob(pattern,**kwargs):yield self._tree_result(p)
        def rglob(self,pattern,**kwargs):
            for p in OriginalWindowsPath(native(str(self),True)).rglob(pattern,**kwargs):yield self._tree_result(p)
    pathlib.Path=OwnedPath
    return OwnedPath
