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
from helper import Slowdown, TunnelHub, TunnelClient
from app import Runtime, handler
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

class Tests(unittest.TestCase):
    def test_cpu_memory_worker_policy(self):
        with patch('hwdetect.hardware',return_value={'ram':{'free_mb':12000},'gpu':None}):
            device,count=select('cpu'); self.assertEqual(count,2); self.assertEqual(device['selected'],'cpu')
        with patch('hwdetect.hardware',return_value={'ram':{'free_mb':6000},'gpu':None}): self.assertEqual(select('cpu')[1],1)
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
    def test_slowdown_rejects_nothing_and_closes(self):
        rt=type('Runtime',(),{'processes':{}})()
        slow=Slowdown(rt,'w2'); slow.set(True); self.assertTrue(slow.on.is_set()); slow.set(False); slow.close()
    def test_reverse_tunnel_auth_and_delay(self):
        # The "worker" on the joined laptop: echoes what it receives.
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
        def echo():
            while True:
                try: conn,_=listener.accept()
                except OSError: return
                with conn: conn.sendall(conn.recv(64))
        threading.Thread(target=echo,daemon=True).start()
        hub=TunnelHub(0,lambda code,session: code=='12345678' and session=='s1')
        local=hub.register('s1')
        bad=TunnelClient('127.0.0.1',hub.port,'s1','00000000',listener.getsockname()[1],pool=1)
        good=TunnelClient('127.0.0.1',hub.port,'s1','12345678',listener.getsockname()[1],pool=2)
        try:
            deadline=time.monotonic()+5
            while hub.idle_count('s1')<2 and time.monotonic()<deadline: time.sleep(.05)
            self.assertEqual(hub.idle_count('s1'),2)  # the wrong code never enters the pool
            for delay in (0,.1):
                good.delay=delay
                with socket.create_connection(('127.0.0.1',local)) as client:
                    start=time.monotonic(); client.sendall(b'hello'); self.assertEqual(client.recv(64),b'hello')
                    self.assertGreaterEqual(time.monotonic()-start,delay*.9)
            hub.unregister('s1')
            with self.assertRaises(ConnectionRefusedError): socket.create_connection(('127.0.0.1',local),timeout=1)
        finally: bad.close(); good.close(); hub.close(); listener.close()
    def test_pair_code_normalisation(self):
        import app
        code=app.pair_code(); self.assertRegex(code,r'^[0-9]{4}-[0-9]{4}$')
        for typed in (code, code.replace('-',' '), code.replace('-',''), code.replace('-','\u2013'), ' '+code+' '):
            self.assertEqual(app.norm_code(typed), code.replace('-',''))
    def test_host_enrolls_many_laptops(self):
        from types import SimpleNamespace
        import app
        rt=Runtime.__new__(Runtime)
        rt.args=SimpleNamespace(command='host',pair_port=0); rt.pair_token='1234-5678'; rt.pair_failures=0
        rt.friends={}; rt.workers={'w1':{'name':'w1','local':True,'status':'up','port':3}}; rt.events=[]; rt.lifecycle=threading.RLock()
        rt.recovery_started=None; rt.unplaced=set(); rt.profile={'p':1}; rt.ports={'controller':8767}
        rt.hub=SimpleNamespace(port=8768,register=lambda s: 40000+len(s)%7,unregister=lambda s:None)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(rt,pair=True))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}'
        def post(path,body,code='1234 5678'):
            return json.load(urlopen(Request(url+path,data=json.dumps(body).encode(),headers={'X-Session-Token':code,'Content-Type':'application/json'})))
        try:
            names=[post('/enroll',{'node':f'laptop{i}'})['name'] for i in range(4)]
            self.assertEqual(names,['w2','w3','w4','w5'])
            again=post('/enroll',{'node':'laptop0','session':next(iter(rt.friends))})
            self.assertEqual(again['name'],'w2'); self.assertEqual(len(rt.friends),4)
            rt.workers['w2']['status']='down'  # laptop0 crashed and starts over without its session
            self.assertEqual(post('/enroll',{'node':'laptop0'})['name'],'w2'); self.assertEqual(len(rt.friends),4)
            with self.assertRaises(HTTPError) as e: post('/enroll',{'node':'x'},code='1234-0000')
            self.assertEqual(e.exception.code,403)
            with self.assertRaises(HTTPError) as e: post('/poll',{'session':'nope'})
            self.assertEqual(e.exception.code,410)
            session=next(s for s,f in rt.friends.items() if f['name']=='w3')
            rt.friends[session]['commands'].append({'type':'worker','action':'stop'})
            with patch.object(Runtime,'status',lambda self: {'app_state':'ready','workers':[],'pairing':{},'events':[]}):
                reply=post('/poll',{'session':session,'running':True})
            self.assertEqual(reply['commands'],[{'type':'worker','action':'stop'}]); self.assertEqual(rt.friends[session]['commands'],[])
            post('/leave',{'session':session}); self.assertNotIn('w3',rt.workers); self.assertEqual(len(rt.friends),3)
            self.assertEqual(post('/enroll',{'node':'late'})['name'],'w3')  # freed name is reused
            rt.pair_failures=20
            with self.assertRaises(HTTPError) as e: post('/check',{})
            self.assertEqual(e.exception.code,429)
        finally: server.shutdown(); server.server_close()
    def test_monitor_waits_for_all_workers_and_restore(self):
        from types import SimpleNamespace
        def check(stages, initial='loading', stopped=False, crashed=False):
            rt=Runtime.__new__(Runtime)
            rt.args=SimpleNamespace(command='solo',device='cpu')
            rt.device={'selected':'cpu'}; rt.friends={}; rt.unplaced=set(); rt.state=initial; rt.message=''; rt.events=[]; rt.generation=-1
            rt.lifecycle=threading.RLock(); rt.ports={'router_http':1,'controller_http':2}
            rt.recovery_started=None; rt.recoveries=[]; rt.ctrl_state={}; rt.stage_stats=[]
            rt.workers={'w1':{'name':'w1','local':True,'status':'up','port':3}, 'w2':{'name':'w2','local':True,'status':'stopped' if stopped else 'up','port':4}}
            rt.processes={'w1':SimpleNamespace(poll=lambda:1 if crashed else None),'w2':SimpleNamespace(poll=lambda:None)}
            rt.closed=SimpleNamespace(wait=iter((False,True)).__next__)
            # The monitor calls wait(timeout); adapt a finite one-pass event.
            sequence=iter((False,True)); rt.closed.wait=lambda _:next(sequence)
            with patch('app.request',side_effect=lambda url: {'stages':stages,'generation':1} if url.endswith('/pipeline') else {'assignments':[]}): rt.monitor()
            return rt.state
        import app; n=app.LAYERS
        one=[{'name':'w1','addr':'127.0.0.1:3','layers':[0,n]}]
        both=[{'name':'w1','addr':'127.0.0.1:3','layers':[0,n//2]},{'name':'w2','addr':'127.0.0.1:4','layers':[n//2,n]}]
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

    def test_wsl_detection_and_browser_never_crash(self):
        import app
        with patch('app.Path.read_text',return_value='5.15.153.1-microsoft-standard-WSL2'), patch('app.lan_ip',return_value='172.29.1.5'):
            self.assertEqual(app.wsl(),'nat')
        with patch('app.Path.read_text',return_value='5.15.153.1-microsoft-standard-WSL2'), patch('app.lan_ip',return_value='192.168.1.20'):
            self.assertEqual(app.wsl(),'mirrored')
        with patch('app.Path.read_text',return_value='6.8.0-generic'):
            self.assertIsNone(app.wsl())
        with patch('app.wsl',return_value='nat'), patch('app.subprocess.Popen',side_effect=FileNotFoundError):
            app.open_browser('http://127.0.0.1:1')  # must not raise

if __name__=='__main__': unittest.main()
