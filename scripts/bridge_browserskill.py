"""BrowserSkill subprocess transport; never launches a daemon.

Legacy call/evaluate/session_stop shapes are retained. Command failures now
raise typed exceptions, rather than silently continuing on a failed navigation.
Only sessions created by this process are stopped.
"""
import atexit
import json
import os
import shutil
import subprocess
from exceptions import BrowserSkillError, BrowserNotConnectedError

_SESSIONS = {}
_HINT = '请在单独 PowerShell 运行：bsk daemon start --foreground；确认扩展已连接。'


def resolve_bsk():
    candidate = os.environ.get('BSK_BIN') or shutil.which('bsk')
    if not candidate:
        raise BrowserSkillError('找不到 BrowserSkill。设置 BSK_BIN 或将 bsk 加入 PATH。' + _HINT)
    return candidate


def run_bsk(args, timeout=60):
    env = os.environ.copy()
    # Never allow a subprocess to auto-launch a Windows Job Object daemon.
    env['BSK_AUTO_START'] = '0'
    try:
        p = subprocess.run([resolve_bsk(), *args], capture_output=True,
                           text=True, encoding='utf-8', errors='replace',
                           timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BrowserSkillError(f'BrowserSkill 调用失败：{exc}。{_HINT}') from exc
    if p.returncode:
        message = (p.stderr or p.stdout or 'empty error output').strip()
        raise BrowserNotConnectedError(f'bsk {args[0]} 失败：{message}。{_HINT}')
    return (p.stdout or '').strip()


def _decode(out):
    try:
        value = json.loads(out)
        # evaluate(JSON.stringify(...)) can produce a JSON string or direct object.
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return {'raw': value}
        return value
    except ValueError:
        return {'raw': out}


def _start(name):
    out = _decode(run_bsk(['session', 'start', '--json']))
    if not isinstance(out, dict) or not out.get('session_id'):
        raise BrowserNotConnectedError('bsk session start 未返回 session_id。' + _HINT)
    _SESSIONS[name] = str(out['session_id'])
    return _SESSIONS[name]


def _sid(name):
    return _SESSIONS.get(name) or _start(name)


def call(action, args, session):
    if action == 'close_session':
        session_stop(session)
        return {'ok': True}
    sid = _sid(session)
    if action == 'navigate':
        out = run_bsk(['navigate', args['url'], '--session', sid,
                       '--wait-until', 'load', '--timeout', '30s'], 45)
        return {'ok': True, 'data': out}
    if action == 'evaluate':
        out = run_bsk(['evaluate', args['code'], '--session', sid, '--timeout', '30s'], 45)
        if not out:
            raise BrowserSkillError('bsk evaluate 返回空内容。')
        return {'ok': True, 'data': {'type': 'string', 'value': out}}
    if action == 'snapshot':
        return {'ok': True, 'data': run_bsk(['snapshot', '--session', sid], 45)}
    if action == 'screenshot':
        cmd = ['screenshot', '--session', sid]
        path = args.get('path') or args.get('out')
        if path:
            cmd += ['--out', str(path)]
        return {'ok': True, 'data': run_bsk(cmd, 45)}
    raise BrowserSkillError(f'Unknown BrowserSkill action: {action}')


def evaluate(code, session):
    return _decode(call('evaluate', {'code': code}, session)['data']['value'])


def session_stop(name=None):
    names = list(_SESSIONS) if name is None else [name]
    for item in names:
        sid = _SESSIONS.pop(item, None)
        if sid:
            run_bsk(['session', 'stop', sid], 30)


def _cleanup():
    # Exit cleanup must not obscure the CLI's actual failure or stop other sessions.
    for name in list(_SESSIONS):
        try:
            session_stop(name)
        except BrowserSkillError:
            pass

atexit.register(_cleanup)
