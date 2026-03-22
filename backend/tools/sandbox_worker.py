"""
Runs in a child process (see python_sandbox.py). Restricted builtins + import whitelist.
Not a cryptographic sandbox; intended for model-generated snippets with timeout isolation.
"""
from __future__ import annotations

import builtins as b
import contextlib
import io
import json
import sys
import traceback

ALLOWED_MODULES = frozenset(
    {
        "math",
        "json",
        "itertools",
        "functools",
        "collections",
        "statistics",
        "datetime",
        "decimal",
        "fractions",
        "string",
        "random",
        "re",
        "operator",
        "copy",
    }
)

SAFE_BUILTINS: dict = {
    "abs": abs,
    "all": all,
    "any": any,
    "ascii": ascii,
    "bin": bin,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ArithmeticError": ArithmeticError,
    "AssertionError": AssertionError,
    "BufferError": BufferError,
    "EOFError": EOFError,
    "FloatingPointError": FloatingPointError,
    "ImportError": ImportError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "LookupError": LookupError,
    "MemoryError": MemoryError,
    "NameError": NameError,
    "NotImplementedError": NotImplementedError,
    "OSError": OSError,
    "OverflowError": OverflowError,
    "RecursionError": RecursionError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "SyntaxError": SyntaxError,
    "SystemError": SystemError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".", 1)[0]
    if root not in ALLOWED_MODULES:
        raise ImportError(f"module {name!r} is not allowed in the sandbox")
    return b.__import__(name, globals, locals, fromlist, level)


SAFE_GLOBALS = {**SAFE_BUILTINS, "__import__": _safe_import}


def _run(code: str) -> dict:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    g: dict = {"__builtins__": SAFE_GLOBALS}
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(compile(code, "<sandbox>", "exec"), g, g)
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
        }
    return {
        "ok": True,
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
    }


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        code = payload.get("code", "")
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"invalid worker input: {e}"}))
        return
    if not isinstance(code, str):
        print(json.dumps({"ok": False, "error": "code must be a string"}))
        return
    out = _run(code)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
