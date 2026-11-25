"""Render evaluation actions with the actual Console Canvas implementation."""
import base64
import hashlib
import importlib.metadata
import os
from pathlib import Path


def studio_paths(agi_repo: Path):
    configured = os.environ.get('GRACE_CONSOLE_DIR')
    root = Path(configured).expanduser().resolve() if configured else agi_repo / 'AIVA' / 'console'
    studio = root / 'telepathic_management' / 'telepathic_console'
    html = studio / 'frontend' / 'canvas.html'
    static = studio / 'backend' / 'static'
    if not html.is_file() or not (static / 'drawing.js').is_file():
        raise RuntimeError('Console Canvas source missing; set GRACE_CONSOLE_DIR to the Console checkout')
    return html, static


def renderer_metadata(agi_repo: Path) -> dict:
    html, static = studio_paths(agi_repo)
    return {'renderer': 'console-canvas-chromium-v1',
            'drawing_js_sha256': hashlib.sha256((static / 'drawing.js').read_bytes()).hexdigest(),
            'canvas_html_sha256': hashlib.sha256(html.read_bytes()).hexdigest(),
            'playwright_version': importlib.metadata.version('playwright')}


def render_png(actions, agi_repo: Path) -> bytes:
    from playwright.sync_api import sync_playwright

    html, static = studio_paths(agi_repo)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script('window.CANVAS_EVAL_MODE = true;')

            def serve(route):
                url = route.request.url
                path = url.split('?', 1)[0].removeprefix('http://canvas.invalid')
                if path == '/canvas':
                    route.fulfill(path=str(html), content_type='text/html')
                elif path == '/api/canvas/config.js':
                    route.fulfill(body='window.CANVAS_STUDIO_CONFIG = {};', content_type='application/javascript')
                elif path.startswith('/static/'):
                    file = (static / path[len('/static/'):]).resolve()
                    if file.is_relative_to(static.resolve()) and file.is_file():
                        route.fulfill(path=str(file))
                    else:
                        route.abort()
                else:
                    route.abort()

            page.route('**/*', serve)
            page.goto('http://canvas.invalid/canvas', wait_until='load')
            if not page.evaluate('typeof window.renderCanvasEvaluation === "function"'):
                raise RuntimeError('Console checkout lacks renderCanvasEvaluation; update it to the compatible version')
            result = page.evaluate('(actions) => window.renderCanvasEvaluation(actions)', actions)
            prefix = 'data:image/png;base64,'
            if not isinstance(result, str) or not result.startswith(prefix):
                raise ValueError('Canvas did not return a PNG')
            return base64.b64decode(result[len(prefix):], validate=True)
        finally:
            browser.close()
