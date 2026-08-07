#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path, PurePosixPath
p=argparse.ArgumentParser(); p.add_argument('--scope',required=True); p.add_argument('--work-id',required=True); p.add_argument('--changed-status',required=True); a=p.parse_args()
config=json.loads(Path(a.scope).read_text(encoding='utf-8'))
if config.get('schema_version')!=3: raise SystemExit('scope schema_version must be 3')
rule=config.get('works',{}).get(a.work_id)
if rule is None: raise SystemExit(f'unknown work id: {a.work_id}')
exact=set(rule.get('exact',[])); prefixes=tuple(rule.get('prefixes',[]))
def normalize(path:str)->str:
    p=PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts: raise SystemExit(f'illegal path: {path}')
    return p.as_posix()
def allowed(path:str)->bool: return path in exact or any(path.startswith(x) for x in prefixes)
violations=[]; seen=[]
for raw in Path(a.changed_status).read_text(encoding='utf-8').splitlines():
    if not raw.strip(): continue
    parts=raw.split('\t'); status=parts[0]; paths=[normalize(x) for x in parts[1:]]
    check=paths if status.startswith(('R','C')) and len(paths)==2 else paths[:1]
    for path in check:
        seen.append(path)
        if not allowed(path): violations.append(path)
if not seen: raise SystemExit('no changed paths found')
if violations: raise SystemExit('out-of-scope paths: '+', '.join(sorted(set(violations))))
print(json.dumps({'work_id':a.work_id,'changed_paths':seen,'scope_ok':True},ensure_ascii=False))
