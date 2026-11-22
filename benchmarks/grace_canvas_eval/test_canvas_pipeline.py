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


@pytest.mark.parametrize('color,expected', [
    ('#c0392b', True), ('#cc2244', True), ('#228844', False), ('#888888', False)])
def test_red_hue_band_wraps_through_zero(color, expected):
    assert eval.T.has_hue([color], 340, 20) is expected


@pytest.mark.parametrize('image_fallback', [False, True])
@pytest.mark.parametrize('use_tools', [False, True])
def test_request_preserves_controls(monkeypatch, image_fallback, use_tools):
    requests = []
    def request(base_url, body, timeout):
        requests.append(body)
        if image_fallback and len(requests) == 1:
            raise urllib.error.HTTPError(base_url, 500, 'image not supported', {}, None)
        return {'choices': [{'message': {'tool_calls': [{'function': {
            'arguments': json.dumps({'actions': [], 'response': 'done'})}}]}}]}
    monkeypatch.setattr(eval, 'urllib_request', request)
    _, meta = eval.draw_actions('http://example.invalid', 'model', 'system', 'brief',
                      images=['fake'] if image_fallback else None,
                      force_tool=use_tools, use_tools=use_tools, reasoning_effort='low')
    assert meta['vision_fallback'] == image_fallback
    assert len(requests) == (2 if image_fallback else 1)
    for body in requests:
        assert body['reasoning_effort'] == 'low'
        if use_tools:
            assert body['tool_choice']['function']['name'] == 'canvas_draw'
        else:
            assert body['response_format']['type'] == 'json_schema'
            schema = body['response_format']['json_schema']['schema']
            assert schema == eval.engine.build_draw_schema(16)
    assert requests[-1]['messages'][1]['content'][0]['type'] == 'text'


def test_schema_hint_keeps_lines_and_triangles():
    variants = eval.build_tool(True)['function']['parameters']['properties']['actions']['items']['anyOf']
    points = next(v for v in variants if v['properties']['kind']['enum'] == ['line'])['properties']['points']
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
        return actions, {'truncated': False, 'elapsed_s': 0, 'more': len(calls) == 1}
    monkeypatch.setattr(eval, 'draw_actions', draw)
    args = SimpleNamespace(base_url='unused', model='unused', schema_hint=False,
                           temperature=0, think_off=True, force_tool=True,
                           reasoning_effort=None, judge_base_url=None, out_dir=str(tmp_path))
    task = {'id': 'offline-review', 'tier': 5, 'brief': 'Paint a leaf',
            'seed_actions': [seed], 'checks': [lambda scene: (len(scene['objects']) == 2, 'kept objects')]}
    result = eval.run_task(task, args)
    assert result['passes'][1]['rendered'] and result['score'] == 1
    assert 'leaf' in calls[1][3] and 'background' in calls[1][3]
    final = [seed] + json.loads((tmp_path / 'offline-review.actions.json').read_text())
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


def test_default_vision_reviews_even_when_first_pass_says_done(monkeypatch):
    calls = []
    def draw(*args, **kwargs):
        calls.append(kwargs)
        return [{'kind': 'ellipse', 'id': 'apple', 'x': 100, 'y': 100,
                 'width': 200, 'height': 200, 'fill': True, 'fill_color': '#cc2222'}], {
                     'truncated': False, 'elapsed_s': 0, 'more': False}
    monkeypatch.setattr(eval, 'draw_actions', draw)
    args = SimpleNamespace(base_url='unused', model='unused', schema_hint=False,
                           temperature=0, think_off=False, force_tool=False,
                           reasoning_effort='medium', judge_base_url=None, out_dir=None)
    result = eval.run_task({'id': 'review', 'tier': 1, 'brief': 'Draw an apple', 'checks': []}, args)
    assert len(calls) == 2
    assert all(call['images'] and call['strict_geometry'] for call in calls)
    assert all(p['with_image'] for p in result['passes'])
