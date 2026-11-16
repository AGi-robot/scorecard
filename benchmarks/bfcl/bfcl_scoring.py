"""Simplified AST checker following official BFCL semantics.

Official checker: berkeley-function-call-leaderboard/bfcl_eval/eval_checker/
ast_eval/ast_checker.py (Apache-2.0, vendored intent). This is a dependency-free
reimplementation for the Python single-turn categories:

- simple: exactly 1 call; function name must match; every provided argument
  value must be in the ground truth's allowed list for that argument.
  Ground truth values are lists of acceptable values per argument.
- multiple: same as simple, but the model must also pick the right function
  among several (handled identically — name must match).
- parallel / parallel_multiple: set of calls must match one of the allowed
  ground-truth options, order-insensitive. Each call checked like simple.
- irrelevance: handled by the runner (no calls expected).

Value comparison is type-lenient (e.g. 10 == 10.0, "true" accepted for
booleans in string form) mirroring the official type_convertor behaviour for
the common cases. Nested structures are compared via normalized JSON.
"""
import json


def _norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        low = s.lower()
        if low in ("true",):
            return True
        if low in ("false",):
            return False
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            return s
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def _val_ok(pred, allowed):
    pn = _norm(pred)
    for a in allowed:
        if _norm(a) == pn:
            return True
        # numeric tolerance
        try:
            if abs(float(pn) - float(_norm(a))) < 1e-6:
                return True
        except Exception:
            pass
    return False


def _call_ok(pred_call, gt_call):
    # each is {func_name: {arg: value}} ; gt values are lists of allowed
    if set(pred_call.keys()) != set(gt_call.keys()):
        return False
    for fname, gt_args in gt_call.items():
        pred_args = pred_call.get(fname, {})
        if not isinstance(pred_args, dict):
            return False
        # required args present: every gt arg with non-empty allowed list
        for arg, allowed in gt_args.items():
            if not allowed:
                continue
            if arg not in pred_args:
                # "" in the allowed list means the argument may be omitted
                if "" in allowed:
                    continue
                return False
            if not _val_ok(pred_args[arg], [a for a in allowed if a != ""] or allowed):
                return False
    return True


def _key(call):
    return json.dumps(call, sort_keys=True, default=str)


def score_entry(cat, pred_calls, ground_truth):
    """pred_calls: [{func: args}], ground_truth: list of options, each a list
    of {func: {arg: [allowed...]}}."""
    if not ground_truth:
        return len(pred_calls) == 0
    if cat in ("simple", "multiple"):
        if len(pred_calls) != 1:
            return False
        return any(_call_ok(pred_calls[0], opt[0])
                   for opt in ground_truth if len(opt) == 1)
    if cat in ("parallel", "parallel_multiple"):
        pred_set = sorted(_key(c) for c in pred_calls)
        for opt in ground_truth:
            if len(opt) != len(pred_calls):
                continue
            # order-insensitive: every gt call must have a matching pred call
            used = [False] * len(pred_calls)
            ok = True
            for g in opt:
                found = False
                for i, p in enumerate(pred_calls):
                    if not used[i] and _call_ok(p, g):
                        used[i] = True
                        found = True
                        break
                if not found:
                    ok = False
                    break
            if ok:
                return True
        return False
    return False


def self_test():
    # 1. ground truth as prediction -> must pass
    gt = [{"calculate_triangle_area": {"base": [10], "height": [5], "unit": ["units", ""]}}]
    assert score_entry("simple", [{"calculate_triangle_area": {"base": 10, "height": 5}}], [gt])
    # 2. empty -> must fail
    assert not score_entry("simple", [], [gt])
    # 3. wrong name -> must fail
    assert not score_entry("simple", [{"wrong_fn": {"base": 10}}], [gt])
    # 4. wrong value -> must fail
    assert not score_entry("simple", [{"calculate_triangle_area": {"base": 99, "height": 5}}], [gt])
    # 5. parallel order-insensitive
    gt2 = [[{"f_a": {"x": [1]}}, {"f_b": {"y": [2]}}]]
    assert score_entry("parallel", [{"f_b": {"y": 2}}, {"f_a": {"x": 1}}], gt2)
    assert not score_entry("parallel", [{"f_a": {"x": 1}}], gt2)
    # 6. irrelevance
    assert score_entry("simple", [], []) is True
    print("self-test: all 6 checks passed")


if __name__ == "__main__":
    self_test()
