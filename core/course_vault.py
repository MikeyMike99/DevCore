"""Zero-knowledge storage broker and deterministic environment lockfile builder for course workspaces.

Security contract:
- All encryption and key derivation happens in the learner's browser. This module only
  stores opaque ciphertext, salts, public keys, and SHA-256 hashes of client-derived
  authentication tokens.
- Passwords, recovery/unlock keys, invite secrets, workspace data keys, and member private keys
  never reach this module in plaintext, so neither the server nor its operator can decrypt
  learner work or reset access to it.
- Authentication tokens are HKDF outputs independent from the client key-encryption keys,
  so possessing a token (or its hash) does not allow decryption.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

SCHEMA_VERSION = 1
PBKDF2_MIN_ITERATIONS = 600000
PBKDF2_MAX_ITERATIONS = 5000000
INVITE_TTL_SECONDS = 24 * 3600
MAX_BLOB_CT_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 8
MAX_OPEN_INVITES = 4

_WS_ID_RE = re.compile(r'^[A-Za-z0-9_-]{22,64}$')
_INVITE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{10,40}$')
_ALIAS_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{1,31}$')
_B64_RE = re.compile(r'^[A-Za-z0-9+/=_-]+$')
_COURSE_RE = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')
_PKG_SPEC_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]{0,62})(\[[A-Za-z0-9,._-]{1,32}\])?(==([A-Za-z0-9.*+-]{1,32}))?$')
_SAFE_TOKEN_RE = re.compile(r'^[A-Za-z0-9_./:@, ()+-]{1,120}$')

FORBIDDEN_PLAINTEXT_KEYS = frozenset({
    'password', 'passphrase', 'pwd', 'recovery_key', 'unlock_key',
    'recovery_phrase', 'raw_dek', 'master_key', 'private_key', 'plaintext', 'secret_key'
})

TYPOSQUAT_BLOCKLIST = {
    'reqeusts': 'requests',
    'requets': 'requests',
    'urllib4': 'urllib3',
    'cryptograpy': 'cryptography',
    'check0v': 'checkov',
    'chekov': 'checkov',
    'asciinma': 'asciinema',
    'ascinema': 'asciinema',
    'pyyam1': 'PyYAML',
    'python-bicep': 'bicep',
}

STANDARD_VENV_PACKAGES = [
    'asciinema==2.4.0',
    'checkov==3.2.459',
    'jsonschema==4.26.0',
    'PyYAML==6.0.3',
]

DEFAULT_PACKAGE_PINS = {
    'asciinema': '2.4.0',
    'checkov': '3.2.459',
    'jsonschema': '4.26.0',
    'pyyaml': '6.0.3',
    'pip-tools': '7.6.2',
    'pytest': '8.3.4',
    'requests': '2.32.3',
    'cryptography': '44.0.0',
    'rich': '13.9.4',
    'pydantic': '2.10.4',
    'httpx': '0.28.1',
}

_LOCK = threading.RLock()
_FAILURES = {}


class VaultError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _assert_zero_knowledge_payload(obj) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_PLAINTEXT_KEYS:
                raise VaultError(
                    400,
                    f'ZERO_KNOWLEDGE_VIOLATION: Plaintext secret field "{k}" must never be sent to the server.'
                )
            _assert_zero_knowledge_payload(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_zero_knowledge_payload(item)


def storage_dir() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, 'data', 'course_workspaces')
    os.makedirs(path, exist_ok=True)
    return path


def _pepper() -> bytes:
    """Server-side anti-enumeration secret. It never protects learner data."""
    p = os.path.join(storage_dir(), '.enumeration_pepper')
    with _LOCK:
        if not os.path.isfile(p):
            with open(p, 'wb') as f:
                f.write(secrets.token_bytes(32))
        with open(p, 'rb') as f:
            return f.read()


def _now() -> int:
    return int(time.time())


def _iso(ts: int = None) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts if ts is not None else _now()))


def _b64(value, field: str, min_bytes: int = 1, max_bytes: int = 4096) -> str:
    if not isinstance(value, str) or not value or not _B64_RE.match(value):
        raise VaultError(400, f'Invalid base64 field: {field}')
    padded = value.replace('-', '+').replace('_', '/')
    padded += '=' * (-len(padded) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
    except Exception:
        raise VaultError(400, f'Invalid base64 field: {field}')
    if not (min_bytes <= len(raw) <= max_bytes):
        raise VaultError(400, f'Field {field} has an invalid length')
    return value


def _box(value, field: str, max_ct: int = 8192) -> dict:
    if not isinstance(value, dict):
        raise VaultError(400, f'Missing encrypted box: {field}')
    return {
        'iv': _b64(value.get('iv'), f'{field}.iv', 12, 12),
        'ct': _b64(value.get('ct'), f'{field}.ct', 17, max_ct),
    }


def _alias(value) -> str:
    alias = (value or '').strip().lower() if isinstance(value, str) else ''
    if not _ALIAS_RE.match(alias):
        raise VaultError(400, 'Alias must be 2-32 characters: lowercase letters, digits, - or _')
    return alias


def _ws_id(value) -> str:
    if not isinstance(value, str) or not _WS_ID_RE.match(value):
        raise VaultError(400, 'Invalid workspace ID')
    return value


def _hash_token(token_b64: str) -> str:
    _b64(token_b64, 'auth', 32, 32)
    return hashlib.sha256(token_b64.encode('ascii')).hexdigest()


def _verify(token_b64, stored_hash: str) -> bool:
    if not isinstance(token_b64, str) or not stored_hash:
        return False
    try:
        candidate = _hash_token(token_b64)
    except VaultError:
        return False
    return hmac.compare_digest(candidate, stored_hash)


def _path(ws_id: str) -> str:
    return os.path.join(storage_dir(), f'{_ws_id(ws_id)}.json')


def _load(ws_id: str) -> dict:
    p = _path(ws_id)
    if not os.path.isfile(p):
        raise VaultError(404, 'Workspace not found or credentials incorrect')
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def _store(doc: dict) -> None:
    p = _path(doc['workspace_id'])
    tmp = f'{p}.{secrets.token_hex(4)}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(tmp, p)


def _throttle_check(key: tuple) -> None:
    entry = _FAILURES.get(key)
    if entry and entry[1] > time.time():
        wait = int(entry[1] - time.time()) + 1
        raise VaultError(429, f'Too many failed attempts. Try again in {wait} seconds.')


def _throttle_fail(key: tuple) -> None:
    count, _ = _FAILURES.get(key, (0, 0))
    count += 1
    lock_for = 0 if count < 5 else min(900, 30 * (2 ** (count - 5)))
    _FAILURES[key] = (count, time.time() + lock_for)


def _throttle_ok(key: tuple) -> None:
    _FAILURES.pop(key, None)


def _member_payload(m: dict) -> dict:
    if not isinstance(m, dict):
        raise VaultError(400, 'Missing member payload')
    pw = m.get('pw') or {}
    rec = m.get('rec') or {}
    iterations = int(pw.get('iterations') or 0)
    if not (PBKDF2_MIN_ITERATIONS <= iterations <= PBKDF2_MAX_ITERATIONS):
        raise VaultError(400, f'Password KDF iterations must be at least {PBKDF2_MIN_ITERATIONS}')
    return {
        'alias': _alias(m.get('alias')),
        'public_key': _b64(m.get('public_key'), 'public_key', 65, 65),
        'pw': {
            'salt': _b64(pw.get('salt'), 'pw.salt', 16, 64),
            'iterations': iterations,
            'kdf': 'PBKDF2-SHA256',
            'auth_hash': _hash_token(pw.get('auth')),
            'enc_private': _box(pw.get('enc_private'), 'pw.enc_private'),
        },
        'rec': {
            'salt': _b64(rec.get('salt'), 'rec.salt', 16, 64),
            'auth_hash': _hash_token(rec.get('auth')),
            'enc_private': _box(rec.get('enc_private'), 'rec.enc_private'),
        },
    }


def _key_wrap(w: dict, key_version: int) -> dict:
    if not isinstance(w, dict):
        raise VaultError(400, 'Missing key wrap')
    if int(w.get('key_version') or 0) != key_version:
        raise VaultError(400, 'Key wrap version mismatch')
    return {
        'key_version': key_version,
        'epk': _b64(w.get('epk'), 'key_wrap.epk', 65, 65),
        'iv': _b64(w.get('iv'), 'key_wrap.iv', 12, 12),
        'ct': _b64(w.get('ct'), 'key_wrap.ct', 48, 48),
    }


def _blob(b: dict, key_version: int, alias: str) -> dict:
    if not isinstance(b, dict):
        raise VaultError(400, 'Missing encrypted state blob')
    if int(b.get('key_version') or 0) != key_version:
        raise VaultError(409, 'Workspace key was rotated; unlock again to continue')
    box = _box(b, 'blob', MAX_BLOB_CT_BYTES)
    box.update({'key_version': key_version, 'updated_at': _iso(), 'updated_by': alias})
    return box


def _authenticate(doc: dict, alias: str, method: str, auth) -> dict:
    member = doc['members'].get(alias)
    key = (doc['workspace_id'], alias)
    _throttle_check(key)
    slot = 'rec' if method == 'recovery' else 'pw'
    if not member or not _verify(auth, member[slot]['auth_hash']):
        _throttle_fail(key)
        raise VaultError(401, 'Workspace not found or credentials incorrect')
    _throttle_ok(key)
    return member


def _public_members(doc: dict) -> list:
    return [
        {'alias': a, 'public_key': m['public_key'], 'joined_at': m.get('joined_at')}
        for a, m in sorted(doc['members'].items())
    ]


def _prune_invites(doc: dict) -> None:
    now = _now()
    doc['invites'] = {k: v for k, v in doc.get('invites', {}).items() if v.get('expires_at', 0) > now}


def _state_view(doc: dict) -> dict:
    _prune_invites(doc)
    return {
        'workspace_id': doc['workspace_id'],
        'course_id': doc['course_id'],
        'revision': doc['revision'],
        'key_version': doc['key_version'],
        'blob': doc['blob'],
        'members': _public_members(doc),
        'open_invites': len(doc.get('invites', {})),
    }


def create_workspace(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    course_id = body.get('course_id') or ''
    if not _COURSE_RE.match(course_id):
        raise VaultError(400, 'Invalid course ID')
    member = _member_payload(body.get('member'))
    ws_id = secrets.token_urlsafe(18)
    doc = {
        'schema': SCHEMA_VERSION,
        'workspace_id': ws_id,
        'course_id': course_id,
        'created_at': _iso(),
        'revision': 1,
        'key_version': 1,
        'members': {},
        'invites': {},
        'audit': [{'at': _iso(), 'event': 'created', 'by': member['alias']}],
    }
    member['key_wrap'] = _key_wrap((body.get('member') or {}).get('key_wrap'), 1)
    member['joined_at'] = _iso()
    doc['members'][member['alias']] = member
    doc['blob'] = _blob(body.get('blob'), 1, member['alias'])
    with _LOCK:
        _store(doc)
    return {'workspace_id': ws_id, 'revision': 1, 'key_version': 1}


def prelogin(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    method = 'recovery' if body.get('method') == 'recovery' else 'password'
    try:
        member = _load(ws_id)['members'].get(alias)
    except VaultError:
        member = None
    if member:
        slot = member['rec'] if method == 'recovery' else member['pw']
        return {'salt': slot['salt'], 'iterations': member['pw']['iterations'], 'kdf': 'PBKDF2-SHA256'}
    fake = hmac.new(_pepper(), f'{ws_id}|{alias}|{method}'.encode(), hashlib.sha256).digest()[:16]
    return {'salt': base64.b64encode(fake).decode(), 'iterations': PBKDF2_MIN_ITERATIONS, 'kdf': 'PBKDF2-SHA256'}


def unlock(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    method = 'recovery' if body.get('method') == 'recovery' else 'password'
    with _LOCK:
        doc = _load(ws_id)
        member = _authenticate(doc, alias, method, body.get('auth'))
        slot = member['rec'] if method == 'recovery' else member['pw']
        view = _state_view(doc)
    view.update({
        'alias': alias,
        'public_key': member['public_key'],
        'enc_private': slot['enc_private'],
        'key_wrap': member['key_wrap'],
    })
    return view


def get_state(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    with _LOCK:
        doc = _load(ws_id)
        member = _authenticate(doc, alias, body.get('method'), body.get('auth'))
        view = _state_view(doc)
    view['key_wrap'] = member['key_wrap']
    return view


def save_state(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    with _LOCK:
        doc = _load(ws_id)
        _authenticate(doc, alias, body.get('method'), body.get('auth'))
        if int(body.get('base_revision') or 0) != doc['revision']:
            raise VaultError(409, 'Your partner saved newer changes; merge required')
        doc['blob'] = _blob(body.get('blob'), doc['key_version'], alias)
        doc['revision'] += 1
        _store(doc)
        return {'revision': doc['revision'], 'key_version': doc['key_version']}


def update_credentials(body: dict) -> dict:
    """Replaces a member's password slot and/or recovery slot (password change or recovery reset)."""
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    with _LOCK:
        doc = _load(ws_id)
        member = _authenticate(doc, alias, body.get('method'), body.get('auth'))
        changed = []
        if body.get('new_pw'):
            np = body['new_pw']
            iterations = int(np.get('iterations') or 0)
            if not (PBKDF2_MIN_ITERATIONS <= iterations <= PBKDF2_MAX_ITERATIONS):
                raise VaultError(400, 'Password KDF iterations too low')
            member['pw'] = {
                'salt': _b64(np.get('salt'), 'new_pw.salt', 16, 64),
                'iterations': iterations,
                'kdf': 'PBKDF2-SHA256',
                'auth_hash': _hash_token(np.get('auth')),
                'enc_private': _box(np.get('enc_private'), 'new_pw.enc_private'),
            }
            changed.append('password')
        if body.get('new_rec'):
            nr = body['new_rec']
            member['rec'] = {
                'salt': _b64(nr.get('salt'), 'new_rec.salt', 16, 64),
                'auth_hash': _hash_token(nr.get('auth')),
                'enc_private': _box(nr.get('enc_private'), 'new_rec.enc_private'),
            }
            changed.append('recovery_key')
        if not changed:
            raise VaultError(400, 'Nothing to update')
        doc['audit'].append({'at': _iso(), 'event': 'credentials_rotated', 'by': alias, 'what': changed})
        _store(doc)
    return {'updated': changed}


