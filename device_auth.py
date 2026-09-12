"""Local WebAuthn verification. No broker calls; grants are scoped and single use."""
import base64
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

from webauthn import (generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response, options_to_json,
    base64url_to_bytes)
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
    AuthenticatorAttachment, UserVerificationRequirement, PublicKeyCredentialDescriptor)

ORIGIN = 'http://localhost:8642'
RP_ID = 'localhost'
LOCK = threading.RLock()
SESSIONS = {}
CHALLENGES = {}
TTL = 120


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def atomic_json(path, value):
    """Private, durable replace. Used before submission as well as for keys."""
    path = Path(path)
    path.parent.mkdir(exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(value, f, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
    finally:
        if name and os.path.exists(name): os.unlink(name)


def read(root):
    try:
        data = json.loads((Path(root)/'.device-auth.json').read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError('Device settings could not be read. Approval is blocked until they are repaired.') from exc
    if (not isinstance(data, dict) or data.get('version') != 1
        or not all(isinstance(data.get(k), str) and data[k] for k in ('credential_id','public_key','user_id'))
        or type(data.get('sign_count')) is not int or data['sign_count'] < 0
        or not isinstance(data.get('modes'), list) or any(m not in ('paper','live') for m in data['modes'])
        or type(data.get('tested')) is not bool):
        raise ValueError('Invalid device settings. Approval is blocked.')
    return data


def status(root):
    with LOCK:
        d = read(root)
        return {'ok': True, 'registered': bool(d), 'tested': bool(d and d['tested']),
                'modes': d['modes'] if d else []}


def method(root, mode):
    return 'device' if mode in status(root)['modes'] else 'pin'


def session():
    with LOCK:
        now = time.time()
        for key in list(SESSIONS):
            if SESSIONS[key] <= now: del SESSIONS[key]
        if len(SESSIONS) >= 100:
            raise ValueError('Too many device sessions. Close extra tabs and try later.')
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = now + 1800
        return {'ok': True, 'session': token}


def require_session(token):
    if not isinstance(token, str) or SESSIONS.get(token, 0) <= time.time():
        raise ValueError('Your device session expired. Reload Lens and review again.')


def new_challenge(session_id, purpose, **extra):
    require_session(session_id)
    now = time.time()
    for key in list(CHALLENGES):
        if CHALLENGES[key]['expires'] <= now or CHALLENGES[key]['session'] == session_id:
            del CHALLENGES[key]
    if len(CHALLENGES) >= 100:
        raise ValueError('Too many pending device prompts. Try again shortly.')
    token, challenge = secrets.token_urlsafe(24), secrets.token_bytes(32)
    CHALLENGES[token] = dict(session=session_id, purpose=purpose, challenge=challenge,
                             expires=now+TTL, **extra)
    return token, challenge


def take(payload, session_id, purpose):
    require_session(session_id)
    key = payload.get('challenge_id')
    c = CHALLENGES.get(key) if isinstance(key, str) else None
    if not c or c['session'] != session_id or c['purpose'] != purpose:
        raise ValueError('Device approval does not match this action. Try again.')
    del CHALLENGES[key]
    if c['expires'] <= time.time():
        raise ValueError('Device approval expired. Review again.')
    return c


def check_context(credential):
    try:
        client = json.loads(base64url_to_bytes(credential['response']['clientDataJSON']))
        if client.get('crossOrigin', False) is not False or client.get('topOrigin'):
            raise ValueError()
    except Exception as exc:
        raise ValueError('Device approval must come from the Lens page itself.') from exc


def options(root, session_id, purpose):
    with LOCK:
        d = read(root)
        if not d: raise ValueError('Set up device approval first.')
        cid, challenge = new_challenge(session_id, purpose, credential_id=d['credential_id'])
        opts = generate_authentication_options(rp_id=RP_ID, challenge=challenge, timeout=TTL*1000,
            allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(d['credential_id']))],
            user_verification=UserVerificationRequirement.REQUIRED)
        return {'ok':True, 'challenge_id':cid, 'options':json.loads(options_to_json(opts))}


def verify(root, payload, session_id, purpose):
    with LOCK:
        c = take(payload, session_id, purpose)
        d = read(root)
        credential = payload.get('credential')
        if not d or c['credential_id'] != d['credential_id'] or not isinstance(credential, dict):
            raise ValueError('This credential is no longer registered.')
        check_context(credential)
        try:
            if (base64url_to_bytes(credential['rawId']) != base64url_to_bytes(d['credential_id'])
                or base64url_to_bytes(credential['id']) != base64url_to_bytes(d['credential_id'])):
                raise ValueError()
            handle = credential['response'].get('userHandle')
            if handle and base64url_to_bytes(handle) != base64url_to_bytes(d['user_id']):
                raise ValueError()
            result = verify_authentication_response(credential=credential, expected_challenge=c['challenge'],
                expected_rp_id=RP_ID, expected_origin=ORIGIN, require_user_verification=True,
                credential_public_key=base64url_to_bytes(d['public_key']), credential_current_sign_count=d['sign_count'])
        except Exception as exc:
            raise ValueError('Device verification failed. No orders were approved. Try again.') from exc
        d['sign_count'] = result.new_sign_count
        d['backed_up'] = result.credential_backed_up
        atomic_json(Path(root)/'.device-auth.json', d)
        return d


def api(root, action, payload, session_id, pin_check):
    with LOCK:
        require_session(session_id)
        if action == 'status': return status(root)
        if action == 'reset-enrollment':
            d=read(root)
            if not d or d['modes']:
                raise ValueError('Return both modes to PIN with device verification before replacing the credential.')
            ok, why=pin_check(payload.get('pin',''))
            if not ok: raise ValueError(why)
            (Path(root)/'.device-auth.json').unlink()
            CHALLENGES.clear()
            import approval
            approval.REVIEWS.clear()
            return status(root)
        if action == 'register-options':
            if read(root): raise ValueError('A device credential is already registered.')
            ok, why = pin_check(payload.get('pin', ''))
            if not ok: raise ValueError(why)
            user = secrets.token_bytes(32)
            cid, challenge = new_challenge(session_id, 'register', user_id=encode(user))
            opts = generate_registration_options(rp_id=RP_ID, rp_name='Lens local investing',
                user_id=user, user_name='Lens '+encode(user)[:8], user_display_name='Your local Lens space',
                challenge=challenge, timeout=TTL*1000,
                authenticator_selection=AuthenticatorSelectionCriteria(
                    authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                    user_verification=UserVerificationRequirement.REQUIRED))
            return {'ok':True, 'challenge_id':cid, 'options':json.loads(options_to_json(opts))}
        if action == 'register-verify':
            c = take(payload, session_id, 'register')
            if read(root): raise ValueError('A credential was already registered. Reload Lens.')
            credential = payload.get('credential')
            check_context(credential)
            try:
                result = verify_registration_response(credential=credential, expected_challenge=c['challenge'],
                    expected_rp_id=RP_ID, expected_origin=ORIGIN, require_user_verification=True)
            except Exception as exc:
                raise ValueError('Device setup did not complete. No approval settings were changed.') from exc
            atomic_json(Path(root)/'.device-auth.json', dict(version=1, user_id=c['user_id'],
                credential_id=encode(result.credential_id), public_key=encode(result.credential_public_key),
                sign_count=result.sign_count, tested=False, modes=[], backed_up=result.credential_backed_up))
            return status(root)
        purposes = {'test':'test-only', 'enable-paper':'enable:paper', 'enable-live':'enable:live', 'disable':'disable'}
        for name, purpose in purposes.items():
            if action == name+'-options':
                if name != 'test':
                    d=read(root)
                    if not d or not d['tested']: raise ValueError('Complete the no-trade test first.')
                    ok, why=pin_check(payload.get('pin',''))
                    if not ok: raise ValueError(why)
                return options(root, session_id, purpose)
            if action == name+'-verify':
                d=verify(root, payload, session_id, purpose)
                if name == 'test': d['tested']=True
                elif name == 'disable': d['modes']=[]
                else: d['modes']=sorted(set(d['modes']+[name.removeprefix('enable-')]))
                atomic_json(Path(root)/'.device-auth.json', d)
                # No issued review survives an approval-method transition.
                if name != 'test':
                    import approval
                    approval.REVIEWS.clear()
                return dict(status(root), test_approved=name=='test')
        raise ValueError('Unknown device action.')
