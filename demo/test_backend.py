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
    def test_chat_limits_busy_and_template(self):
        rt=Runtime.__new__(Runtime); rt.state='ready'; rt.args=type('Args',(),{'command':'solo'})()
        rt.chat_lock=threading.Lock(); rt.chat_lock.acquire()
        self.assertEqual(rt.chat({})[0],409); rt.chat_lock.release()
        rt.tokenizer=type('Tokenizer',(),{'apply_chat_template':lambda self,*a,**kw:[1]*500})()
        with self.assertRaisesRegex(ValueError,'512'): rt.chat({'messages':[{'role':'user','content':'hi'}]})
        self.assertFalse(rt.chat_lock.locked())

if __name__=='__main__': unittest.main()