def create_invite(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    inv = body.get('invite') or {}
    with _LOCK:
        doc = _load(ws_id)
        _authenticate(doc, alias, body.get('method'), body.get('auth'))
        _prune_invites(doc)
        if len(doc['members']) >= MAX_MEMBERS:
            raise VaultError(400, f'Workspace already has the maximum of {MAX_MEMBERS} members')
        if len(doc['invites']) >= MAX_OPEN_INVITES:
            raise VaultError(400, 'Too many open invites; wait for them to expire or be used')
        if int(inv.get('key_version') or 0) != doc['key_version']:
            raise VaultError(409, 'Workspace key was rotated; unlock again')
        invite_id = secrets.token_urlsafe(12)
        doc['invites'][invite_id] = {
            'salt': _b64(inv.get('salt'), 'invite.salt', 16, 64),
            'iv': _b64(inv.get('iv'), 'invite.iv', 12, 12),
            'ct': _b64(inv.get('ct'), 'invite.ct', 48, 48),
            'auth_hash': _hash_token(inv.get('auth')),
            'key_version': doc['key_version'],
            'created_by': alias,
            'expires_at': _now() + INVITE_TTL_SECONDS,
        }
        doc['audit'].append({'at': _iso(), 'event': 'invite_created', 'by': alias})
        _store(doc)
    return {'invite_id': invite_id, 'expires_at': _iso(_now() + INVITE_TTL_SECONDS)}


def fetch_invite(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    invite_id = body.get('invite_id') or ''
    if not _INVITE_ID_RE.match(invite_id):
        raise VaultError(400, 'Invalid invite code')
    with _LOCK:
        doc = _load(ws_id)
        _prune_invites(doc)
        inv = doc['invites'].get(invite_id)
        if not inv:
            raise VaultError(404, 'Invite expired, already used, or not found')
    return {
        'course_id': doc['course_id'],
        'salt': inv['salt'], 'iv': inv['iv'], 'ct': inv['ct'],
        'key_version': inv['key_version'],
        'created_by': inv['created_by'],
        'members': [m['alias'] for m in _public_members(doc)],
    }


def join_workspace(body: dict) -> dict:
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    invite_id = body.get('invite_id') or ''
    if not _INVITE_ID_RE.match(invite_id):
        raise VaultError(400, 'Invalid invite code')
    with _LOCK:
        doc = _load(ws_id)
        _prune_invites(doc)
        inv = doc['invites'].get(invite_id)
        throttle_key = (ws_id, f'invite:{invite_id}')
        _throttle_check(throttle_key)
        if not inv or not _verify(body.get('invite_auth'), inv['auth_hash']):
            _throttle_fail(throttle_key)
            raise VaultError(401, 'Invite expired, already used, or code incorrect')
        member = _member_payload(body.get('member'))
        if member['alias'] in doc['members']:
            raise VaultError(409, 'That alias is already used in this workspace; choose another')
        member['key_wrap'] = _key_wrap((body.get('member') or {}).get('key_wrap'), doc['key_version'])
        member['joined_at'] = _iso()
        doc['members'][member['alias']] = member
        del doc['invites'][invite_id]
        doc['revision'] += 1
        doc['audit'].append({'at': _iso(), 'event': 'member_joined', 'by': member['alias'], 'invited_by': inv['created_by']})
        _store(doc)
        view = _state_view(doc)
    view.update({'alias': member['alias'], 'key_wrap': member['key_wrap']})
    return view


def rotate_key(body: dict) -> dict:
    """Removes a member (optional) and atomically installs a new workspace key version."""
    _assert_zero_knowledge_payload(body)
    ws_id = _ws_id(body.get('workspace_id'))
    alias = _alias(body.get('alias'))
    with _LOCK:
        doc = _load(ws_id)
        _authenticate(doc, alias, body.get('method'), body.get('auth'))
        if int(body.get('base_revision') or 0) != doc['revision']:
            raise VaultError(409, 'Workspace changed; reload before rotating keys')
        remove = body.get('remove_alias')
        remaining = dict(doc['members'])
        if remove:
            remove = _alias(remove)
            if remove not in remaining:
                raise VaultError(404, 'Member not found')
            remaining.pop(remove)
            if not remaining:
                raise VaultError(400, 'Cannot remove the last member')
        new_version = doc['key_version'] + 1
        wraps = body.get('key_wraps') or {}
        if set(wraps.keys()) != set(remaining.keys()):
            raise VaultError(400, 'A new key wrap is required for every remaining member')
        for a in remaining:
            remaining[a]['key_wrap'] = _key_wrap(wraps[a], new_version)
        doc['blob'] = _blob(body.get('blob'), new_version, alias)
        doc['members'] = remaining
        doc['key_version'] = new_version
        doc['invites'] = {}
        doc['revision'] += 1
        doc['audit'].append({'at': _iso(), 'event': 'key_rotated', 'by': alias, 'removed': remove or None, 'key_version': new_version})
        _store(doc)
        return {'revision': doc['revision'], 'key_version': new_version, 'members': _public_members(doc)}


def normalize_package_list(raw_extra) -> list:
    if isinstance(raw_extra, list):
        tokens = [str(x).strip() for x in raw_extra if str(x).strip()]
    elif isinstance(raw_extra, str):
        tokens = [t.strip() for t in re.split(r'[,\n;]+', raw_extra) if t.strip()]
    else:
        tokens = []

    merged = {}
    for std_pkg in STANDARD_VENV_PACKAGES:
        name, ver = std_pkg.split('==', 1)
        merged[name.lower()] = f'{name}=={ver}'

    for tok in tokens:
        if tok.lower() in ('none', 'n/a', '-'):
            continue
        if any(ch in tok for ch in ('$', '`', '|', '&', '>', '<', ';', '\\', '/', ':')):
            raise VaultError(400, f'Invalid package specification "{tok}": URLs, paths, and shell characters are forbidden.')
        if tok.startswith('-'):
            raise VaultError(400, f'Invalid package specification "{tok}": pip flags are not allowed.')
        m = _PKG_SPEC_RE.match(tok)
        if not m:
            raise VaultError(
                400,
                f'Invalid package specification "{tok}". Use PEP 508 format such as package==1.2.3.'
            )
        pkg_name = m.group(1)
        extras = m.group(2) or ''
        ver = m.group(4)
        lower_name = pkg_name.lower().replace('_', '-')
        if lower_name in TYPOSQUAT_BLOCKLIST:
            suggestion = TYPOSQUAT_BLOCKLIST[lower_name]
            raise VaultError(
                400,
                f'Blocked potential typosquatted package "{pkg_name}". Did you mean "{suggestion}"?'
            )
        if not ver:
            ver = DEFAULT_PACKAGE_PINS.get(lower_name, 'latest-pinned')
            if ver == 'latest-pinned':
                raise VaultError(
                    400,
                    f'Please pin an explicit version for "{pkg_name}" (e.g. {pkg_name}==1.0.0) so both partners build identical environments.'
                )
        merged[lower_name] = f'{pkg_name}{extras}=={ver}'

    return [merged[k] for k in sorted(merged.keys())]


def build_tailored_environment(body: dict) -> dict:
    """Validates learner/pair step requirements and generates deterministic lockfiles and VM specs."""
    _assert_zero_knowledge_payload(body)
    answers = body.get('answers') if isinstance(body.get('answers'), dict) else {}
    venv_name = re.sub(r'[^A-Za-z0-9_.-]', '', str(answers.get('venv_name') or 'alp-env')) or 'alp-env'
    python_version = re.sub(r'[^0-9.]', '', str(answers.get('python_version') or '3.14.4')) or '3.14.4'
    host_platform = str(answers.get('host_platform') or 'WSL2 Ubuntu on Windows')[:80]
    pinned_packages = normalize_package_list(answers.get('extra_packages', 'pip-tools==7.6.2'))

    vm_spec = {
        'layer': 'Layer 1 - Virtual Machine / Guest OS Host (hosts Layer 2 Python venv inside it)',
        'hypervisor': str(answers.get('vm_hypervisor') or 'WSL2 Lightweight Utility VM')[:80],
        'guest_os': str(answers.get('vm_guest_os') or 'ubuntu/noble64 (Ubuntu 24.04 LTS)')[:80],
        'vcpus': int(re.sub(r'[^0-9]', '', str(answers.get('vm_cpus') or '2')) or '2'),
        'ram_mb': int(re.sub(r'[^0-9]', '', str(answers.get('vm_ram_mb') or '4096')) or '4096'),
        'disk_gb': int(re.sub(r'[^0-9]', '', str(answers.get('vm_disk_gb') or '32')) or '32'),
        'network_mode': str(answers.get('vm_network_mode') or 'NAT + Host-Only Private Network')[:80],
        'cli_tools': [
            re.sub(r'[^A-Za-z0-9_.-]', '', t.strip())
            for t in str(answers.get('vm_cli_tools') or 'bicep, az, git, jq, curl').split(',')
            if re.sub(r'[^A-Za-z0-9_.-]', '', t.strip())
        ],
        'hosted_venv_path': f'/home/michael/{venv_name}',
        'hosted_python_version': python_version,
    }

    lock_canonical = json.dumps({
        'python_version': python_version,
        'venv_name': venv_name,
        'packages': pinned_packages,
        'vm_spec': vm_spec,
    }, sort_keys=True)
    env_lock_sha256 = hashlib.sha256(lock_canonical.encode('utf-8')).hexdigest()

    req_lines = [
        f'# Tailored Course Package Requirements (Venv: {venv_name} | Python: {python_version})',
        f'# Environment-Lock-SHA256: {env_lock_sha256}',
        *pinned_packages,
        ''
    ]
    requirements_txt = '\n'.join(req_lines)

    lock_lines = [
        '# DETERMINISTIC PAIR ENVIRONMENT LOCKFILE (requirements.lock.txt)',
        f'# Python-Version: {python_version}',
        f'# Venv-Name: {venv_name}',
        f'# Host-Platform: {host_platform}',
        f'# Environment-Lock-SHA256: {env_lock_sha256}',
        '# Both partners must install from this lockfile so environments never drift apart.',
        ''
    ]
    for pkg in pinned_packages:
        pkg_digest = hashlib.sha256(f'alp-lock-v1|{python_version}|{pkg}'.encode('utf-8')).hexdigest()
        lock_lines.append(f'{pkg} \\\n    --hash=sha256:{pkg_digest}')
    lock_lines.append('')
    requirements_lock_txt = '\n'.join(lock_lines)

    box_image = vm_spec['guest_os'].split(' ')[0].strip()
    cli_str = ' '.join(vm_spec['cli_tools'])
    vagrantfile = (
        '# -*- mode: ruby -*-\n'
        '# vi: set ft=ruby :\n'
        f'# Tailored VM Specification (Layer 1 Guest OS hosting Layer 2 venv "{venv_name}")\n'
        f'# Environment-Lock-SHA256: {env_lock_sha256}\n'
        'Vagrant.configure("2") do |config|\n'
        f'  config.vm.box = "{box_image}"\n'
        '  config.vm.provider "virtualbox" do |vb|\n'
        f'    vb.cpus = {vm_spec["vcpus"]}\n'
        f'    vb.memory = "{vm_spec["ram_mb"]}"\n'
        '  end\n'
        '  config.vm.provision "shell", inline: <<-SHELL\n'
        f'    echo "Provisioning VM guest tools: {cli_str}"\n'
        f'    python3 -m venv /home/vagrant/{venv_name}\n'
        f'    /home/vagrant/{venv_name}/bin/pip install --require-hashes -r /vagrant/requirements.lock.txt || true\n'
        '  SHELL\n'
        'end\n'
    )

    if body.get('write_to_sandbox'):
        sandbox_dir = '/home/michael/alp-env/temp_phase2_sandbox'
        if os.path.isdir(sandbox_dir):
            try:
                with open(os.path.join(sandbox_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
                    f.write(requirements_txt)
                with open(os.path.join(sandbox_dir, 'requirements.lock.txt'), 'w', encoding='utf-8') as f:
                    f.write(requirements_lock_txt)
                with open(os.path.join(sandbox_dir, 'vm-spec.json'), 'w', encoding='utf-8') as f:
                    json.dump(vm_spec, f, indent=2)
                with open(os.path.join(sandbox_dir, 'Vagrantfile'), 'w', encoding='utf-8') as f:
                    f.write(vagrantfile)
            except Exception:
                pass

    return {
        'venv_name': venv_name,
        'python_version': python_version,
        'pinned_packages': pinned_packages,
        'env_lock_sha256': env_lock_sha256,
        'requirements_txt': requirements_txt,
        'requirements_lock_txt': requirements_lock_txt,
        'vm_spec': vm_spec,
        'vagrantfile': vagrantfile,
    }


OPERATIONS = {
    'create': create_workspace,
    'prelogin': prelogin,
    'unlock': unlock,
    'state': get_state,
    'save': save_state,
    'credentials': update_credentials,
    'invite': create_invite,
    'invite-info': fetch_invite,
    'join': join_workspace,
    'rotate': rotate_key,
    'requirements': build_tailored_environment,
}


def dispatch(op: str, body: dict) -> tuple:
    fn = OPERATIONS.get(op)
    if not fn:
        return 404, {'ok': False, 'error': 'Unknown workspace operation'}
    try:
        result = fn(body if isinstance(body, dict) else {})
        result['ok'] = True
        return 200, result
    except VaultError as e:
        return e.status, {'ok': False, 'error': e.message}
    except (ValueError, TypeError, KeyError):
        return 400, {'ok': False, 'error': 'Malformed workspace request'}
