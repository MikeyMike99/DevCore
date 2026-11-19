"""Course enrolment: email verification of a registration, and team invite links.

Why: a registration is only trusted once the owner of the email address has confirmed it. That
confirms the enrolment and stops someone else from enrolling with another person's name and email.

Only hashes of tokens and codes are stored. Tokens and codes expire, are single use, and are rate
limited. Team links carry the project settings only (never anyone's name or email).
"""
import hashlib
import html
import json
import os
import secrets
import threading
import time

VERIFY_TTL = 24 * 3600          # a verification link / code works for 24 hours
INVITE_TTL = 7 * 24 * 3600      # a team link works for 7 days
INVITE_MAX_USES = 20
CODE_MAX_ATTEMPTS = 5
SEND_LIMIT_PER_HOUR = 3         # per learner and course
SEND_LIMIT_PER_EMAIL_HOUR = 5   # per email address, across everyone

_LOCK = threading.Lock()


def public_base_url() -> str:
    """Links in emails use this fixed address, never the request's Host header (which an attacker controls)."""
    return (os.environ.get('DEVCORE_COURSE_PUBLIC_URL') or 'https://siraugga.mikeytech.dev').rstrip('/')


def _h(value: str) -> str:
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _store_path(root: str, name: str) -> str:
    d = os.path.join(root, '_enrolment')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _load(root: str, name: str) -> dict:
    try:
        with open(_store_path(root, name), 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(root: str, name: str, data: dict) -> None:
    path = _store_path(root, name)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(tmp, path)


def mask_email(email: str) -> str:
    email = str(email or '')
    if '@' not in email:
        return ''
    local, _, domain = email.partition('@')
    shown = local[:1] if len(local) <= 2 else local[:2]
    return shown + '***@' + domain


def _prune(data: dict, now: float) -> None:
    for k in [k for k, v in data.items() if isinstance(v, dict) and v.get('expires', now + 1) < now - 86400]:
        data.pop(k, None)


def _rate_ok(data: dict, key: str, limit: int, now: float) -> bool:
    stamps = [t for t in data.get('_rate', {}).get(key, []) if now - t < 3600]
    if len(stamps) >= limit:
        return False
    stamps.append(now)
    data.setdefault('_rate', {})[key] = stamps
    return True


# ------------------------------------------------------------------ verification

def create_verification(root: str, box: str, course_id: str, email: str):
    """Returns (token, code), or (None, reason) when sending too often."""
    now = time.time()
    with _LOCK:
        data = _load(root, 'verifications.json')
        _prune(data, now)
        if not _rate_ok(data, 'box:' + _h(box + '|' + course_id), SEND_LIMIT_PER_HOUR, now):
            _save(root, 'verifications.json', data)
            return None, 'Too many emails were requested. Please wait an hour and try again.'
        if not _rate_ok(data, 'mail:' + _h(email.lower()), SEND_LIMIT_PER_EMAIL_HOUR, now):
            _save(root, 'verifications.json', data)
            return None, 'Too many emails were requested for this address. Please wait an hour and try again.'
        # a new request replaces any older one for the same learner
        for k in [k for k, v in data.items() if isinstance(v, dict) and v.get('box') == box and v.get('course_id') == course_id]:
            data.pop(k, None)
        token = secrets.token_urlsafe(32)
        code = '%06d' % secrets.randbelow(1000000)
        data[_h(token)] = {
            'box': box, 'course_id': course_id, 'email_hash': _h(email.lower()),
            'code_hash': _h(code), 'attempts': 0, 'created': now, 'expires': now + VERIFY_TTL,
        }
        _save(root, 'verifications.json', data)
    return token, code


def find_by_token(root: str, token: str):
    now = time.time()
    with _LOCK:
        rec = _load(root, 'verifications.json').get(_h(token))
    if isinstance(rec, dict) and rec.get('expires', 0) > now:
        return dict(rec)
    return None


def consume_token(root: str, token: str) -> None:
    with _LOCK:
        data = _load(root, 'verifications.json')
        data.pop(_h(token), None)
        _save(root, 'verifications.json', data)


def check_code(root: str, box: str, course_id: str, code: str) -> str:
    """'ok', 'bad', 'locked', 'expired' or 'none'."""
    now = time.time()
    code = ''.join(ch for ch in str(code or '') if ch.isdigit())
    with _LOCK:
        data = _load(root, 'verifications.json')
        for k, rec in list(data.items()):
            if not isinstance(rec, dict) or rec.get('box') != box or rec.get('course_id') != course_id:
                continue
            if rec.get('expires', 0) < now:
                return 'expired'
            if rec.get('attempts', 0) >= CODE_MAX_ATTEMPTS:
                return 'locked'
            if len(code) == 6 and secrets.compare_digest(_h(code), rec.get('code_hash', '')):
                data.pop(k, None)
                _save(root, 'verifications.json', data)
                return 'ok'
            rec['attempts'] = rec.get('attempts', 0) + 1
            _save(root, 'verifications.json', data)
            return 'locked' if rec['attempts'] >= CODE_MAX_ATTEMPTS else 'bad'
    return 'none'


def build_verification_email(full_name: str, course_title: str, link: str, code: str):
    name = html.escape(str(full_name or 'there'))
    title = html.escape(str(course_title or 'the course'))
    safe_link = html.escape(link, quote=True)
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#0f172a">'
        f'<h2 style="margin:0 0 12px">Confirm and start your course</h2>'
        f'<p>Hello {name},</p>'
        f'<p>Someone (we hope you) enrolled in <strong>{title}</strong> with this email address. '
        'Please confirm that it was you. This confirms your enrolment and makes sure nobody else can use your name and email.</p>'
        f'<p style="margin:20px 0"><a href="{safe_link}" style="background:#0d9488;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Confirm and start the course</a></p>'
        f'<p>Or type this code in the course page:</p>'
        f'<p style="font-size:28px;letter-spacing:6px;font-weight:bold;font-family:monospace">{html.escape(code)}</p>'
        '<p style="color:#475569;font-size:13px">The link and code work for 24 hours. If this was not you, ignore this email: nothing will be activated.</p>'
        '</div>'
    )
    text_body = (
        f'Hello {full_name or "there"},\n\n'
        f'Someone (we hope you) enrolled in {course_title} with this email address.\n'
        f'Confirm and start the course: {link}\n'
        f'Or type this code in the course page: {code}\n\n'
        'The link and code work for 24 hours. If this was not you, ignore this email: nothing will be activated.\n'
    )
    return html_body, text_body


