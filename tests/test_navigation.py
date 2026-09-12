"""Navigation, local home state and setup migration; no real broker access."""
import io
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
import home
import navigation
import personal_space
import webdash
import workspace

ROOT=Path(__file__).resolve().parents[1]

class Elements(HTMLParser):
    def __init__(self): super().__init__();self.ids=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href'))

class NavigationTests(unittest.TestCase):
    def test_every_destination_has_unique_ids_and_the_shared_three_primary_links(self):
        for route,file in navigation.PAGES.items():
            markup=navigation.render((ROOT/file).read_text(),route)
            parser=Elements();parser.feed(markup)
            self.assertEqual(len(parser.ids),len(set(parser.ids)),route)
            nav=markup.split('aria-label="Main navigation">')[1].split('</nav>')[0]
            for url in ['href="/"','href="/portfolio/holdings"','href="/invest"']:self.assertIn(url,nav)
            self.assertEqual(nav.count('<a '),3,route)
            self.assertIn('href="/profile"',markup)
            self.assertIn('data-lens-route="'+route+'"',markup)

    def test_profile_sections_and_portfolio_source_shortcut_resolve(self):
        source=navigation.render((ROOT/'workspace.html').read_text(),'/portfolio')
        self.assertIn('href="/profile/data/sources">Data sources ↗',source)
        for route in ['/profile/activity','/profile/data','/profile/data/sources','/profile/settings']:
            source=navigation.render((ROOT/navigation.PAGES[route]).read_text(),route)
            self.assertIn('aria-label="Profile sections"',source)
        for target in navigation.ALIASES.values():self.assertIn(target,navigation.PAGES)

    def test_http_aliases_and_pages_do_not_mutate_or_contact_broker(self):
        def get(path):
            h=object.__new__(webdash.Handler);h.path=path;h.wfile=io.BytesIO();codes=[];headers={}
            h.send_response=codes.append;h.send_header=lambda k,v:headers.update({k:v});h.end_headers=lambda:None
            h.do_GET();return codes[-1],headers,h.wfile.getvalue()
        with patch.object(webdash,'run_step') as run,patch.object(webdash.gateway,'status') as broker:
            for old,target in navigation.ALIASES.items():
                code,headers,_=get(old);self.assertEqual(code,302);self.assertEqual(headers['Location'],target)
            for route in navigation.PAGES:
                code,headers,body=get(route);self.assertEqual(code,200,route);self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertIn(b'/navigation.js',body)
            run.assert_not_called();broker.assert_not_called()

class SetupAndHomeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        for obj,key,value in [(workspace,'HERE',self.root),(workspace,'DATA',self.root/'.workspace'),(webdash,'HERE',self.root)]:
            p=patch.object(obj,key,value);p.start();self.addCleanup(p.stop)

    def test_legacy_profile_keeps_setup_and_new_profiles_remember_completion(self):
        folder=self.root/'.workspace';folder.mkdir();path=folder/'profile.json'
        original=json.dumps(dict(version=1,first_name='Ada',created_at='2026-09-12'));path.write_text(original)
        self.assertTrue(personal_space.api('bootstrap',{})['profile']['setup_complete'])
        self.assertEqual(path.read_text(),original)
        path.unlink();p=personal_space.api('create',{'first_name':'Ada'})['profile'];self.assertFalse(p['setup_complete'])
        personal_space.api('update',{'first_name':'New'})
        self.assertFalse(personal_space.api('bootstrap',{})['profile']['setup_complete'])
        personal_space.api('complete-setup',{})
        self.assertTrue(personal_space.api('bootstrap',{})['profile']['setup_complete'])
        self.assertEqual(personal_space.api('bootstrap',{})['profile']['first_name'],'New')

    def test_http_cannot_finish_setup_without_a_pin(self):
        personal_space.api('create',{})
        def complete():
            h=object.__new__(webdash.Handler);h.path='/api/space/complete-setup';h.rfile=io.BytesIO(b'{}');h.wfile=io.BytesIO()
            h.headers={'Host':'localhost:8642','Origin':'http://localhost:8642','Content-Type':'application/json','Content-Length':'2'}
            codes=[];h.send_response=codes.append;h.send_header=lambda *a:None;h.end_headers=lambda:None;h.do_POST()
            return codes[-1]
        self.assertEqual(complete(),400)
        with patch.object(webdash,'pin_read',return_value={'hash':'test'}):self.assertEqual(complete(),200)
        self.assertTrue(personal_space.read_profile()['setup_complete'])
        self.assertFalse((self.root/'.device-auth.json').exists())

    def test_home_prioritizes_uncertain_submission_and_only_reads_local_files(self):
        with patch.object(webdash.gateway,'status',side_effect=AssertionError('No broker')):
            self.assertEqual(home.summary(self.root)['next_step']['href'],'/portfolio#portfolio')
            self.assertFalse(list(self.root.iterdir()))
            (self.root/'state.paper.pending').write_text('1')
            (self.root/'state.live.pending').write_text('2')
            out=home.summary(self.root)
            self.assertIn('live submission',out['next_step']['description'])
            self.assertIn('uncertain',out['next_step']['description'])
            self.assertEqual(out['next_step']['href'],'/invest')
