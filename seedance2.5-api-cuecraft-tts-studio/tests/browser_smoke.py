"""Optional browser integration test; simulated provider, no paid API calls."""
import os
import sys, tempfile, threading, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from tests.test_app import FakeProvider
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as temp:
    provider = FakeProvider()
    app = create_app(temp, provider)
    server = make_server('127.0.0.1', 8792, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROME_EXECUTABLE') or None, headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8792')
        page.get_by_role('button', name='Create your first project').click()
        page.click('#sample')
        assert 'Sample' in page.locator('#project-title').input_value()
        page.click('#project-form button[type=submit]')
        page.wait_for_selector('#project-dialog', state='hidden')
        assert page.locator('.cue-item').count() == 3
        page.fill('#cue-title', 'Opening revised')
        page.click('.cue-item:nth-child(2)')
        page.wait_for_function('() => document.querySelector("#cue-title").value === "Cue 02"')
        page.click('.cue-item:first-child')
        page.wait_for_function('() => document.querySelector("#cue-title").value === "Opening revised"')
        page.click('#generate')
        page.wait_for_selector('.status:has-text("SUCCESS")', timeout=20000)
        assert provider.submissions == 1
        page.fill('#cue-text', 'A changed script.')
        page.click('#save')
        page.wait_for_selector('.stale')
        assert page.locator('#export').is_disabled()
        page.on('dialog', lambda d: d.accept())
        page.click('#generate')
        page.wait_for_function('() => document.querySelectorAll(".status").length===2 && [...document.querySelectorAll(".status")].every(e=>e.textContent==="SUCCESS")', timeout=20000)
        assert provider.submissions == 2
        page.locator('[data-action=select]').first.click()
        page.wait_for_function('() => document.querySelector(".take").classList.contains("chosen")')
        page.reload()
        page.wait_for_selector('.take.chosen')
        assert page.locator('#cue-text').input_value() == 'A changed script.'
        assert provider.submissions == 2
        page.click('#new-project')
        page.keyboard.press('Escape')
        page.wait_for_selector('#project-dialog', state='hidden')
        print(json.dumps({'offlineBrowserFlows': 'sample, split, autosave on switch, generate, stale block, new take, select, refresh, keyboard close', 'fakeSubmissions': provider.submissions, 'pageErrors': errors}))
        browser.close()
    server.shutdown()