def send_verification_email(to_address: str, full_name: str, course_title: str, token: str, code: str) -> dict:
    """Returns {'ok', 'delivery': 'smtp'|'local'|'failed', 'message'}."""
    link = public_base_url() + '/course/verify?token=' + token
    html_body, text_body = build_verification_email(full_name, course_title, link, code)
    try:
        from services.mail import engine as mail_eng
        from services.mail import config as mail_cfg
        ok, message, _ = mail_eng.send_email(
            to_address, 'Confirm your enrolment: ' + str(course_title or 'the course'), html_body, text_body)
        backend = str(getattr(mail_cfg.config, 'MAIL_BACKEND', 'local') or 'local').lower()
        delivery = 'local' if (backend == 'local' or os.environ.get('DEVCORE_MAIL_DRY_RUN', '') == '1') else 'smtp'
        return {'ok': bool(ok), 'delivery': delivery if ok else 'failed', 'message': str(message)[:200]}
    except Exception as exc:
        return {'ok': False, 'delivery': 'failed', 'message': 'The email could not be sent: ' + str(exc)[:160]}


# ------------------------------------------------------------------ team invites

def create_invite(root: str, box: str, course_id: str, project: dict) -> str:
    now = time.time()
    with _LOCK:
        data = _load(root, 'invites.json')
        _prune(data, now)
        for k in [k for k, v in data.items() if isinstance(v, dict) and v.get('box') == box and v.get('course_id') == course_id]:
            data.pop(k, None)  # one active link per learner: a new link replaces the old one
        token = secrets.token_urlsafe(24)
        data[_h(token)] = {
            'box': box, 'course_id': course_id, 'created': now, 'expires': now + INVITE_TTL,
            'uses': 0, 'max_uses': INVITE_MAX_USES,
            'project': {
                'organization': str(project.get('organization') or '')[:48],
                'azure_location': str(project.get('azure_location') or '')[:40],
                'compliance_framework': str(project.get('compliance_framework') or '')[:48],
            },
        }
        _save(root, 'invites.json', data)
    return token


def lookup_invite(root: str, token: str):
    now = time.time()
    with _LOCK:
        rec = _load(root, 'invites.json').get(_h(token or ''))
    if isinstance(rec, dict) and rec.get('expires', 0) > now and rec.get('uses', 0) < rec.get('max_uses', INVITE_MAX_USES):
        return {'course_id': rec['course_id'], 'project': dict(rec['project']), 'expires': rec['expires'],
                'uses': rec.get('uses', 0), 'max_uses': rec.get('max_uses', INVITE_MAX_USES)}
    return None


def use_invite(root: str, token: str):
    """Counts one joiner. Returns the invite's project, or None if the link is not valid."""
    now = time.time()
    with _LOCK:
        data = _load(root, 'invites.json')
        rec = data.get(_h(token or ''))
        if not isinstance(rec, dict) or rec.get('expires', 0) < now or rec.get('uses', 0) >= rec.get('max_uses', INVITE_MAX_USES):
            return None
        rec['uses'] = rec.get('uses', 0) + 1
        _save(root, 'invites.json', data)
        return dict(rec['project'])


def invite_status(root: str, box: str, course_id: str):
    now = time.time()
    with _LOCK:
        for v in _load(root, 'invites.json').values():
            if isinstance(v, dict) and v.get('box') == box and v.get('course_id') == course_id and v.get('expires', 0) > now:
                return {'active': True, 'uses': v.get('uses', 0), 'max_uses': v.get('max_uses', INVITE_MAX_USES), 'expires': v.get('expires')}
    return {'active': False, 'uses': 0, 'max_uses': INVITE_MAX_USES}
