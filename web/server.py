#!/usr/bin/env python3
"""Serveur local de l'interface VMPGC : python3 web/server.py  ->  http://localhost:8000
Compile avec le vrai compilateur, exécute avec la vraie VM (vm/gcvm), renvoie aussi le
programme en JSON pour le visualisateur (web/gcsim.js)."""
import json, os, subprocess, sys, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from compiler.frontend.lexer import ToyError
from compiler.backend.program import compile_source
from compiler.backend.tbc import write_tbc
from compiler.backend.disassembler import format_program

VM = os.path.join(ROOT, "vm", "gcvm")
if not os.path.exists(VM):
    subprocess.run(["make", "-s", "-C", os.path.join(ROOT, "vm")], check=True)


def bits(mask):
    return [i for i in range(64) if (mask >> i) & 1]


def program_json(p):
    return {
        "types": [{"id": t.type_id, "kind": t.kind, "name": t.name, "fields": t.field_count,
                   "ptr": bits(t.pointer_mask)} for t in p.types],
        "functions": [{"name": f.name, "start": f.start, "params": f.parameter_count,
                       "locals": f.local_count} for f in p.functions],
        "code": [[i.opcode, i.operand] for i in p.instructions],
        "maps": {m.pc: {"depth": m.depth, "locals": bits(m.locals_mask), "stack": bits(m.stack_mask)}
                 for m in p.stack_maps},
        "main": p.main_index,
    }


def run(source, gc, heap):
    try:
        prog = compile_source(source)
    except ToyError as error:
        return {"ok": False, "stage": "compilation", "error": str(error)}
    with tempfile.TemporaryDirectory() as tmp:
        tbc = os.path.join(tmp, "p.tbc")
        write_tbc(prog, tbc)
        cmd = [VM, tbc, f"--gc={gc}", f"--heap={int(heap)}", "--gc-stats"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            out, err, code = r.stdout, r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "timeout (20 s)", -1
    return {"ok": True, "bytecode": format_program(prog), "output": out[:20000], "stderr": err[:4000],
            "exit_code": code, "program": program_json(prog)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        files = {"/": ("index.html", "text/html"), "/gcsim.js": ("gcsim.js", "text/javascript")}
        if self.path in files:
            name, ctype = files[self.path]
            with open(os.path.join(HERE, name), "rb") as f:
                return self._send(200, f.read(), ctype + "; charset=utf-8")
        if self.path == "/api/examples":
            d = os.path.join(ROOT, "tests", "programs")
            ex = {n: open(os.path.join(d, n), encoding="utf-8").read()
                  for n in sorted(os.listdir(d)) if n.endswith(".toy") and not n.startswith(("bad_", "err_"))}
            return self._send(200, json.dumps(ex).encode(), "application/json")
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/run":
            return self._send(404, b"not found", "text/plain")
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        result = run(data.get("source", ""), data.get("gc", "ms"), data.get("heap", 8388608))
        self._send(200, json.dumps(result).encode(), "application/json")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8005
    print(f"VMPGC : http://localhost:{port}   (Ctrl+C pour arrêter)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
