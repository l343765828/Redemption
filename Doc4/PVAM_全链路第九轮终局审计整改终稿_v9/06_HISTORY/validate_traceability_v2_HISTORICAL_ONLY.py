#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

STEP_RE = re.compile(r'^###\s+(STEP-PVAM-[0-9A-Z]+-[0-9]{2})[：:]', re.M)
LOCAL_TC_RE = re.compile(r'^\|\s*(TC-PVAM-[0-9A-Z]+-[0-9]{2})\s*\|', re.M)
EV_RE = re.compile(r'^\|\s*(EV-PVAM-[0-9A-Z]+-(?:[0-9]{2}|P[0-9]{2}))\s*\|', re.M)
CONTROLLED_TC_RE = re.compile(r'(?<!PVAM-)\bTC-(?:00[1-9]|0[12][0-9]|03[0-2])\b')
WORK_ID_RE = re.compile(r'WORK-PVAM-(?:07A|07B|0[1-8])')
TASK_ID_RE = re.compile(r'TASK-PVAM-(?:07A|07B|0[1-8])')

class ValidationError(Exception): pass

def fail(msg: str) -> None: raise ValidationError(msg)
def read(path: Path) -> str:
    if not path.is_file(): fail(f'missing file: {path}')
    return path.read_text(encoding='utf-8')
def section(text: str, start: str, end: str) -> str:
    s=re.search(start,text,re.M)
    if not s: fail(f'missing section: {start}')
    e=re.search(end,text[s.end():],re.M)
    return text[s.end():s.end()+e.start()] if e else text[s.end():]
def unique(values, label):
    vals=list(values)
    if len(vals)!=len(set(vals)): fail(f'duplicate {label}: {vals}')
    return set(vals)
def parse_work(path: Path):
    text=read(path)
    m=WORK_ID_RE.search(path.name)
    if not m: fail(f'cannot infer work id: {path.name}')
    wid=m.group(0)
    steps=unique(STEP_RE.findall(text),f'{wid} STEP definitions')
    tsec=section(text,r'^### 9\.1\b.*$',r'^### 9\.2\b.*$')
    tests=unique(LOCAL_TC_RE.findall(tsec),f'{wid} local TC definitions')
    esec=section(text,r'^## 12\.\s.*$',r'^## 13\.\s.*$')
    evs=unique(EV_RE.findall(esec),f'{wid} EV definitions')
    controlled=set(CONTROLLED_TC_RE.findall(tsec))
    return {'id':wid,'text':text,'steps':steps,'tests':tests,'evidences':evs,'controlled':controlled,'path':path}
def load_docs(directory: Path, prefix: str, id_re):
    out={}
    for p in sorted(directory.glob(prefix+'*.md')):
        if '完整套件' in p.name or '施工总方案' in p.name or '总方案' in p.name: continue
        m=id_re.search(p.name)
        if not m: continue
        ident=m.group(0)
        if ident in out: fail(f'duplicate document for {ident}')
        out[ident]=p
    return out

