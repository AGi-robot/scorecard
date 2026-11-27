"""Harness validation fixtures, never model benchmark results."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('html_eval', Path(__file__).with_name('aiva_html_eval.py'))
evalmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evalmod)

FIXTURE = '''<!doctype html><html><meta name="viewport" content="width=device-width, initial-scale=1"><body>
<h1>Harness validation fixture: not a benchmark result</h1>
<p>This deliberately plain document exercises the browser's interaction checks and error detection. It is not a model-generated visualization.</p>
<div id="step-label">Stage 0</div><button id="next">Next</button><button id="reset">Reset</button><button id="play">Play</button>
<script>
let step=0,playing=false,timer;function render(){document.querySelector('#step-label').textContent='Stage '+step;}
window.AIVA_DEMO={getState:()=>({step,playing}),reset:()=>{clearInterval(timer);step=0;playing=false;render()},next:()=>{step=Math.min(6,step+1);render()},togglePlay:()=>{playing=!playing;clearInterval(timer);if(playing)timer=setInterval(()=>{AIVA_DEMO.next();if(step===6){playing=false;clearInterval(timer)}},200)}};
for(const [id,method] of [['next','next'],['reset','reset'],['play','togglePlay']]) document.getElementById(id).onclick=()=>AIVA_DEMO[method]();
</script></body></html>'''


class HarnessTests(unittest.TestCase):
    def test_fenced_and_reasoned_response(self):
        text='<think>planning</think>\n```html\n<!doctype html><html>ok</html>\n```'
        self.assertEqual(evalmod.extract(text),'<!doctype html><html>ok</html>')

    def test_retry_selects_only_truncated_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            evalmod.save(root/'truncated'/'manifest.json',{'finish_reason':'length'})
            evalmod.save(root/'complete'/'manifest.json',{'finish_reason':'stop'})
            self.assertEqual(evalmod.limited_models(root,['truncated','complete','missing']),['truncated'])

    def test_medium_effort_reaches_api_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            args=SimpleNamespace(output=Path(temp),temperature=0.7,max_tokens=6144,
                                 reasoning_effort='medium',timeout=2)
            response={'choices':[{'finish_reason':'stop','message':{'content':'<!doctype html><html>fixture</html>'}}]}
            with patch.object(evalmod,'request',return_value=response) as api:
                evalmod.generate(args,'fixture','http://127.0.0.1:9999/v1','test-model')
            body=api.call_args.args[1]
            self.assertEqual(body['reasoning_effort'],'medium')
            self.assertEqual(body['max_tokens'],6144)
            self.assertTrue((Path(temp)/'fixture'/'index.html').is_file())

    def test_non_html_rejected(self):
        with self.assertRaises(ValueError):
            evalmod.extract('I cannot write this page.')

    def test_browser_detects_broken_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'index.html').write_text(FIXTURE)
            valid=evalmod.check(directory)
            self.assertEqual(valid['passed'],valid['total'],valid)
            (directory/'index.html').write_text(FIXTURE.replace("step=Math.min(6,step+1)","step=0"))
            broken=evalmod.check(directory)
            self.assertFalse(broken['checks']['seven_steps']['passed'])
            self.assertLess(broken['passed'],broken['total'])

    def test_external_asset_dependency_is_detected_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'index.html').write_text(FIXTURE.replace('<h1>', '<img src="https://assets.invalid/fixture.png"><h1>'))
            result=evalmod.check(directory)
            self.assertFalse(result['checks']['no_external_requests']['passed'])

    def test_api_is_checked_when_control_ids_differ(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            fixture=FIXTURE.replace('id="next"','id="custom-next"').replace("['next','next']", "['custom-next','next']")
            fixture=fixture.replace('getState:()=>({step,playing})','getState:()=>({step,playing,extra:"allowed"})')
            (directory/'index.html').write_text(fixture)
            result=evalmod.check(directory)
            self.assertFalse(result['checks']['visible_controls']['passed'])
            self.assertTrue(result['checks']['initial_state']['passed'])
            self.assertTrue(result['checks']['seven_steps']['passed'])
            self.assertTrue(result['checks']['autoplay_advances']['passed'])

    def test_browser_records_javascript_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'index.html').write_text(FIXTURE.replace('</script>',"throw new Error('fixture-error');</script>"))
            broken=evalmod.check(directory)
            self.assertFalse(broken['checks']['no_javascript_errors']['passed'])
            self.assertIn('fixture-error',str(broken['page_errors']))


if __name__=='__main__':
    unittest.main()
