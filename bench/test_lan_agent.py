import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

from lan_agent import handler


class LANProtocolTests(unittest.TestCase):
    def setUp(self):
        self.agent=SimpleNamespace(token='a'*24,status=Mock(return_value={'packages':{'torch':'2.8.0+cpu'}}),
            start=Mock(return_value={'worker_addr':'127.0.0.1:1'}),stop=Mock(),
            stop_worker=Mock(return_value={'action':'stopped owned worker'}),promote=Mock())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.agent))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close()
    def request(self,path,body=None,token='a'*24):
        return urllib.request.urlopen(urllib.request.Request(self.url+path,
            data=None if body is None else json.dumps(body).encode(),headers={'X-Lab-Token':token}),timeout=2)
    def test_unauthorized_control_never_reaches_process_operations(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/start',{'layers':[0,28]},token='bad')
        self.assertEqual(error.exception.code,403);self.agent.start.assert_not_called()
        self.agent.stop.assert_not_called();self.agent.stop_worker.assert_not_called()
    def test_stop_and_status_protocol(self):
        with self.request('/status') as response:self.assertEqual(json.load(response)['packages']['torch'],'2.8.0+cpu')
        with self.request('/stop-worker',{}) as response:self.assertEqual(json.load(response)['action'],'stopped owned worker')
        self.agent.stop_worker.assert_called_once();self.agent.stop.assert_not_called()
    def test_unknown_endpoint_never_starts_a_process(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/execute',{'command':'anything'})
        self.assertEqual(error.exception.code,404);self.agent.start.assert_not_called()


if __name__=='__main__':unittest.main()
