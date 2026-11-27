"""Offline checks for launcher side effects and authenticated model requests."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_modal_bench as launcher  # noqa: E402


def test_dry_run_needs_neither_key_nor_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('AIVA_LLM_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['run_modal_bench.py', '--model', 'ministral', '--bench', 'ifeval', '--dry-run'])
    with patch.object(launcher, 'preflight') as preflight, patch.object(launcher, 'check_key') as check:
        launcher.main()
    preflight.assert_not_called()
    check.assert_not_called()


def test_chatbot_eval_forwards_configured_api_key(monkeypatch):
    path = ROOT / 'benchmarks/aiva_chatbot_eval/preference_bench.py'
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('preference_auth_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-token')
    payload = {'choices': [{'message': {'content': 'Hello'}}]}
    with patch.object(module.urllib.request, 'urlopen') as open_url:
        open_url.return_value.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
        assert module.chat('https://endpoint.invalid/v1', 'test', []) == payload
    request = open_url.call_args.args[0]
    assert request.get_header('Authorization') == 'Bearer test-token'