def compare_sets(label, actual, expected):
    missing=set(expected)-set(actual); extra=set(actual)-set(expected)
    if missing or extra:
        fail(f'{label}: missing={sorted(missing)} extra={sorted(extra)}')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',required=True); ap.add_argument('--plan',required=True); ap.add_argument('--report',required=True)
    ap.add_argument('--modplan',required=True); ap.add_argument('--task-dir',required=True); ap.add_argument('--work-dir',required=True)
    a=ap.parse_args()
    m=json.loads(read(Path(a.manifest)))
    if m.get('schema_version')!=3: fail('schema_version must be 3')
    baseline='2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb'
    if m.get('baseline_commit')!=baseline: fail('baseline mismatch')
    plan=read(Path(a.plan)); report=read(Path(a.report)); mod=read(Path(a.modplan))
    tasks=load_docs(Path(a.task_dir),'TASK-PVAM-',TASK_ID_RE)
    work_paths=load_docs(Path(a.work_dir),'WORK-PVAM-',WORK_ID_RE)
    works={wid:parse_work(p) for wid,p in work_paths.items()}
    expected_work_ids={'WORK-PVAM-01','WORK-PVAM-02','WORK-PVAM-03','WORK-PVAM-04','WORK-PVAM-05','WORK-PVAM-06','WORK-PVAM-07A','WORK-PVAM-07B','WORK-PVAM-08'}
    compare_sets('work documents',works,expected_work_ids)
    compare_sets('task documents',tasks,{x.replace('WORK-','TASK-') for x in expected_work_ids})

    core_expected=[f'R-{i:03d}' for i in range(1,14)]
    if m.get('core_issues')!=core_expected: fail('core issue list mismatch')
    if m.get('subissues')!={'R-012':['R-012A','R-012B']}: fail('R-012 parent/child mismatch')
    core=m.get('core_edges',[])
    ids=[r.get('issue_id') for r in core]
    if len(ids)!=14 or len(set(ids))!=14: fail('core edge ids must be 14 unique rows')
    compare_sets('core edge issue ids',ids,{f'R-{i:03d}' for i in range(1,12)}|{'R-012A','R-012B','R-013'})
    by={r['issue_id']:r for r in core}
    if by['R-012A'].get('parent_issue_id')!='R-012' or by['R-012B'].get('parent_issue_id')!='R-012': fail('R-012 parent link missing')
    if set(by['R-012A']['checks'])!={'CHK-ARCH-002','CHK-EVT-006','CHK-EVT-007','CHK-TEST-001','CHK-TEST-003'}: fail('R-012A CHK set mismatch')
    if set(by['R-012B']['checks'])!={'CHK-ARCH-002','CHK-EVT-006','CHK-EVT-007','CHK-TEST-003'}: fail('R-012B CHK set mismatch')
    if not {'CHK-ARCH-003','CHK-BIZ-011'} <= set(by['R-003']['checks']): fail('R-003 repaired edges missing')
    if 'CHK-BIZ-006' not in by['R-009']['checks']: fail('R-009 repaired edge missing')

    non=m.get('non_core_edges',[])
    non_ids=[r.get('item_id') for r in non]
    required_non={'RISK-001','RISK-002','UV-001','UV-002','UV-003','UV-004','UV-005','OPT-001','OPT-002','GAP-DEC004-2B','FIX-001'}
    compare_sets('non-core items',non_ids,required_non)
    if len(non_ids)!=len(set(non_ids)): fail('duplicate non-core item')
    allowed_status={'UAT_VERIFY','ACCEPTED','DEFERRED','CONFIRMED_CLOSED'}
    for r in non:
        if r.get('status') not in allowed_status: fail(f'invalid non-core status: {r}')
        if r['item_id'] not in (report+mod): fail(f'non-core item absent from report/modplan: {r["item_id"]}')

    # Forward layer validation and aggregate manifest nodes by WORK.
    agg={wid:{'steps':set(),'tests':set(),'evidences':set()} for wid in works}
    for r in core:
        required={'issue_id','parent_issue_id','checks','decisions','task_id','work_id','rem_id','implementation_id','verification_id','steps','local_tests','evidences'}
        if not required <= r.keys(): fail(f'missing core fields: {r.get("issue_id")}')
        wid=r['work_id']; tid=r['task_id']
        if wid not in works or tid not in tasks: fail(f'unknown task/work in {r["issue_id"]}')
        task_text=read(tasks[tid]); work_text=works[wid]['text']
        for token in r['checks']+r['decisions']:
            if token not in plan: fail(f'{token} absent from PLAN')
        for token in [r['issue_id'],*r['checks'],*r['decisions'],r['rem_id'],r['implementation_id'],r['verification_id']]:
            if token not in task_text+work_text+report+mod: fail(f'{token} absent across controlled layers')
        agg[wid]['steps'].update(r['steps']); agg[wid]['tests'].update(r['local_tests']); agg[wid]['evidences'].update(r['evidences'])
    for r in non:
        wid=r.get('work_id'); tid=r.get('task_id')
        if wid:
            if wid not in works or tid not in tasks: fail(f'unknown non-core task/work: {r["item_id"]}')
            text=read(tasks[tid])+works[wid]['text']
            if r['item_id'] not in text+mod+report: fail(f'non-core source missing: {r["item_id"]}')
            agg[wid]['steps'].update(r.get('steps',[])); agg[wid]['tests'].update(r.get('local_tests',[])); agg[wid]['evidences'].update(r.get('evidences',[]))

    # Exact bidirectional set differences: Manifest orphans and WORK orphans both fail.
    for wid,w in works.items():
        compare_sets(f'{wid} STEP bidirectional',w['steps'],agg[wid]['steps'])
        compare_sets(f'{wid} local TC bidirectional',w['tests'],agg[wid]['tests'])
        compare_sets(f'{wid} EV bidirectional',w['evidences'],agg[wid]['evidences'])

    mappings=m.get('controlled_test_mappings',[])
    mids=[x.get('work_id') for x in mappings]
    compare_sets('controlled mapping works',mids,expected_work_ids)
    if len(mids)!=len(set(mids)): fail('duplicate controlled mapping work')
    for row in mappings:
        wid=row['work_id']; tid=row['task_id']; w=works[wid]; task_text=read(tasks[tid])
        controlled=set(row.get('controlled_tc',[])); local=set(row.get('local_tc',[]))
        compare_sets(f'{wid} manifest local mapping',local,w['tests'])
        compare_sets(f'{wid} WORK controlled TC',controlled,w['controlled'])
        task_controlled=set(CONTROLLED_TC_RE.findall(task_text))
        if not controlled <= task_controlled:
            fail(f'{wid} controlled TC absent from TASK: {sorted(controlled-task_controlled)}')
        for tc in controlled:
            if tc not in plan: fail(f'{tc} absent from PLAN')

    print(f'TRACEABILITY_V3_PASS core_edges={len(core)} non_core={len(non)} works={len(works)}')

if __name__=='__main__':
    try: main()
    except (ValidationError, AssertionError, KeyError, json.JSONDecodeError) as exc:
        print(f'TRACEABILITY_V3_FAIL: {exc}',file=sys.stderr)
        raise SystemExit(2)
