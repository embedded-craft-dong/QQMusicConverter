"""Opt-in scan of QQMusic readable memory for authst session fields.
No process modifications, memory dumps, login-token files or token logging.
"""
import ctypes as C
from ctypes import wintypes as W
import re, subprocess, time
from job import checkpoint

SCAN_LIMIT = 512 * 1024 * 1024
SCAN_SECONDS = 12
CHUNK_SIZE = 1024 * 1024
OVERLAP = 8192
PATTERN = re.compile(rb'"authst"\s*:\s*"([A-Za-z0-9+/=_-]{20,2048})"')


def scan_chunks(start, end, budget):
    """Count overlap and failed attempts toward the strict byte budget."""
    pos = start
    while pos < end and budget > 0:
        size = min(CHUNK_SIZE + OVERLAP, end - pos, budget)
        yield pos, size
        budget -= size
        pos += CHUNK_SIZE


def extract_tokens(data):
    tokens = {x.decode('ascii') for x in PATTERN.findall(data)}
    if b'a\0u\0t\0h\0s\0t\0' in data:
        for offset in (0, 1):
            text = data[offset:].decode('utf-16le', errors='ignore').encode('ascii', errors='ignore')
            tokens.update(x.decode('ascii') for x in PATTERN.findall(text))
    return tokens

def session_candidates(args=None):
    checkpoint(args)
    pid=int(subprocess.check_output(['powershell','-NoProfile','-Command','(Get-Process QQMusic | Select-Object -First 1).Id'],text=True,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=5).strip())
    checkpoint(args)
    k=C.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    class MBI(C.Structure):
        _fields_=[('BaseAddress',C.c_void_p),('AllocationBase',C.c_void_p),('AllocationProtect',W.DWORD),('PartitionId',W.WORD),('RegionSize',C.c_size_t),('State',W.DWORD),('Protect',W.DWORD),('Type',W.DWORD)]
    k.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t];k.VirtualQueryEx.restype=C.c_size_t
    h=k.OpenProcess(0x410,False,pid)
    if not h: raise RuntimeError('无法读取当前 QQ 音乐进程；请以相同权限运行，或使用 --ekey-file。')
    tokens=set();address=0;attempted=0
    deadline = time.monotonic() + SCAN_SECONDS
    try:
        while address<0x7fffffffffff and attempted < SCAN_LIMIT and time.monotonic() < deadline:
            checkpoint(args)
            m=MBI()
            if not k.VirtualQueryEx(h,address,C.byref(m),C.sizeof(m)):break
            start=m.BaseAddress or 0;end=start+m.RegionSize
            if end<=address:break
            if m.State==0x1000 and m.Protect&0xff in (2,4,8,0x20,0x40,0x80) and not m.Protect&0x100:
                for pos,size in scan_chunks(start,end,SCAN_LIMIT-attempted):
                    checkpoint(args)
                    if time.monotonic() >= deadline:return tokens
                    buf=C.create_string_buffer(size);n=C.c_size_t()
                    attempted += size
                    if k.ReadProcessMemory(h,pos,buf,size,C.byref(n)):
                        tokens.update(extract_tokens(buf.raw[:n.value]))
            address=end
    finally:k.CloseHandle(h)
    return tokens

