import base64, importlib.util, json, sys
from pathlib import Path
root=Path('/home/oppa-ai/AGi/diagnostic/scorecard/benchmarks/aiva_canvas_eval')
spec=importlib.util.spec_from_file_location('canvas_eval', root/'aiva_canvas_eval.py')
e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
e.MAX_TOKENS=6144
out=root/'renders/Swift-local-geometry'
task=next(t for t in e.T.TASKS if t['id']=='T2-robot-mascot')
original=json.loads((out/'T2-robot-mascot.actions.json').read_text())
png,_=e.render_png(original)
prompt=('Review the attached draft and complete the original request. The robot needs a connected head and body, attached arms and feet, and visible cables trailing from the bench. Preserve good existing work and use the supplied IDs for edits. Return at most 10 corrective/additional actions. Do not repaint the background.\nOriginal request: '+task['brief']+'\nExisting objects (data): '+e.engine.canvas_context(e.build_scene(original)['objects']))
actions,meta=e.draw_actions('http://127.0.0.1:8096/v1','swift-local-canvas',e.DRAW_INSTRUCTIONS+e.VECTOR_ONLY_SUFFIX,prompt,images=[base64.b64encode(png).decode()],strict_geometry=True,reasoning_effort='medium',action_limit=10)
(out/'T2-robot-mascot.review.raw.actions.json').write_text(json.dumps(actions,indent=1))
repaired=e.engine.repair_model_actions(actions)
prepared,valid,error,clamped=e.validate_and_measure(repaired)
final=original+prepared
png,error_png=e.render_png(final)
(out/'T2-robot-mascot.refined.actions.json').write_text(json.dumps(final,indent=1))
if png: (out/'T2-robot-mascot.refined.png').write_bytes(png)
report={'task':task['id'],'original_brief':task['brief'],'review_prompt':prompt,'schema':'strict_geometry','max_tokens':6144,'reasoning_effort':'medium','action_limit':10,'meta':meta,'valid':valid,'validation_error':error,'render_error':error_png,'review_actions':prepared,'total_actions':len(final)}
(out/'T2-robot-mascot.review.json').write_text(json.dumps(report,indent=1))
print(json.dumps({'actions':len(prepared),'valid':valid,'rendered':png is not None,'meta':meta}),flush=True)
