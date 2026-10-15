import hashlib,json,sys,os
from pathlib import Path
base=Path(__file__).resolve().parent
checks=json.loads((base/'SHA256SUMS.json').read_text())
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
for n,h in checks.items():assert digest(base/n)==h,n
if len(sys.argv)>1:
 root=Path(sys.argv[1]);rows=json.loads((base/'FILES.json').read_text())['files']
 for row in rows:
  p=root/row['path']
  if row.get('directory'):assert p.is_dir(),row['path']
  elif 'link' in row:assert p.is_symlink() and os.readlink(p)==row['link'],row['path']
  else:assert p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],row['path']
 print('PASS: restored files and archive parts')
else:print('PASS: archive parts')
