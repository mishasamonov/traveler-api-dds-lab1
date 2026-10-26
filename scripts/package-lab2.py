"""Package only Git-tracked source, explicitly selected raw results, and the report."""
import argparse, hashlib, subprocess, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
GIT=Path('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe')
def main(output,report):
    cmd=[str(GIT) if GIT.exists() else 'git','-c',f'safe.directory={ROOT.as_posix()}','ls-files','-z']
    tracked=subprocess.run(cmd,cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout.split(b'\0')
    files=[ROOT/name.decode('utf-8') for name in tracked if name]
    files+=list((ROOT/'tests/performance-tests/results').glob('*-raw.json.gz'))
    manifest=[];output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            resolved=path.resolve()
            if not resolved.is_relative_to(ROOT.resolve()):raise ValueError(f'Outside repository: {path}')
            if not path.is_file():continue
            name='TravelerAPI_Lab2/'+path.relative_to(ROOT).as_posix()
            archive.write(path,name)
            digest=hashlib.sha256(path.read_bytes()).hexdigest();manifest.append(f'{digest}  {name}')
        report=Path(report);archive.write(report,'TravelerAPI_Lab2/TravelerAPI_Lab2_Samonov.docx')
        manifest.append(f'{hashlib.sha256(report.read_bytes()).hexdigest()}  TravelerAPI_Lab2/TravelerAPI_Lab2_Samonov.docx')
        archive.writestr('TravelerAPI_Lab2/SHA256SUMS.txt','\n'.join(manifest)+'\n')
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any('/node_modules/' in name or '/.git/' in name or name.endswith('/.env') for name in archive.namelist())
    print(f'{output}: {len(files)+2} entries, {output.stat().st_size/1024**2:.1f} MiB')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args();main(a.output,a.report)
