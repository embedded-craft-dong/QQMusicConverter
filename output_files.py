"""Shared output names and atomic publication; never change source files."""
import os
from pathlib import Path
import re
import tempfile
from job import checkpoint


def valid_stem(value):
    value = value.strip()
    if (not value or value in ('.', '..') or len(value) > 120
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith(('.', ' '))
            or re.fullmatch(r'(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value)):
        raise ValueError('输出名称不能包含路径、Windows 禁用字符或保留名称，且不能超过 120 个字符。')
    return value


def output_path(source, folder, suffix, args=None):
    stem = getattr(args, 'output_stem', None) or Path(source).stem
    return Path(folder) / (valid_stem(stem) + suffix)


def publish(temporary, target, overwrite=False):
    if overwrite:
        os.replace(temporary, target)
    elif os.name == 'nt':
        os.rename(temporary, target)
    else:
        os.link(temporary, target)
        os.unlink(temporary)


def save_bytes(target, data, args=None, overwrite=False):
    target = Path(target)
    checkpoint(args)
    if target.exists() and not overwrite:
        raise FileExistsError('同名文件已存在；请改输出名称或另选目录。')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.asset-', suffix='.tmp', dir=target.parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        checkpoint(args)
        publish(temporary, target, overwrite)
        temporary = None
        return target
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink()
