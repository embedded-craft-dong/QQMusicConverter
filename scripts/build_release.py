"""Test, build and package a Windows x64 release; never publish or include private inputs."""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from music_gui import VERSION

SOURCE_FILES=('music_gui.py','music_workspace.py','tasks.py','media_assets.py','output_files.py','frozen_smoke.py',
              'ui_theme.py','convert_music.py','qmc_core.py','qq_session.py','job.py','settings.py','lyrics.py',
              'requirements.txt','requirements-build.txt','README.md','README.zh-CN.md','CHANGELOG.md','CHANGELOG.zh-CN.md','LICENSE',
              'THIRD_PARTY_NOTICES.md','.gitignore','.gitattributes')
SOURCE_DIRS=('scripts','tests','docs','assets','licenses','.github')
ALLOWED_EXT={'.py','.md','.txt','.yml','.yaml','.png','.ico','.terms'}


def source_paths():
    paths=[ROOT/name for name in SOURCE_FILES]
    for name in SOURCE_DIRS:
        for path in (ROOT/name).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                if path.suffix.lower() in ALLOWED_EXT or path.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
                    paths.append(path)
    return sorted(set(paths))


def run(*args):
    subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,check=True)


def main():
    if sys.platform!='win32' or struct.calcsize('P')!=8:
        raise SystemExit('Build this release on Windows x64 with Python 3.12.')
    run('-m','unittest','discover','-s','tests','-v')
    run('scripts/make_icon.py')
    run('scripts/collect_licenses.py')
    dist,build,release=ROOT/'dist',ROOT/'build',ROOT/'release'
    for folder in (dist,build,release):folder.mkdir(exist_ok=True)
    version_file=build/'version_info.txt'
    version_file.write_text("""VSVersionInfo(
      ffi=FixedFileInfo(filevers=(0,3,0,1),prodvers=(0,3,0,1),mask=0x3f,flags=2,OS=0x40004,fileType=1,subtype=0,date=(0,0)),
      kids=[StringFileInfo([StringTable('040904b0',[
        StringStruct('FileDescription','Music Asset Workbench'),StringStruct('FileVersion','0.3.0-beta.1'),
        StringStruct('ProductName','QQMusicConverter'),StringStruct('ProductVersion','0.3.0-beta.1'),
        StringStruct('OriginalFilename','QQMusicConverter.exe'),StringStruct('LegalCopyright','GPL-3.0; see included notices')])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])])])
""",encoding='utf-8')
    run('-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
        '--name','QQMusicConverter','--distpath',dist,'--workpath',build/'pyinstaller','--specpath',build,
        '--collect-all','_soundfile_data','--collect-all','soundfile',
        '--add-data',str(ROOT/'assets')+';assets','--add-data',str(ROOT/'licenses')+';licenses',
        '--add-data',str(ROOT/'LICENSE')+';.','--add-data',str(ROOT/'THIRD_PARTY_NOTICES.md')+';.',
        '--icon',ROOT/'assets/app.ico','--version-file',version_file,ROOT/'music_gui.py')
    run('scripts/smoke_exe.py',dist/'QQMusicConverter.exe')
    package_release()


def package_release():
    """Refresh documents/source archives around the already-tested executable."""
    dist,release=ROOT/'dist',ROOT/'release'
    source=release/f'QQMusicConverter-{VERSION}-source.zip'
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as z:
        for path in source_paths():
            z.write(path,'QQMusicConverter/'+path.relative_to(ROOT).as_posix())
    binary=release/f'QQMusicConverter-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(binary,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(dist/'QQMusicConverter.exe','QQMusicConverter.exe')
        for name in ('README.md','README.zh-CN.md','LICENSE','THIRD_PARTY_NOTICES.md','CHANGELOG.md','CHANGELOG.zh-CN.md'):
            z.write(ROOT/name,name)
        for directory in ('licenses','docs'):
            for path in (ROOT/directory).rglob('*'):
                if path.is_file():z.write(path,path.relative_to(ROOT).as_posix())
        z.write(source,source.name)
    shutil.copyfile(dist/'QQMusicConverter.exe',release/'QQMusicConverter.exe')
    checksum=[]
    for path in (release/'QQMusicConverter.exe',source,binary):
        checksum.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
    (release/'SHA256SUMS.txt').write_text('\n'.join(checksum)+'\n',encoding='ascii')
    print('Release ready:',release)


if __name__=='__main__':
    if sys.argv[1:]==['--package-only']:
        package_release()
    elif sys.argv[1:]:
        raise SystemExit('Usage: build_release.py [--package-only]')
    else:
        main()
