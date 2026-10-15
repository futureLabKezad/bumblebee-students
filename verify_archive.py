import io,json,tarfile,hashlib
from pathlib import Path
base=Path(__file__).resolve().parent
expected={r['path']:r for r in json.loads((base/'FILES.json').read_text())['files']}
class Parts(io.RawIOBase):
 def __init__(self):self.paths=iter(sorted(base.glob('workspace.tar.gz.part*')));self.f=None
 def readable(self):return True
 def read(self,n=-1):
  chunks=[];remaining=n
  while n<0 or remaining>0:
   if self.f is None:
    p=next(self.paths,None)
    if p is None:break
    self.f=p.open('rb')
   b=self.f.read(remaining if n>=0 else -1)
   if not b:self.f.close();self.f=None;continue
   chunks.append(b);remaining-=len(b)
  return b''.join(chunks)
seen=set();hashes={}
with tarfile.open(fileobj=Parts(),mode='r|gz') as tar:
 for member in tar:
  row=expected[member.name];seen.add(member.name)
  if member.isdir():assert row.get('directory')
  elif member.issym():assert member.linkname==row['link']
  elif member.islnk():assert hashes[member.linkname]==row['sha256'];hashes[member.name]=row['sha256']
  else:
   h=hashlib.sha256();f=tar.extractfile(member)
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
   assert h.hexdigest()==row['sha256'] and member.size==row['bytes'],member.name
   hashes[member.name]=h.hexdigest()
assert seen==set(expected),(len(seen),len(expected))
print(json.dumps({'pass':True,'entries':len(seen),'files':len(hashes)}))
