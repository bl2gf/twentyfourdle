import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import server
from game import puzzle,solve

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        server.DB_PATH=Path(cls.temp.name)/'test.db'
        server.initialize()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()

    def client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self,client,path,body=None):
        request=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with client.open(request) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_two_players_spoilers_and_persistence(self):
        alice,bob,outsider=self.client(),self.client(),self.client()
        self.assertEqual(self.call(alice,'submit',{})[0],401)
        a=self.call(alice,'profile',{'name':'Alice'})[1]
        key=a['recoveryKey']
        self.call(bob,'profile',{'name':'Bob'})
        a=self.call(alice,'clubs',{'name':'Math pals'})[1]
        code=a['clubs'][0]['id']
        self.assertEqual(self.call(bob,'join',{'code':code})[0],200)
        self.call(outsider,'profile',{'name':'Outsider'})
        self.assertEqual(self.call(outsider,'state')[1]['clubs'],[])
        a=self.call(alice,'start',{})[1]
        started=a['attempt']['started']
        self.assertEqual(self.call(alice,'start',{})[1]['attempt']['started'],started)
        answer=solve(tuple(a['cards']))['expression']
        a=self.call(alice,'submit',{'day':a['day'],'expression':answer})[1]
        self.assertIsNotNone(a['attempt']['elapsed'])
        elapsed=a['attempt']['elapsed']
        self.assertEqual(self.call(alice,'submit',{'day':a['day'],'expression':answer})[1]['attempt']['elapsed'],elapsed)
        b=self.call(bob,'state')[1]
        self.assertIsNone(b['cards'])
        self.assertIsNone(b['optimal'])
        self.assertIsNone(b['clubs'][0]['players'][0]['first_expression'])
        b=self.call(bob,'start',{})[1]
        b=self.call(bob,'submit',{'day':b['day'],'expression':answer})[1]
        self.assertTrue(all(p['first_expression'] for p in b['clubs'][0]['players']))
        restored=self.client()
        a2=self.call(restored,'recover',{'key':key})[1]
        self.assertEqual(a2['attempt']['elapsed'],elapsed)
        self.assertIsNone(self.call(alice,'state')[1]['player'])
        with patch('server.today',return_value='2027-01-01'):
            self.assertIsNone(self.call(restored,'state')[1]['attempt'])
            self.assertEqual(self.call(restored,'submit',{'day':a['day'],'expression':answer})[0],400)

    def test_cross_origin_rejected(self):
        request=urllib.request.Request(self.base+'/api/profile',data=b'{"name":"x"}',headers={'Content-Type':'application/json','Origin':'https://other.example'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(request)
        self.assertEqual(ctx.exception.code,403)

if __name__=='__main__':unittest.main()
