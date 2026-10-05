"""Contract/security and scoped transport tests, without downloading a model."""
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from hwdetect import select
from helper import DelayedRelay, Helper
from app import Runtime, handler
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

class Tests(unittest.TestCase):
    def test_cpu_memory_worker_policy(self):
        with patch('hwdetect.hardware',return_value={'ram':{'free_mb':12000},'gpu':None}):
            device,count=select('cpu'); self.assertEqual(count,2); self.assertEqual(device['selected'],'cpu')
        with patch('hwdetect.hardware',return_value={'ram':{'free_mb':8000},'gpu':None}): self.assertEqual(select('cpu')[1],1)
        with patch('hwdetect.hardware',return_value={'ram':{'free_mb':2000},'gpu':None}):
            with self.assertRaisesRegex(RuntimeError,'RAM'): select('cpu')
    def test_force_gpu_failure(self):
        fake=type('Torch',(),{'cuda':type('Cuda',(),{'is_available':staticmethod(lambda:False)})})
        with patch.dict(sys.modules,torch=fake), patch('hwdetect.hardware',return_value={'ram':{'free_mb':8000},'gpu':None}):
            with self.assertRaisesRegex(RuntimeError,'Forced GPU'): select('cuda')
            self.assertEqual(select('auto')[0]['selected'],'cpu')
    def test_missing_token_rejects_every_post(self):
        rt=type('Runtime',(),{'token':'secret','args':type('Args',(),{'command':'solo'})})()
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(rt))
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            for endpoint in ('chat','worker','fault','mode','load','exit'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/{endpoint}',data=b'{}'))
                self.assertEqual(error.exception.code,403)
        finally: server.shutdown(); server.server_close()
    def test_helper_host_guard(self):
        rt=type('Runtime',(),{'processes':{}})()
        helper=Helper(rt,'10.0.0.1','secret')
        try:
            self.assertTrue(helper.authorize('10.0.0.1','secret'))
            self.assertFalse(helper.authorize('10.0.0.2','secret'))
            self.assertFalse(helper.authorize('10.0.0.1','wrong'))
            with self.assertRaises(ValueError): helper.action('shell')
        finally: helper.close()
    def test_transport_delay_only_proxy(self):
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
        def echo():
            conn,_=listener.accept()
            with conn: conn.sendall(conn.recv(64))
        threading.Thread(target=echo,daemon=True).start()
        relay=DelayedRelay(listener.getsockname()[1]); relay.delay=.1
        try:
            with socket.create_connection(('127.0.0.1',relay.port)) as client:
                start=time.monotonic(); client.sendall(b'hello'); self.assertEqual(client.recv(64),b'hello')
                self.assertGreaterEqual(time.monotonic()-start,.09)
        finally: relay.close(); listener.close()
    def test_monitor_waits_for_all_workers_and_restore(self):
        from types import SimpleNamespace
        def check(stages, initial='loading', stopped=False, crashed=False):
            rt=Runtime.__new__(Runtime)
            rt.args=SimpleNamespace(command='solo',device='cpu')
            rt.device={'selected':'cpu'}; rt.remote=None; rt.state=initial; rt.message=''; rt.events=[]; rt.generation=-1
            rt.lifecycle=threading.RLock(); rt.ports={'router_http':1,'controller_http':2}
            rt.recovery_started=None; rt.recoveries=[]; rt.ctrl_state={}; rt.stage_stats=[]
            rt.workers={'w1':{'name':'w1','local':True,'status':'up','port':3}, 'w2':{'name':'w2','local':True,'status':'stopped' if stopped else 'up','port':4}}
            rt.processes={'w1':SimpleNamespace(poll=lambda:1 if crashed else None),'w2':SimpleNamespace(poll=lambda:None)}
            rt.closed=SimpleNamespace(wait=iter((False,True)).__next__)
            # The monitor calls wait(timeout); adapt a finite one-pass event.
            sequence=iter((False,True)); rt.closed.wait=lambda _:next(sequence)
            with patch('app.request',side_effect=lambda url: {'stages':stages,'generation':1} if url.endswith('/pipeline') else {'assignments':[]}): rt.monitor()
            return rt.state
        one=[{'name':'w1','addr':'127.0.0.1:3','layers':[0,28]}]
        both=[{'name':'w1','addr':'127.0.0.1:3','layers':[0,14]},{'name':'w2','addr':'127.0.0.1:4','layers':[14,28]}]
        self.assertEqual(check(one),'loading')
        self.assertEqual(check(one,initial='recovering'),'recovering')
        self.assertEqual(check(both),'ready')
        self.assertEqual(check(one,initial='recovering',stopped=True),'ready')
        self.assertEqual(check(both,initial='ready',crashed=True),'failed')

    def test_chat_limits_busy_and_template(self):
        rt=Runtime.__new__(Runtime); rt.state='ready'; rt.args=type('Args',(),{'command':'solo'})()
        rt.chat_lock=threading.Lock(); rt.chat_lock.acquire()
        rt.user_waiting=threading.Event(); rt.closed=threading.Event(); rt.history=[]
        # Background load never queues behind a busy pipeline...
        self.assertEqual(rt.chat({},background=True)[0],409)
        # ...but a person's message waits for the running request instead of failing.
        threading.Timer(.3,rt.chat_lock.release).start()
        start=time.monotonic()
        with self.assertRaises(KeyError): rt.chat({})
        self.assertGreaterEqual(time.monotonic()-start,.25)
        self.assertFalse(rt.user_waiting.is_set())
        rt.tokenizer=type('Tokenizer',(),{'apply_chat_template':lambda self,*a,**kw:[1]*500})()
        with self.assertRaisesRegex(ValueError,'512'): rt.chat({'messages':[{'role':'user','content':'hi'}]})
        self.assertFalse(rt.chat_lock.locked())

if __name__=='__main__': unittest.main()
