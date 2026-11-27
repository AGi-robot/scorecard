#!/usr/bin/env python3
"""Local model HTML coding comparison. Generated code runs only in a browser."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODELS = json.loads((HERE / 'models.json').read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def request(url, body=None, timeout=30):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def extract(text):
    text = text.strip()
    # Strip a complete reasoning block, but never modify the generated HTML itself.
    text = re.sub(r'^<think>.*?</think>\s*', '', text, flags=re.S)
    fenced = re.fullmatch(r'```(?:html)?\s*\n(.*?)\n```', text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1)
    start = re.search(r'<!doctype\s+html|<html[\s>]', text, re.I)
    if not start:
        raise ValueError('No HTML document in model response')
    return text[start.start():]


def generate(args, name, base_url, api_model):
    directory = args.output / name
    directory.mkdir(parents=True, exist_ok=True)
    prompt = (HERE / 'prompt.txt').read_text()
    provenance = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                  for path in ['AIVA/README.md', 'AIVA/docs/telepathy-flow.md', 'models/llama-router.ini']}
    body = {'model': api_model, 'messages': [{'role': 'user', 'content': prompt}],
            'temperature': args.temperature, 'top_p': 0.95, 'max_tokens': args.max_tokens,
            'stream': False, 'seed': 42}
    if args.reasoning_effort:
        body['reasoning_effort'] = args.reasoning_effort
    config = {'model': name, 'endpoint': base_url, 'request': body,
              'architecture_sha256': provenance, 'protocol': 'aiva-html-v1',
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
    existing = directory / 'manifest.json'
    if (directory / 'response.json').exists():
        old = json.loads(existing.read_text())
        if old['request'] != body or old['prompt_sha256'] != config['prompt_sha256']:
            raise ValueError(f'{name}: existing result has a different generation protocol; use a new output')
        return
    config['started_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(existing, config)
    started = time.monotonic()
    try:
        response = request(base_url.rstrip('/') + '/chat/completions', body, args.timeout)
        save(directory / 'response.json', response)
        choice = response['choices'][0]
        text = choice['message'].get('content') or ''
        (directory / 'response.txt').write_text(text)
        config.update(elapsed_s=round(time.monotonic()-started, 2),
                      finish_reason=choice.get('finish_reason'), usage=response.get('usage'),
                      completed=choice.get('finish_reason') == 'stop')
        (directory / 'index.html').write_text(extract(text))
    except Exception as exc:
        config['error'] = str(exc)
        raise
    finally:
        save(existing, config)


def check(directory):
    from playwright.sync_api import sync_playwright
    result = {'checks': {}, 'page_errors': [], 'blocked_requests': [],
              'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def record(name, passed, detail=None):
        result['checks'][name] = {'passed': bool(passed), 'detail': detail}
    def wait_state(page, expression, timeout):
        until = time.monotonic() + timeout / 1000
        while time.monotonic() < until:
            if page.evaluate(expression):
                return
            page.wait_for_timeout(50)
        raise TimeoutError(expression)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                      service_workers='block', accept_downloads=False)
        page = context.new_page()
        page.add_init_script("window.__aivaCspViolations=[]; document.addEventListener('securitypolicyviolation', e=>window.__aivaCspViolations.push({uri:e.blockedURI,directive:e.effectiveDirective}));")
        page.on('pageerror', lambda exc: result['page_errors'].append(str(exc)))
        def serve(route):
            if route.request.url == 'http://aiva-eval.invalid/':
                route.fulfill(path=str(directory / 'index.html'), content_type='text/html',
                              headers={'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"})
            else:
                result['blocked_requests'].append(route.request.url)
                route.abort()
        context.route('**/*', serve)
        try:
            page.goto('http://aiva-eval.invalid/', wait_until='load', timeout=15000)
            page.wait_for_timeout(500)
            record('nonempty_page', len(page.locator('body').inner_text().strip()) > 100)
            initial = page.evaluate('window.AIVA_DEMO?.getState?.() ?? null')
            record('initial_state', isinstance(initial,dict) and initial.get('step') == 0 and initial.get('playing') is False, initial)
            controls = all(page.locator('button#'+key).count() == 1 and
                           page.locator('button#'+key).is_visible() for key in ('next','reset','play'))
            record('visible_controls', controls)
            def control(key, method):
                button = page.locator('button#'+key)
                if button.count() == 1 and button.is_visible():
                    button.click(timeout=2000)
                else:
                    page.evaluate('window.AIVA_DEMO.'+method+'()')
            def step_label():
                label=page.locator('#step-label')
                return label.inner_text() if label.count() == 1 else ''
            if isinstance(initial,dict):
                labels = [step_label()]
                steps = [initial['step']]
                for _ in range(6):
                    control('next','next')
                    page.wait_for_timeout(80)
                    steps.append(page.evaluate('window.AIVA_DEMO.getState().step'))
                    labels.append(step_label())
                record('seven_steps', steps == list(range(7)), steps)
                record('changing_step_labels', len(set(labels)) == 7 and all(x.strip() for x in labels), labels)
                page.evaluate('window.AIVA_DEMO.next()')
                record('clamps_at_end', page.evaluate('window.AIVA_DEMO.getState().step') == 6)
                control('reset','reset')
                record('reset', page.evaluate('window.AIVA_DEMO.getState().step === 0 && window.AIVA_DEMO.getState().playing === false'))
                control('play','togglePlay')
                record('play', page.evaluate('window.AIVA_DEMO.getState().playing') is True)
                control('play','togglePlay')
                record('pause', page.evaluate('window.AIVA_DEMO.getState().playing') is False)
                page.evaluate('window.AIVA_DEMO.reset(); window.AIVA_DEMO.togglePlay()')
                try:
                    wait_state(page, 'window.AIVA_DEMO.getState().step > 0', timeout=6000)
                    record('autoplay_advances', True)
                except Exception:
                    record('autoplay_advances', False)
                page.evaluate('window.AIVA_DEMO.reset()')
                page.wait_for_timeout(1500)
                record('reset_stops_playback', page.evaluate('window.AIVA_DEMO.getState().step === 0 && window.AIVA_DEMO.getState().playing === false'))
                page.evaluate('for(let i=0;i<5;i++) window.AIVA_DEMO.next(); window.AIVA_DEMO.togglePlay()')
                try:
                    wait_state(page, 'window.AIVA_DEMO.getState().step === 6 && !window.AIVA_DEMO.getState().playing', timeout=10000)
                    record('autoplay_stops_at_end', True)
                except Exception:
                    record('autoplay_stops_at_end', False)
                page.evaluate('window.AIVA_DEMO.reset(); window.AIVA_DEMO.next(); window.AIVA_DEMO.next(); window.AIVA_DEMO.next()')
        except Exception as exc:
            result['test_error'] = str(exc)
        finally:
            # Preserve visual evidence even when a model's interaction code throws.
            try:
                page.screenshot(path=str(directory / 'desktop.png'), full_page=True, timeout=10000)
                page.set_viewport_size({'width':390, 'height':844})
                page.wait_for_timeout(100)
                record('mobile_no_horizontal_overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                record('mobile_controls', all(page.locator('button#'+k).count() == 1 and page.locator('button#'+k).is_visible()
                                              for k in ('next','reset','play')))
                page.screenshot(path=str(directory / 'mobile.png'), full_page=True, timeout=10000)
            except Exception as exc:
                result['screenshot_error'] = str(exc)
            record('no_javascript_errors', not result['page_errors'] and 'Page.evaluate:' not in result.get('test_error',''), result['page_errors'])
            try:
                result['csp_violations'] = page.evaluate('window.__aivaCspViolations || []')
            except Exception:
                result['csp_violations'] = []
            external_violations = [v for v in result['csp_violations'] if v.get('uri','').startswith(('http:','https:','ws:','wss:'))]
            record('no_external_requests', not result['blocked_requests'] and not external_violations, result['blocked_requests'] + external_violations)
            browser.close()
    required = ['nonempty_page','initial_state','visible_controls','seven_steps','changing_step_labels',
                'clamps_at_end','reset','play','pause','autoplay_advances','reset_stops_playback','autoplay_stops_at_end','mobile_no_horizontal_overflow','mobile_controls',
                'no_javascript_errors','no_external_requests']
    result['passed'] = sum(result['checks'].get(k, {}).get('passed', False) for k in required)
    result['total'] = len(required)
    result['note'] = 'Mechanical checks only: not an architecture-fidelity, aesthetic, or agentic benchmark score.'
    save(directory / 'checks.json', result)
    return result


def gallery(output):
    rows = []
    summary = []
    for directory in sorted(output.iterdir()):
        if not directory.is_dir() or not ((directory / 'manifest.json').exists() or (directory / 'failure.json').exists()):
            continue
        manifest = json.loads((directory / 'manifest.json').read_text()) if (directory / 'manifest.json').exists() else {}
        if (directory / 'failure.json').exists():
            manifest['error'] = json.loads((directory / 'failure.json').read_text())['error']
        checks = json.loads((directory / 'checks.json').read_text()) if (directory / 'checks.json').exists() else {}
        name = html.escape(directory.name)
        status = f"{checks.get('passed',0)}/{checks.get('total',16)} checks; finish={manifest.get('finish_reason','pending')}"
        rows.append(f'<article><h2>{name}</h2><p>{html.escape(status)}</p><p>{html.escape(manifest.get("error", ""))}</p>'
                    f'<a href="{name}/index.html" target="_blank" rel="noopener">Open generated page</a> · '
                    f'<a href="{name}/checks.json">Checks</a><a href="{name}/desktop.png"><img src="{name}/desktop.png" alt="{name} desktop screenshot"></a>'
                    f'<iframe sandbox="allow-scripts" loading="lazy" src="{name}/index.html" title="{name} interactive preview" referrerpolicy="no-referrer"></iframe></article>')
        summary.append({'model': directory.name, 'checks': checks.get('passed'), 'total':checks.get('total'),
                        'finish_reason':manifest.get('finish_reason'), 'elapsed_s':manifest.get('elapsed_s'), 'error':manifest.get('error'), 'runtime_error':checks.get('test_error')})
    (output / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>AIVA cartoon coding comparison</title><style>body{font:16px system-ui;background:#eef2fa;color:#17213b;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:24px}article{background:white;padding:20px;border-radius:20px}img{width:100%;margin-top:16px}iframe{width:100%;height:650px;border:1px solid #cdd5e6;margin-top:16px}a{color:#244cad}</style>'
        '<h1>AIVA cartoon coding comparison</h1><p>Same prompt, one generated HTML per model. Checks measure functionality, not visual quality. Review factual accuracy, readability, cartoon style, and animation separately. Live previews are sandboxed.</p><main>' + ''.join(rows) + '</main></html>')
    save(output / 'summary.json', summary)
    subprocess.run([sys.executable, str(HERE/'comparison_report.py'), str(output.parent)], check=True)


def busy_evaluation():
    # Do not start competing model processes while long-running evaluations own the GPU.
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            parts = (process / 'cmdline').read_bytes().split(b'\0')
            if parts and b'python' in parts[0] and any(part.endswith((b'/ifeval_run.py', b'/ifbench_baseline.py', b'/ifbench_run.py', b'/evalplus/generate.py')) for part in parts):
                # Remote endpoints do not occupy the local GPU.
                urls = [part.decode(errors='replace') for part in parts if part.startswith((b'http://',b'https://'))]
                if not urls or any('127.0.0.1' in url or 'localhost' in url for url in urls):
                    return True
        except (OSError, PermissionError):
            pass
    return False


def run_owned(args, name):
    model = MODELS[name]
    directory = args.output / name
    if (directory / 'response.json').exists():
        return
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / 'server.log'
    command = [str(args.llama_server), '--model', str(args.models_root / model['file']),
               '--alias', name, '--host','127.0.0.1','--port',str(args.port), '--ctx-size',str(args.context),
               '--n-gpu-layers','auto','--flash-attn','on','--jinja','--parallel','1',
               '--cache-type-k','q4_0','--cache-type-v','q4_0','--reasoning-budget',str(args.reasoning_budget)]
    if args.reasoning_effort:
        command += ['--reasoning-effort',args.reasoning_effort]
    if model.get('template'):
        command += ['--chat-template-file', str(ROOT / 'models/templates/mistral-v7-tekken.jinja')]
    base = f'http://127.0.0.1:{args.port}'
    # Never attach to or terminate an existing process on our requested port.
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',args.port)) == 0:
            raise RuntimeError(f'Port {args.port} already occupied; choose a free --port')
    save(directory / 'server-command.json', command)
    weights = args.models_root / model['file']
    stat = weights.stat()
    save(directory / 'model-file.json', {'path': str(weights), 'size_bytes': stat.st_size,
                                        'mtime_ns': stat.st_mtime_ns,
                                        'backend_version': subprocess.check_output([str(args.llama_server),'--version'], stderr=subprocess.STDOUT, text=True).strip()})
    with log_path.open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            until = time.monotonic()+args.startup_timeout
            while time.monotonic() < until:
                if child.poll() is not None:
                    raise RuntimeError(f'{name}: server exited; see {log_path}')
                try:
                    if request(base+'/health',timeout=2).get('status') == 'ok':
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError(f'{name}: server startup timed out')
            caps = request(base+'/props', timeout=10).get('chat_template_caps', {})
            save(directory/'template-capabilities.json',caps)
            if args.reasoning_effort and not caps.get('supports_reasoning_effort'):
                print(f'{name}: template reports no reasoning-effort support; requested {args.reasoning_effort} may be ignored',flush=True)
            try:
                generate(args,name,base+'/v1',name)
            finally:
                manifest_path=directory/'manifest.json'
                if manifest_path.exists():
                    metadata=json.loads(manifest_path.read_text())
                    metadata['reasoning_effort_supported']=caps.get('supports_reasoning_effort',False)
                    metadata['reasoning_effort_levels']=caps.get('reasoning_effort_levels',[])
                    save(manifest_path,metadata)
        finally:
            child.terminate()
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def limited_models(source, names):
    return [name for name in names
            if (source/name/'manifest.json').is_file()
            and json.loads((source/name/'manifest.json').read_text()).get('finish_reason') == 'length']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['generate','check','sweep','retry-limited'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--contestant',action='append',default=[],help='label=http://host:port/v1/model-alias')
    p.add_argument('--models',nargs='+',choices=list(MODELS),default=list(MODELS))
    p.add_argument('--source',type=Path,help='Original output directory for retry-limited')
    p.add_argument('--reasoning-effort',choices=['minimal','low','medium','high','xhigh','max'])
    p.add_argument('--reasoning-budget',type=int,default=512)
    p.add_argument('--temperature',type=float,default=0.7)
    p.add_argument('--max-tokens',type=int,default=6144)
    p.add_argument('--timeout',type=int,default=1200)
    p.add_argument('--context',type=int,default=16384)
    p.add_argument('--startup-timeout',type=int,default=600)
    p.add_argument('--port',type=int,default=8096)
    p.add_argument('--llama-server',type=Path,default=Path.home()/'llama.cpp/build/bin/llama-server')
    p.add_argument('--models-root',type=Path,default=Path('/opt/agi/models'))
    p.add_argument('--wait-for-idle',action='store_true')
    args=p.parse_args()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    errors=[]
    if args.stage == 'retry-limited':
        if not args.source:
            p.error('retry-limited requires --source')
        if args.source.resolve() == args.output:
            p.error('retry output must be separate from the original run')
        while True:
            running = False
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit() or int(proc.name) == os.getpid():
                    continue
                try:
                    argv = (proc/'cmdline').read_bytes().split(b'\0')
                    if argv and b'python' in argv[0] and b'sweep' in argv and any(x.endswith(b'/aiva_html_eval.py') for x in argv):
                        running = True
                except OSError:
                    pass
            if not running:
                break
            if not args.wait_for_idle:
                p.error('Original sweep is still running; use --wait-for-idle')
            print('Waiting for the original model sweep...',flush=True)
            time.sleep(30)
        args.models = limited_models(args.source, args.models)
        save(args.output/'retry-plan.json', {'source':str(args.source.resolve()), 'models':args.models,
                                            'reasoning_effort':args.reasoning_effort,
                                            'reasoning_budget':args.reasoning_budget, 'max_tokens':args.max_tokens})
        print('Retrying truncated models: '+', '.join(args.models),flush=True)
        args.stage = 'sweep'
    if args.stage == 'generate':
        if not args.contestant:
            p.error('generate needs at least one --contestant')
        for spec in args.contestant:
            name,endpoint=spec.split('=',1)
            if not re.fullmatch(r'[a-zA-Z0-9_-]+',name):
                p.error('contestant labels must contain only letters, digits, hyphens, underscores')
            base,api_model=endpoint.rsplit('/',1)
            try:
                print(f'Generating {name}',flush=True)
                generate(args,name,base,api_model)
            except Exception as exc:
                errors.append(f'{name}: {exc}')
            if (args.output/name/'index.html').exists():
                check(args.output/name)
            gallery(args.output)
    elif args.stage == 'sweep':
        for name in args.models:
            if not (args.output/name/'response.json').exists():
                while busy_evaluation():
                    if not args.wait_for_idle:
                        raise SystemExit('Another evaluation is running; use --wait-for-idle to queue without interrupting it.')
                    print('Waiting for other evaluations to finish...',flush=True)
                    time.sleep(30)
                try:
                    print(f'Generating {name}',flush=True)
                    run_owned(args,name)
                except Exception as exc:
                    errors.append(f'{name}: {exc}')
                    save(args.output/name/'failure.json',{'error':str(exc)})
            if (args.output/name/'index.html').exists():
                check(args.output/name)
            gallery(args.output)
    else:
        for directory in sorted(args.output.iterdir()):
            if directory.is_dir() and (directory/'index.html').exists():
                print(directory.name,check(directory),flush=True)
        gallery(args.output)
    print(f'Gallery: {args.output / "index.html"}',flush=True)
    if errors:
        print('\n'.join(errors),flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
