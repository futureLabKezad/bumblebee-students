import os,json,hashlib,tarfile,io,time,stat,gzip
from pathlib import Path
root=Path(__file__).resolve().parent.parent; out=Path(__file__).resolve().parent
status='''# Состояние Bumblebee на 15 октября 2026 года

Работа остановлена по указанию владельца. По следующему поручению подготовлен полный снимок рабочей папки, включая незавершённые изменения, исходники, окружения, сборки и журналы. Новые испытания не запускались.

Полётный пакет пока не принят. Совместная наземная диагностика INT_combined_ground_02 прошла. Параметры редакции 10 и детектор редакции 03 собраны в combined_03. Предполётный запуск 02 подтвердил штатное включение зрения и возврат всех 19 параметров, но завершился ошибкой независимого чтения свежего статуса. Запуск 03 завершился до подготовки профиля; ARM отсутствовал. Неуспешные результаты сохранены.

Кандидат поля field_measurements_01 содержит листы обычных меток 30 × 42 см, прежние чёрные квадраты 29 × 29 см и прежние координаты карты. Проверка распознавания дала 20/20 ID и 80/80 ориентаций. Длина площадки 4,15 м идёт вдоль жёлтой рулетки на фотографии, глубина 2,40 м. Лист метки 0 и привязка границ площадки не установлены. Фотография подтверждает порядок и ориентацию части ID, но не точность расстояний: среднеквадратическое отклонение единой перспективной модели 35,43 пикселя. Масштабирование карты не выполнялось.

Модуль сохранения времени измерения VPE подготовлен и автономно проверен, но ещё не подключён к полётному кандидату. Исполнитель и независимый проверяющий сценариев находятся в integration/flight_trial_01 и flight_verification_01. Требуются надёжная предполётная проверка, испытание свежести VPE, S1–S9, отмены и пять последовательных успешных полётов на закреплённом составе.

Настоящий дрон не использовался. Готовность к эксплуатации и завершение полётной проверки не заявляются.
'''
(root/'СОСТОЯНИЕ_20261015.md').write_text(status)
for name in ('ПЛАН_ПРОДОЛЖЕНИЯ_CODEX.md','ПЕРЕДАЧА_РАБОТЫ_CODEX.md'):
 with (root/name).open('a') as f:
  if 'Обновление 15 октября 2026 года' not in (root/name).read_text():f.write('\n\n## Обновление 15 октября 2026 года\n\nАктуальное состояние, незавершённые проверки и уточнения поля записаны в `СОСТОЯНИЕ_20261015.md`. Прежние разделы содержат историю и не заменяют этот статус. Подготовлен полный снимок для GitHub по прямому поручению владельца.\n')
p=root/'parallel_work/20261015/coordination.json'; data=json.loads(p.read_text());data['phase']='stopped_snapshot_requested';data['parameters']['status']='revision10_reviewed_preflight_not_accepted';data['parameters']['last_review']='integration/parameters_review_10/REVIEW.json';data['vision']['status']='detector03_frozen_freshness_reviewed_not_integrated';data['integration'].update(combined_candidate='integration/combined_03',last_run='sim/runs/INT_flight_preflight_03',last_run_passed=False,flight_accepted=False,next_gate='Resume only on owner instruction; preflight then freshness and S1-S9');p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
(out/'STATUS.md').write_text(status)
items=[]
for base,ds,fs in os.walk(root):
 ds[:]=sorted(d for d in ds if root/Path(base).relative_to(root)/d != out)
 for d in list(ds):
  p=Path(base)/d;st=p.lstat();rel=p.relative_to(root).as_posix()
  if p.is_symlink():
   items.append({'path':rel,'link':os.readlink(p),'mode':stat.S_IMODE(st.st_mode)});ds.remove(d)
  else:items.append({'path':rel,'directory':True,'mode':stat.S_IMODE(st.st_mode)})
 for n in sorted(fs):
  p=Path(base)/n; rel=p.relative_to(root).as_posix(); st=p.lstat()
  if stat.S_ISLNK(st.st_mode):items.append({'path':rel,'link':os.readlink(p),'mode':stat.S_IMODE(st.st_mode)})
  elif stat.S_ISREG(st.st_mode):
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
   items.append({'path':rel,'bytes':st.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(st.st_mode)})
(out/'FILES.json').write_text(json.dumps({'root':str(root),'excluded':['github_snapshot_20261015 (this export only)'],'files':items},ensure_ascii=False,indent=2)+'\n')
class Chunks:
 def __init__(self):self.f=None;self.index=0;self.size=0;self.total=0
 def write(self,b):
  original=len(b)
  while b:
   if self.f is None or self.size==64*1024*1024:
    if self.f:self.f.close()
    self.index+=1;self.f=(out/f'workspace.tar.gz.part{self.index:04}').open('wb');self.size=0
   n=min(len(b),64*1024*1024-self.size);self.f.write(b[:n]);self.size+=n;self.total+=n;b=b[n:]
  return original
 def flush(self):
  if self.f:self.f.flush()
chunks=Chunks();seen={}
with gzip.GzipFile(fileobj=chunks,mode='wb',compresslevel=3,mtime=0) as gz, tarfile.open(fileobj=gz,mode='w|',dereference=False) as tar:
 for i,item in enumerate(items):
  p=root/item['path'];info=tar.gettarinfo(str(p),arcname=item['path'])
  if 'sha256' in item:
   key=(item['sha256'],item['bytes'],item['mode'])
   if key in seen:info.type=tarfile.LNKTYPE;info.linkname=seen[key];info.size=0;tar.addfile(info)
   else:
    seen[key]=item['path']
    with p.open('rb') as f:tar.addfile(info,f)
  else:tar.addfile(info)
  if i%5000==0:print(json.dumps({'files_archived':i,'total_files':len(items),'compressed_bytes':chunks.total}),flush=True)
if chunks.f:chunks.f.close()
checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('workspace.tar.gz.part*'))}
(out/'SHA256SUMS.json').write_text(json.dumps(checks,indent=2)+'\n')
(out/'README.md').write_text('''# Полный рабочий снимок Bumblebee

Снимок от 15 октября 2026 года содержит всю папку bbsim-work, включая незавершённую работу и результаты неуспешных испытаний. Текущий статус указан в [STATUS.md](STATUS.md). Исторические отчёты внутри архива могут описывать более раннее состояние.

Архив разбит на части по 64 МиБ. FILES.json содержит SHA256 исходных файлов и ссылки. Одинаковые файлы в архиве сохранены через жёсткие ссылки для сокращения объёма. Исходная папка и рабочие ветки проекта не заменены.

Восстановление в новой пустой папке на macOS или Linux:

```sh
python3 verify_snapshot.py
mkdir restored
cat workspace.tar.gz.part* | tar -xzf - -C restored
python3 verify_snapshot.py restored
```

Снимок содержит Linux-сборки и виртуальные окружения; их наличие не означает переносимость на другую ОС. Полётный пакет не принят. Настоящий дрон не использовался.
''')
print(json.dumps({'done':True,'files':len(items),'original_bytes':sum(x.get('bytes',0) for x in items),'compressed_bytes':chunks.total,'parts':len(checks)}),flush=True)
