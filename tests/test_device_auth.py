"""Synthetic ES256 authenticator: real WebAuthn verifier, no hardware or broker."""
import hashlib
import io
import json
import secrets
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cbor2
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
import device_auth as auth
import approval
import webdash


class Authenticator:
    def __init__(self):
        self.key=ec.generate_private_key(ec.SECP256R1())
        self.id=secrets.token_bytes(32)
        self.count=0

    def respond(self, options, register=False, origin=auth.ORIGIN, flags=None, rp='localhost'):
        client=json.dumps({'type':'webauthn.create' if register else 'webauthn.get',
            'challenge':options['options']['challenge'], 'origin':origin, 'crossOrigin':False}).encode()
        self.count+=1
        data=hashlib.sha256(rp.encode()).digest()+bytes([flags if flags is not None else 0x45 if register else 0x05])+struct.pack('>I',self.count)
        if register:
            numbers=self.key.public_key().public_numbers()
            cose=cbor2.dumps({1:2,3:-7,-1:1,-2:numbers.x.to_bytes(32,'big'),-3:numbers.y.to_bytes(32,'big')})
            data+=b'\0'*16+struct.pack('>H',len(self.id))+self.id+cose
            response={'attestationObject':auth.encode(cbor2.dumps({'fmt':'none','attStmt':{},'authData':data}))}
        else:
            signature=self.key.sign(data+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256()))
            response={'authenticatorData':auth.encode(data),'signature':auth.encode(signature)}
        response['clientDataJSON']=auth.encode(client)
        return {'challenge_id':options['challenge_id'],'credential':{'id':auth.encode(self.id),'rawId':auth.encode(self.id),'type':'public-key','response':response}}


class DeviceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        auth.SESSIONS.clear();auth.CHALLENGES.clear();approval.REVIEWS.clear()
        self.session=auth.session()['session'];self.device=Authenticator()

    def call(self, action, p=None):
        return auth.api(self.root,action,p or {},self.session,lambda pin:(pin=='1234','wrong PIN'))

    def enroll(self):
        opts=self.call('register-options',{'pin':'1234'})
        self.call('register-verify',self.device.respond(opts,True))

    def test_registration_test_and_separate_live_activation(self):
        self.enroll()
        self.assertEqual(auth.status(self.root)['modes'],[])
        with self.assertRaisesRegex(ValueError,'test first'):self.call('enable-live-options',{'pin':'1234'})
        opts=self.call('test-options')
        self.assertTrue(self.call('test-verify',self.device.respond(opts))['test_approved'])
        for mode in ['paper','live']:
            opts=self.call('enable-'+mode+'-options',{'pin':'1234'})
            self.call('enable-'+mode+'-verify',self.device.respond(opts))
            self.assertEqual(auth.method(self.root,mode),'device')
        opts=self.call('disable-options',{'pin':'1234'})
        self.call('disable-verify',self.device.respond(opts))
        self.assertEqual(auth.method(self.root,'live'),'pin')
        self.assertEqual((self.root/'.device-auth.json').stat().st_mode&0o777,0o600)

    def test_enrollment_requires_pin_and_does_not_overwrite(self):
        with self.assertRaises(ValueError):self.call('register-options',{'pin':'9999'})
        self.assertFalse((self.root/'.device-auth.json').exists())
        self.enroll()
        before=(self.root/'.device-auth.json').read_bytes()
        with self.assertRaises(ValueError):self.call('register-options',{'pin':'1234'})
        self.assertEqual((self.root/'.device-auth.json').read_bytes(),before)

    def test_real_verifier_rejects_wrong_origin_rp_key_and_missing_uv(self):
        self.enroll()
        for kwargs in [{'origin':'http://localhost:9999'},{'rp':'evil.example'},{'flags':1}]:
            with self.subTest(kwargs=kwargs):
                opts=self.call('test-options');proof=self.device.respond(opts,**kwargs)
                with self.assertRaises(ValueError):self.call('test-verify',proof)
        opts=self.call('test-options')
        with self.assertRaises(ValueError):self.call('test-verify',Authenticator().respond(opts))
        self.assertFalse(auth.status(self.root)['tested'])

    def test_replay_expiry_session_and_purpose_are_bound(self):
        self.enroll();opts=self.call('test-options');proof=self.device.respond(opts)
        with self.assertRaises(ValueError):auth.verify(self.root,proof,self.session,'orders:different')
        with self.assertRaises(ValueError):auth.verify(self.root,proof,auth.session()['session'],'test-only')
        self.call('test-verify',proof)
        with self.assertRaises(ValueError):self.call('test-verify',proof)
        opts=self.call('test-options');auth.CHALLENGES[opts['challenge_id']]['expires']=0
        with self.assertRaises(ValueError):self.call('test-verify',self.device.respond(opts))
        opts=self.call('test-options');auth.CHALLENGES.clear()
        with self.assertRaises(ValueError):self.call('test-verify',self.device.respond(opts))

    def test_tampered_signature_and_write_failure_cannot_approve(self):
        self.enroll();opts=self.call('test-options');proof=self.device.respond(opts)
        proof['credential']['response']['signature']=auth.encode(b'wrong')
        with self.assertRaises(ValueError):self.call('test-verify',proof)
        opts=self.call('test-options')
        with patch.object(auth,'atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.call('test-verify',self.device.respond(opts))
        self.assertFalse(auth.status(self.root)['tested'])

    def test_reset_requires_pin_and_cannot_bypass_active_device_mode(self):
        self.enroll()
        with self.assertRaises(ValueError):self.call('reset-enrollment',{'pin':'9999'})
        self.call('reset-enrollment',{'pin':'1234'})
        self.assertFalse(auth.status(self.root)['registered'])
        self.enroll()
        opts=self.call('test-options');self.call('test-verify',self.device.respond(opts))
        opts=self.call('enable-live-options',{'pin':'1234'});self.call('enable-live-verify',self.device.respond(opts))
        with self.assertRaises(ValueError):self.call('reset-enrollment',{'pin':'1234'})
        self.assertEqual(auth.method(self.root,'live'),'device')

    def test_corrupt_store_fails_closed_and_profile_has_no_authority(self):
        (self.root/'.device-auth.json').write_text('corrupt')
        with self.assertRaises(ValueError):auth.method(self.root,'paper')
        (self.root/'.device-auth.json').unlink()
        (self.root/'profile.json').write_text('{"device_approved":true}')
        self.assertEqual(auth.method(self.root,'live'),'pin')

    def test_http_auth_requires_exact_origin_and_session(self):
        def request(action, origin=None, session=None, host='localhost:8642'):
            h=object.__new__(webdash.Handler);h.path='/api/device/'+action
            h.headers={'Host':host,'Content-Type':'application/json','Content-Length':'2'}
            if origin:h.headers['Origin']=origin
            if session:h.headers['X-Lens-Session']=session
            h.rfile=io.BytesIO(b'{}');h.wfile=io.BytesIO();codes=[]
            h.send_response=codes.append;h.send_header=lambda *a:None;h.end_headers=lambda:None
            with patch.object(webdash,'HERE',self.root):h.do_POST()
            return codes[0],json.loads(h.wfile.getvalue())
        for origin in [None,'http://localhost:9999','https://localhost:8642']:
            self.assertEqual(request('session',origin)[0],403)
        self.assertEqual(request('status',auth.ORIGIN)[0],400)
        self.assertEqual(request('status',auth.ORIGIN,self.session)[0],200)
        self.assertEqual(request('status',auth.ORIGIN,self.session,'127.0.0.1:8642')[0],403)


if __name__=='__main__':unittest.main()
