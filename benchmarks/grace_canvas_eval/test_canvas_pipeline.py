"""Offline pipeline checks; no model scores are produced."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest
from PIL import Image

# AGI_REPO points to the checkout containing capability/canvas/src; imaging is optional.
spec = importlib.util.spec_from_file_location(
    'canvas_eval_pipeline', Path(__file__).with_name('grace_canvas_eval.py'))
eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval)


@pytest.mark.parametrize('image_fallback', [False, True])
def test_request_preserves_controls(monkeypatch, image_fallback):
    requests = []
    def request(base_url, body, timeout):
        requests.append(body)
        if image_fallback and len(requests) == 1:
            raise urllib.error.HTTPError(base_url, 500, 'image not supported', {}, None)
        return {'choices': [{'message': {'tool_calls': [{'function': {
            'arguments': json.dumps({'actions': [], 'response': 'done'})}}]}}]}
    monkeypatch.setattr(eval, 'urllib_request', request)
    eval.draw_actions('http://example.invalid', 'model', 'system', 'brief',
                      images=['fake'] if image_fallback else None,
                      force_tool=True, reasoning_effort='low')
    assert len(requests) == (2 if image_fallback else 1)
    for body in requests:
        assert body['reasoning_effort'] == 'low'
        assert body['tool_choice']['function']['name'] == 'canvas_draw'
    assert requests[-1]['messages'][1]['content'][0]['type'] == 'text'


def test_schema_hint_keeps_lines_and_triangles():
    points = eval.build_tool(True)['function']['parameters']['properties']['actions']['items']['properties']['points']
    assert points.get('minItems', 0) <= 2


def test_review_keeps_draft_and_seed_and_renders_color(monkeypatch, tmp_path):
    seed = {'kind': 'rectangle', 'id': 'background', 'x': 0, 'y': 0,
            'width': 1000, 'height': 650, 'fill': True, 'fill_color': '#ffffff', 'stroke': False}
    draft = {'kind': 'polygon', 'id': 'leaf', 'points': [[100, 100], [400, 100], [100, 400]],
             'stroke': False, 'fill_color': '#cc2222'}
    calls = []
    def draw(*args, **kwargs):
        calls.append(args)
        actions = [draft] if len(calls) == 1 else [{'kind': 'style', 'id': 'leaf', 'fill_color': '#22cc22'}]
        return actions, {'truncated': False, 'elapsed_s': 0}
    monkeypatch.setattr(eval, 'draw_actions', draw)
    args = SimpleNamespace(base_url='unused', model='unused', schema_hint=False,
                           temperature=0, think_off=True, force_tool=True,
                           reasoning_effort=None, judge_base_url=None, out_dir=str(tmp_path))
    task = {'id': 'offline-review', 'tier': 5, 'brief': 'Paint a leaf',
            'seed_actions': [seed], 'checks': [lambda scene: (len(scene['objects']) == 2, 'kept objects')]}
    result = eval.run_task(task, args)
    assert result['pass2']['rendered'] and result['pass2']['score'] == 1
    assert 'leaf' in calls[1][3] and 'background' in calls[1][3]
    final = json.loads((tmp_path / 'offline-review.final.actions.json').read_text())
    png, error = eval.render_png(final)
    assert error is None
    r, g, b = Image.open(io.BytesIO(png)).convert('RGB').getpixel((150, 150))
    assert g > 150 and r < 100 and b < 100


def test_scene_and_render_share_missing_color_fallback():
    actions = [{'kind': 'ellipse', 'x': 100, 'y': 100, 'width': 200, 'height': 200,
                'fill': True, 'stroke': False}]
    scene = eval.build_scene(actions)
    assert scene['objects'][0]['fill_color'] == '#e8a87c'
    png, error = eval.render_png(actions)
    assert error is None and png.startswith(b'\x89PNG')
