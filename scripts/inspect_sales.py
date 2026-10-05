#!/usr/bin/env python3
"""Capture local BrowserSkill evidence; does not generate/select production selectors.

Pass the sales URL observed in the browser, not a presumed route. Initial snapshot
is local only. --scope exports only an investigator-confirmed filter container.
No full FastMoss HTML or login data should be committed to GitHub.
"""
import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from bridge_browserskill import call, evaluate, run_bsk, session_stop
from exceptions import FastMossError, FilterVerificationError
from sales_io import write_json, atomic_write


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='从实际页面地址栏复制的商品销量榜 HTTPS URL')
    parser.add_argument('--out-dir', required=True, help='本地调查目录，请勿提交完整 snapshot')
    parser.add_argument('--scope', help='通过 snapshot/evaluate 实际确认的唯一商品筛选容器 CSS selector')
    args = parser.parse_args(argv)
    host = urlparse(args.url)
    if host.scheme != 'https' or host.hostname not in ('www.fastmoss.com', 'fastmoss.com'):
        parser.error('URL 必须是 FastMoss 实际 HTTPS 页面')
    session = 'sales-investigation-' + uuid.uuid4().hex
    try:
        # Exact status output is evidence; no fabricated connected-browser claim.
        status = run_bsk(['status'])
        directory = Path(args.out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write(directory / 'status.txt', lambda stream: stream.write(status))
        call('navigate', {'url': args.url}, session)
        snapshot = call('snapshot', {}, session)['data']
        atomic_write(directory / 'snapshot.txt', lambda stream: stream.write(snapshot))
        code = '''JSON.stringify({url:location.href,title:document.title,
          tables:Array.from(document.querySelectorAll('table')).map(t=>({
            id:t.id,className:t.className,
            headers:Array.from(t.querySelectorAll('thead th')).map(h=>(h.innerText||h.textContent||'').trim())
          }))})'''
        inventory = evaluate(code, session)
        write_json(directory / 'inventory.json', inventory)
        if args.scope:
            cfg = json.dumps(args.scope)
            code = '''(() => {
              const roots=document.querySelectorAll(SELECTOR);
              if(roots.length!==1)return JSON.stringify({error:'filter scope must be unique',count:roots.length});
              return JSON.stringify({url:location.href,scope:SELECTOR,html:roots[0].outerHTML});
            })()'''.replace('SELECTOR', cfg)
            scoped = evaluate(code, session)
            if not isinstance(scoped, dict) or scoped.get('error'):
                raise FilterVerificationError(f'筛选区域 scope 无法确认：{scoped}')
            write_json(directory / 'filter_scope.json', scoped)
        evidence = []
        for filename in ('status.txt', 'snapshot.txt', 'inventory.json', 'filter_scope.json'):
            path = directory / filename
            if path.is_file():
                evidence.append({'path': filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        write_json(directory / 'investigation.json', {'transport':'BrowserSkill',
                   'observed_at':datetime.now(timezone.utc).isoformat(), 'requested_url':args.url,
                   'evidence':evidence, 'complete':False})
        print(f'[captured] {directory}；仍需调查每步 selected state/SPA data_filters，不能直接采集。')
        return 0
    except (FastMossError, OSError, ValueError) as exc:
        print(f'ERROR [{type(exc).__name__}]: {exc}', file=sys.stderr)
        return 1
    finally:
        try:
            session_stop(session)
        except FastMossError:
            pass

if __name__ == '__main__':
    sys.exit(main())
