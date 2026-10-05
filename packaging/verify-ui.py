#!/usr/bin/env python3
"""Browser contract smoke test; requires Playwright + Chromium, never shipped in the app.
Run: python packaging/verify-ui.py --shots /tmp/shardwise-ui-shots
"""
import argparse
import asyncio
from pathlib import Path
import subprocess
import tempfile
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

async def verify(shots):
    shots.mkdir(parents=True, exist_ok=True)
    processes = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 1280, 'height': 720})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            urls = {}
            for name, flags in [('cpu', []), ('gpu-pair', ['--gpu', '--mode', 'host']), ('single', ['--single-worker']), ('join', ['--mode', 'join'])]:
                proc = subprocess.Popen(['python3', str(ROOT/'demo/mock_api.py'), '--port', '0', *flags], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                processes.append(proc)
                url = proc.stdout.readline().strip().removeprefix('MOCK: ')
                urls[name] = url
                await page.goto(url)
                assert await page.title() == 'Shardwise · Demo'
                assert await page.locator('h1').inner_text() == 'Shardwise'
                if name == 'cpu':
                    token = await page.evaluate('token')
                    response = await page.request.post(url+'/api/chat', data={'messages': [{'role': 'user', 'content': 'hello'}]}, headers={'X-Session-Token': token})
                    assert response.status == 503
                    for state in ['downloading', 'calibrating', 'loading']:
                        await page.wait_for_function("s => document.getElementById('state').textContent===s", arg=state)
                        await page.screenshot(path=str(shots/(state+'.png')), full_page=True)
                await page.wait_for_function("document.getElementById('state').textContent==='ready'")
                await page.screenshot(path=str(shots/(name+'.png')), full_page=True)
                await page.set_viewport_size({'width': 390, 'height': 844})
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), name
                await page.screenshot(path=str(shots/(name+'-phone.png')), full_page=True)
                await page.set_viewport_size({'width': 1280, 'height': 720})
                if name in ('single', 'join'):
                    assert await page.locator('#worker-controls button').count() == 0
                if name == 'join':
                    assert await page.locator('#send').is_disabled()
                    assert await page.locator('#execution').is_hidden()
            await page.goto(urls['cpu'])
            await page.wait_for_function("document.getElementById('state').textContent==='ready'")
            token = await page.evaluate('token')
            assert (await page.request.post(urls['cpu']+'/api/chat', data={}, headers={'X-Session-Token': 'wrong'})).status == 403
            chat = {'messages': [{'role': 'user', 'content': 'hello'}], 'max_new_tokens': 128}
            first = asyncio.create_task(page.request.post(urls['cpu']+'/api/chat', data=chat, headers={'X-Session-Token': token}))
            await asyncio.sleep(.2)
            assert (await page.request.post(urls['cpu']+'/api/chat', data=chat, headers={'X-Session-Token': token})).status == 409
            assert (await first).status == 200
            await page.locator('#prompt').fill('Explain the demo')
            await page.locator('#send').click()
            await page.wait_for_function("document.querySelector('.message.assistant')")
            assert '57 tokens' in await page.locator('.message.assistant').inner_text()
            await page.get_by_role('button', name='Inspect w1 layers').click()
            await page.get_by_role('button', name='Stop w2').click()
            await page.wait_for_function("document.getElementById('state').textContent==='recovering'")
            await page.screenshot(path=str(shots/'recovering.png'), full_page=True)
            await page.wait_for_function("document.getElementById('state').textContent==='ready'")
            assert await page.locator('#walk li.done').count() == 4
            assert await page.locator('.worker.w1 .assigned').count() == 28
            assert await page.get_by_role('button', name='Stop w1').is_disabled()
            await page.get_by_role('button', name='Restore w2').click()
            await page.wait_for_function("document.getElementById('state').textContent==='recovering'")
            await page.wait_for_function("document.getElementById('state').textContent==='ready'")
            assert await page.locator('#walk li.done').count() == 5
            await page.locator('#load').check()
            await page.wait_for_timeout(1100)
            assert await page.locator('#load').is_checked()
            await page.emulate_media(color_scheme='dark')
            await page.screenshot(path=str(shots/'dark.png'), full_page=True)
            await page.goto(urls['gpu-pair'])
            await page.get_by_role('button', name='Slow down').click()
            await page.wait_for_function("document.getElementById('events').textContent.includes('Mock fault slow')")
            await page.get_by_role('button', name='+100 ms transport delay').click()
            await page.wait_for_function("document.getElementById('events').textContent.includes('Mock fault net')")
            await page.get_by_role('button', name='Clear faults').click()
            await page.wait_for_function("document.getElementById('events').textContent.includes('Mock fault clear')")
            await page.goto(urls['cpu'])
            page.on('dialog', lambda dialog: dialog.accept())
            await page.locator('#execution').select_option('cpu')
            await page.wait_for_function("document.getElementById('state').textContent==='downloading'")
            await page.route('**/api/status', lambda route: route.abort())
            await page.route('**/api/hw', lambda route: route.abort())
            await page.wait_for_function("!document.getElementById('connection').hidden")
            await page.wait_for_function("document.getElementById('cpu').textContent.includes('unreachable')")
            await page.unroute('**/api/status')
            await page.unroute('**/api/hw')
            await page.wait_for_function("document.getElementById('connection').hidden")
            await page.wait_for_function("document.getElementById('state').textContent==='ready'")
            await page.get_by_role('button', name='Exit app').click()
            await page.wait_for_function("document.getElementById('state').textContent==='stopped'")
            assert not errors, errors
            await browser.close()
            print(f'PASS: startup states, CPU/GPU/Pair/single/phone/dark screenshots, auth, busy, chat, layer recovery, restore, load, faults, mode, reconnect, exit. Screenshots: {shots}')
    finally:
        for proc in processes:
            proc.terminate()
            proc.wait(timeout=5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shots', type=Path, default=Path(tempfile.gettempdir())/'shardwise-ui-shots')
    asyncio.run(verify(parser.parse_args().shots))
