"""BrowserSkill adapter driven ONLY by locally investigated DOM profiles.

No production FastMoss selector, period label, or sales URL is guessed here.
An absent/mismatched profile fails closed before collecting any rows.
"""
import hashlib
import json
import os
import time
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse
from bridge_browserskill import call, evaluate, session_stop
from exceptions import (BrowserSkillError, CategoryDiscoveryError, FastMossLoginError,
                        FilterNotFoundError, FilterVerificationError, NoDataError)

DIMENSIONS = ('country', 'shop_type', 'l1', 'l2', 'l3', 'period')


def load_profile(path=None):
    path = Path(path or os.environ.get('FASTMOSS_SALES_PROFILE', 'local-profiles/sales.json'))
    if not path.is_file():
        raise FilterVerificationError(
            f'缺少已调查的销量榜 DOM profile：{path}。'
            '必须先在已登录的 Windows BrowserSkill 环境完成页面调查；'
            '参见 docs/DOM_INVESTIGATION.md。禁止猜测 selector 或保存未核验数据。')
    try:
        profile = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise FilterVerificationError(f'DOM profile 无法读取：{exc}') from exc
    url = urlparse(profile.get('url', ''))
    if url.scheme != 'https' or url.hostname not in ('fastmoss.com', 'www.fastmoss.com'):
        raise FilterVerificationError('profile URL 必须是实际调查的 HTTPS FastMoss 页面。')
    proof = profile.get('investigation', {})
    if proof.get('transport') != 'BrowserSkill' or not proof.get('observed_at'):
        raise FilterVerificationError('profile 缺少 BrowserSkill 调查来源和时间。')
    evidence = proof.get('evidence', [])
    if not evidence:
        raise FilterVerificationError('profile 缺少本地调查证据及 SHA256。')
    for entry in evidence:
        evidence_path = path.parent / entry.get('path', '')
        if (not evidence_path.is_file() or hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                != entry.get('sha256')):
            raise FilterVerificationError(f'调查证据不存在或已变化：{evidence_path}')
    required = ('filter_scope', 'table_scope', 'read_state_js', 'click_filter_js',
                'discover_options_js', 'next_page_js')
    if any(not isinstance(profile.get(key), str) or not profile[key].strip() for key in required):
        raise FilterVerificationError('profile 未完成 DOM scope、状态、交互或分页实现。')
    if set(profile.get('period_labels', {})) != {'week', 'month'}:
        raise FilterVerificationError('profile 必须包含实际观察的 week/month 页面标签。')
    if not profile.get('header_aliases'):
        raise FilterVerificationError('profile 缺少实际表头映射。')
    profile['_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return profile


# Standards-based table traversal, constrained to the investigated table scope.
# Merged header cells are expanded; a multi-row header becomes its leaf label.
EXTRACT_TABLE_JS = r'''(ctx) => {
  const table = ctx.table;
  const read = el => (el.innerText || el.textContent || '').trim();
  const head = Array.from(table.querySelectorAll('thead tr'));
  const grid = [];
  for (let r=0; r<head.length; r++) {
    grid[r] ||= []; let c=0;
    for (const cell of head[r].querySelectorAll('th,td')) {
      while (grid[r][c] !== undefined) c++;
      for (let rr=0; rr<(cell.rowSpan||1); rr++) {
        grid[r+rr] ||= [];
        for (let cc=0; cc<(cell.colSpan||1); cc++) grid[r+rr][c+cc]=read(cell);
      }
      c += cell.colSpan || 1;
    }
  }
  const headers = grid.length ? grid[grid.length-1] : [];
  const rows = [];
  for (const tr of table.querySelectorAll('tbody tr')) {
    const cells = Array.from(tr.querySelectorAll(':scope > td'));
    if (!cells.length) continue;
    if (cells.some(c => c.colSpan!==1 || c.rowSpan!==1)) {
      // Empty/prompt rows must be recognized by investigated read_state_js;
      // do not silently ignore a malformed nonempty row.
      if (cells.every(c => !read(c))) continue;
      return {error:'body cell spans are not supported; cannot confirm alignment'};
    }
    rows.push(cells.map(c => ({text:read(c),
      links:Array.from(c.querySelectorAll('a[href]')).map(a=>a.href),
      name:ctx.name_selector ? read(c.querySelector(ctx.name_selector)||{textContent:''}) : ''})));
  }
  return {headers,rows};
}'''


class SalesBrowser:
    def __init__(self, profile, *, nav_sleep=6, filter_sleep=3, page_sleep=4,
                 timeout=45, session=None):
        self.profile = profile
        self.session = session or 'sales-' + uuid.uuid4().hex
        self.nav_sleep = nav_sleep
        self.filter_sleep = filter_sleep
        self.page_sleep = page_sleep
        self.timeout = timeout

    def close(self):
        try:
            session_stop(self.session)
        except BrowserSkillError as exc:
            print(f"WARNING: 无法停止本脚本 session：{exc}", file=sys.stderr)

    def _invoke(self, key, args=None):
        cfg = self.profile
        # No whole-page text matching: both selectors must uniquely identify scopes.
        # Hook functions receive scope nodes and request args, never snapshot refs.
        fn = EXTRACT_TABLE_JS if key == 'extract_table' else cfg[key]
        context = json.dumps({'filter_scope': cfg['filter_scope'], 'table_scope': cfg['table_scope'],
                              'name_selector': cfg.get('name_selector'), 'args': args or {}},
                             ensure_ascii=False)
        code = '''(() => {
          const cfg = CFG;
          const roots = document.querySelectorAll(cfg.filter_scope);
          const tables = document.querySelectorAll(cfg.table_scope);
          if (roots.length !== 1 || tables.length !== 1)
            return JSON.stringify({error:'DOM scope not unique',roots:roots.length,tables:tables.length});
          const ctx={root:roots[0],table:tables[0],args:cfg.args,name_selector:cfg.name_selector};
          try { return JSON.stringify((FN)(ctx)); }
          catch (e) { return JSON.stringify({error:String(e)}); }
        })()'''.replace('const cfg = CFG;', 'const cfg = ' + context + ';').replace('(FN)(ctx)', '(' + fn + ')(ctx)')
        result = evaluate(code, self.session)
        if not isinstance(result, dict) and key != 'discover_options_js':
            raise FilterVerificationError(f'{key} 未返回可核验对象：{result}')
        if isinstance(result, dict) and result.get('error'):
            raise FilterVerificationError(f'{key}：{result}')
        return result

    def navigate(self):
        call('navigate', {'url': self.profile['url']}, self.session)
        time.sleep(self.nav_sleep)
        self.wait_for({})

    def state(self):
        state = self._invoke('read_state_js')
        # Actual final URL after redirect, rather than profile's claimed URL.
        actual_url = evaluate('JSON.stringify({url:location.href})', self.session)
        if not isinstance(actual_url, dict) or actual_url.get('url', '').split('#')[0] != self.profile['url'].split('#')[0]:
            raise FilterVerificationError(f'当前 URL 与已调查销量榜不一致：{actual_url}')
        if state.get('logged_in') is not True:
            raise FastMossLoginError('无法确认 FastMoss 登录状态，禁止采集。')
        return state

    @staticmethod
    def verified(state, expected):
        return (state.get('loading') is False and state.get('ready') is True
                and bool(state.get('revision'))
                and all(state.get(k) == v for k, v in expected.items())
                and all(state.get('data_filters', {}).get(k) == v for k, v in expected.items()))

    def wait_for(self, expected, *, previous_revision=None):
        end = time.monotonic() + self.timeout
        stable = 0
        previous = None
        last = {}
        while time.monotonic() < end:
            last = self.state()
            valid = self.verified(last, expected)
            if previous_revision is not None:
                valid = valid and last.get('revision') != previous_revision
            fingerprint = json.dumps(last, sort_keys=True, ensure_ascii=False)
            stable = stable + 1 if valid and fingerprint == previous else (1 if valid else 0)
            if stable >= 2:
                return last
            previous = fingerprint
            time.sleep(0.5)
        raise FilterVerificationError(f'SPA 刷新或筛选无法确认，期望={expected}；实际={last}')

    def select(self, dim, label, expected):
        before = self.state()
        result = self._invoke('click_filter_js', {'dimension': dim, 'label': label})
        if result.get('clicked') is not True and result.get('already_selected') is not True:
            raise FilterNotFoundError(f'筛选区域未提供：{dim}={label}；{result}')
        time.sleep(self.filter_sleep)
        # A genuine change must commit a new data revision, not just an optimistic UI update.
        previous = before.get('revision') if before.get(dim) != label else None
        return self.wait_for(expected, previous_revision=previous)

    def options(self, level, expected):
        self.wait_for(expected)
        result = self._invoke('discover_options_js', {'level': level})
        if not isinstance(result, list) or not result:
            raise CategoryDiscoveryError(f'没有确认到第 {level} 级类目选项：{result}')
        options = []
        for item in result:
            if not isinstance(item, dict) or not str(item.get('label', '')).strip():
                raise CategoryDiscoveryError(f'类目选项格式错误：{item}')
            if item.get('selectable') is not True:
                continue
            options.append({'label': item['label'].strip(), 'id': item.get('id')})
        if not options or len({item['label'] for item in options}) != len(options):
            raise CategoryDiscoveryError('类目选项为空或同级名称重复，禁止猜测层级。')
        return options

    def extract(self, expected, page):
        requested = {**expected, 'page': page}
        before = self.wait_for(requested)
        payload = self._invoke('extract_table')
        after = self.state()
        if before != after or not self.verified(after, requested):
            raise FilterVerificationError('读取销量表时页面状态改变，禁止保存。')
        if after.get('no_data') is True:
            raise NoDataError(f'已验证筛选没有数据：{expected}')
        return payload, after

    def next_page(self, expected, page):
        before = self.wait_for({**expected, 'page': page})
        result = self._invoke('next_page_js', {'page': page})
        if result.get('end') is True and result.get('clicked') is not True:
            return False
        if result.get('clicked') is not True:
            raise FilterVerificationError(f'无法确认分页：{result}')
        time.sleep(self.page_sleep)
        self.wait_for({**expected, 'page': page + 1}, previous_revision=before['revision'])
        return True
