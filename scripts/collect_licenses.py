"""Copy notices from the installed build environment without accessing the network."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys
import tkinter

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'licenses';out.mkdir(exist_ok=True)
    packages=('numpy','soundfile','cffi','pycparser','pyinstaller','pyinstaller-hooks-contrib',
              'altgraph','packaging','pefile','pywin32-ctypes','setuptools')
    versions=[]
    for name in packages:
        dist=metadata.distribution(name);versions.append(f'{name}=={dist.version}')
        found=False
        for entry in dist.files or []:
            if entry.name.upper().startswith(('LICENSE','COPYING','NOTICE')) and '.dist-info/' in str(entry):
                relative=str(entry).split('.dist-info/',1)[1]
                target=out/name/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(dist.locate_file(entry),target);found=True
        if not found:raise RuntimeError(f'Missing license: {name}')
    import _soundfile_data
    shutil.copyfile(Path(_soundfile_data.__file__).parent/'COPYING',out/'libsndfile-LGPL-2.1.txt')
    shutil.copyfile(Path(sys.base_prefix)/'LICENSE.txt',out/'Python-LICENSE.txt')
    interp=tkinter.Tcl()
    tk_base=Path(interp.eval('info library')).parent
    for folder in ('tcl8.6','tk8.6'):
        source=tk_base/folder/'license.terms'
        if source.is_file():shutil.copyfile(source,out/f'{folder}-license.terms')
    # The Python license also includes Tcl/Tk notices on Windows distributions.
    (out/'BUILD_VERSIONS.txt').write_text('Python '+sys.version.split()[0]+'\n'+'\n'.join(versions)+'\n',encoding='utf-8')


if __name__=='__main__':main()
