"""Build a combined static report from saved runs; no inference required."""
import html
import json
from pathlib import Path
import sys


def build_report(root):
    runs = {p.name: p for p in sorted(root.iterdir()) if p.is_dir() and (p/'summary.json').exists()}
    names = sorted({p.name for run in runs.values() for p in run.iterdir()
                    if p.is_dir() and ((p/'manifest.json').exists() or (p/'failure.json').exists())})
    rows = []
    for name in names:
        cells = []
        for run, directory in runs.items():
            path = directory/name
            if not (path/'manifest.json').exists():
                error = json.loads((path/'failure.json').read_text()).get('error','Failed') if (path/'failure.json').exists() else 'Not run'
                cells.append('<td>'+html.escape(error)+'</td>')
                continue
            manifest = json.loads((path/'manifest.json').read_text())
            checks = json.loads((path/'checks.json').read_text()) if (path/'checks.json').exists() else {}
            request = manifest.get('request',{})
            prefix = html.escape(run+'/'+name)
            status = html.escape(str(manifest.get('finish_reason','pending')))
            support = html.escape(str(manifest.get('reasoning_effort_supported','not recorded')))
            cells.append(f'<td><strong>{checks.get("passed",0)}/{checks.get("total",16)} checks</strong> · {status}<br>'
                         f'<a href="{prefix}/index.html">Open page</a> · <a href="{prefix}/desktop.png">Screenshot</a> · <a href="{prefix}/checks.json">Checks</a><br>'
                         f'<small>Output limit: {request.get("max_tokens","?")}; effort: {html.escape(str(request.get("reasoning_effort","default")))}; template support: {support}</small></td>')
        rows.append('<tr><th scope="row">'+html.escape(name)+'</th>'+''.join(cells)+'</tr>')
    columns = ''.join('<th>'+html.escape(run)+'</th>' for run in runs)
    links = ' · '.join(f'<a href="{html.escape(run)}/index.html">{html.escape(run)} visual gallery</a>' for run in runs)
    (root/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>AIVA HTML model comparison</title><style>body{font:16px system-ui;margin:32px;background:#f1f5fb;color:#152445}table{border-collapse:collapse;width:100%;background:white}td,th{padding:18px;text-align:left;border-bottom:1px solid #d4ddec}a{color:#2452ba}small{color:#52617b}main{overflow:auto}p{max-width:1000px;line-height:1.6}</style>'
        '<h1>AIVA cartoon HTML comparison</h1><p>Same architecture prompt, one generated page per model and configuration. Mechanical browser checks are not visual-quality scores. Inspect the actual pages and screenshots. The retry changes both requested effort and output allowance; templates without effort support may ignore that setting.</p><p>'+links+'</p><main><table><thead><tr><th>Model</th>'+columns+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></main></html>')


if __name__ == '__main__':
    build_report(Path(sys.argv[1]).resolve())
