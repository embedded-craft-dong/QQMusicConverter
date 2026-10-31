"""Run the bundled EXE away from source, without external Python search paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    executable=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='converter-portable-test-') as folder:
        staging=Path(folder)
        copy=staging/'QQMusicConverter.exe'
        shutil.copyfile(executable,copy)
        report=staging/'report.json'
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','VIRTUAL_ENV','CONDA','_PYI'))}
        env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        env['LOCALAPPDATA']=str(staging/'preferences')
        completed=subprocess.run([str(copy),'--self-test',str(report)],cwd=staging,env=env,timeout=60)
        result=json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
        if completed.returncode or not result.get('ok'):
            raise RuntimeError('Bundled executable self-test failed: '+str(result))
        print('Portable EXE self-test passed:',', '.join(result['checks']))


if __name__=='__main__':main()
