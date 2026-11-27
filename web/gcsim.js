/* Simulateur de la VM Toy + des deux collecteurs (Mark-and-Sweep, Cheney), pour le visualisateur.
 * Il suit vm/interp.c et vm/heap.c : mêmes tailles de blocs (en-tête 16 octets), même first-fit,
 * mêmes racines (stack maps). Il enregistre des instantanés du tas. Les entiers sont des nombres JS,
 * et des BigInt dès qu'ils dépassent 2^53 : l'arithmétique 64 bits avec retour (wrap) reste exacte. */
(function (root) {
  const HDR = 16, B = 65536;   // B : adresse de base du tas (0 est réservé à null)
  // états d'un bloc : 0 libre, 1 objet, 2 vivant (marqué/copié), 3 mort, 4 nouveau, 5 déjà copié, 6 semi-espace inutilisé
  function simulate(prog, opt) {
    const total = opt.heap & ~15, isMS = opt.gc === "ms";
    const half = Math.floor(total / 2) & ~15;
    const maxSteps = opt.maxSteps || 3000000, maxEvents = opt.maxEvents || 1500, blockBudget = opt.blockBudget || 400000;
    const objs = new Map(), events = [], out = [];
    let free = isMS ? [{ a: B, s: total }] : [], cur = 0, bump = B, limit = B + half;
    const st = { coll: 0, objs: 0, bytes: 0, rec: 0 };
    let blocksUsed = 0, steps = 0, frames = [];

    const refsOf = (o) => {
      const t = prog.types[o.type - 1];
      if (t.kind === 1) return t.ptr.filter((k) => k < o.slots.length);
      if (t.kind === 3) return o.slots.map((_, k) => k);
      return [];
    };
    function rootSlots() {
      const r = [];
      for (const f of frames) {
        const m = prog.maps[f.pc];
        if (!m) throw new Error("pas de stack map à l'instruction " + f.pc);
        for (const k of m.locals) r.push([f.locals, k]);
        for (const k of m.stack) if (k < m.depth) r.push([f.stack, k]);
      }
      return r;
    }
    function snap(kind, label, stateOf, freeBlocks) {
      if (events.length >= maxEvents || blocksUsed > blockBudget) return;
      const b = [];
      for (const [a, o] of objs) b.push([a - B, o.size, stateOf(a), o.type]);
      for (const f of freeBlocks) b.push([f.a - B, f.s, f.st || 0, 0]);
      b.sort((x, y) => x[0] - y[0]);
      blocksUsed += b.length;
      let roots = [];
      try { roots = rootSlots().map(([arr, k]) => arr[k]).filter((v) => v !== 0 && objs.has(v)).map((v) => v - B); } catch (e) { /* hors point de sûreté : pas de racines à afficher */ }
      events.push({ k: kind, label, step: steps, fn: frames.length ? prog.functions[frames[frames.length - 1].fn].name : "",
        depth: frames.length, blocks: b, roots, stats: { ...st }, cur });
    }
    const plain = () => (isMS ? free : [{ a: bump, s: limit - bump }, { a: B + (1 - cur) * half, s: half, st: 6 }]);

    /* ----- Mark-and-Sweep ----- */
    function collectMS() {
      snap("gc", "Début de la collecte", () => 1, free);
      const marked = new Set(), stack = [];
      const push = (v) => { if (v !== 0 && !marked.has(v)) { marked.add(v); stack.push(v); } };
      for (const [arr, k] of rootSlots()) push(arr[k]);
      while (stack.length) { const o = objs.get(stack.pop()); for (const k of refsOf(o)) push(o.slots[k]); }
      snap("gc", "Marquage terminé : vivants / morts", (a) => (marked.has(a) ? 2 : 3), free);
      const all = [...objs].map(([a, o]) => ({ a, s: o.size, obj: true })).concat(free.map((f) => ({ a: f.a, s: f.s, obj: false })));
      all.sort((x, y) => x.a - y.a);
      const nf = []; let run = null;
      for (const b of all) {
        if (b.obj && marked.has(b.a)) { if (run) { nf.push(run); run = null; } }
        else { if (b.obj) { st.rec += b.s; objs.delete(b.a); } if (!run) run = { a: b.a, s: 0 }; run.s += b.s; }
      }
      if (run) nf.push(run);
      free = nf;
    }
    function allocMS(bytes) {
      for (let i = 0; i < free.length; i++) {
        const f = free[i];
        if (f.s >= bytes) {
          const a = f.a, rest = f.s - bytes;
          if (rest >= HDR) { free[i] = { a: a + bytes, s: rest }; return [a, bytes]; }
          free.splice(i, 1); return [a, f.s];
        }
      }
      return null;
    }

    /* ----- Stop-and-Copy (Cheney) ----- */
    function collectCopy() {
      const fromStart = B + cur * half, toStart = B + (1 - cur) * half, usedBefore = bump - fromStart;
      snap("gc", "Début de la collecte", () => 1, [{ a: bump, s: limit - bump }, { a: toStart, s: half, st: 6 }]);
      let fp = toStart; const fwd = new Map(), order = [];
      const forward = (v) => {
        if (v === 0) return 0;
        if (fwd.has(v)) return fwd.get(v);
        const o = objs.get(v), n = fp; fp += o.size;
        objs.set(n, { type: o.type, size: o.size, slots: o.slots.slice() });
        fwd.set(v, n); order.push(n); return n;
      };
      for (const [arr, k] of rootSlots()) arr[k] = forward(arr[k]);
      for (let i = 0; i < order.length; i++) { const o = objs.get(order[i]); for (const k of refsOf(o)) o.slots[k] = forward(o.slots[k]); }
      const inFrom = (a) => a >= fromStart && a < fromStart + half;
      snap("gc", "Copie terminée : les objets vivants sont dans le nouvel espace", (a) => (inFrom(a) ? (fwd.has(a) ? 5 : 3) : 2),
        [{ a: fp, s: toStart + half - fp }, { a: bump, s: fromStart + half - bump, st: 6 }]);
      for (const a of [...objs.keys()]) if (inFrom(a)) objs.delete(a);
      st.rec += usedBefore - (fp - toStart);
      cur = 1 - cur; bump = fp; limit = toStart + half;
    }

    class Stop extends Error { constructor(status, message, code) { super(message); this.status = status; this.code = code; } }
    function collect() { st.coll++; isMS ? collectMS() : collectCopy(); snap("gc", "Collecte terminée", () => 1, plain()); }
    function heapAlloc(type, slots) {
      if (slots > total / 8) throw new Stop("oom", `mémoire insuffisante : objet de ${slots} cases, tas de ${total} octets`, 101);
      const bytes = HDR + slots * 8;
      let r = isMS ? allocMS(bytes) : (limit - bump >= bytes ? (bump += bytes, [bump - bytes, bytes]) : null);
      if (!r) {
        collect();
        r = isMS ? allocMS(bytes) : (limit - bump >= bytes ? (bump += bytes, [bump - bytes, bytes]) : null);
        if (!r) throw new Stop("oom", `mémoire insuffisante : objet de ${slots} cases, tas de ${total} octets`, 101);
      }
      objs.set(r[0], { type, size: r[1], slots: new Array(slots).fill(0) });
      st.objs++; st.bytes += r[1];
      return r[0];
    }
    const MAXS = 2n ** 53n - 1n;
    const norm = (r) => { r = BigInt.asIntN(64, r); return r >= -MAXS && r <= MAXS ? Number(r) : r; };
    const big = (a, b, f) => norm(f(BigInt(a), BigInt(b)));

    const mainFn = prog.functions[prog.main];
    frames = [{ fn: prog.main, pc: mainFn.start, locals: new Array(mainFn.locals).fill(0), stack: [] }];
    let status = "ok", message = "", exitCode = 0;
    try {
      const code = prog.code;
      for (;;) {
        if (++steps > maxSteps) { status = "truncated"; message = `simulation arrêtée après ${maxSteps} instructions`; break; }
        const f = frames[frames.length - 1], [op, arg] = code[f.pc], s = f.stack;
        const err = (m) => { throw new Stop("error", m + ` (fonction '${prog.functions[f.fn].name}', instruction ${f.pc})`, 100); };
        switch (op) {
          case "PUSH_INT": s.push(arg); f.pc++; break;
          case "PUSH_NULL": s.push(0); f.pc++; break;
          case "POP": s.pop(); f.pc++; break;
          case "LOAD_LOCAL": s.push(f.locals[arg]); f.pc++; break;
          case "STORE_LOCAL": f.locals[arg] = s.pop(); f.pc++; break;
          case "ADD": { const b = s.pop(), a = s.pop(); s.push(typeof a === "number" && typeof b === "number" && Number.isSafeInteger(a + b) ? a + b : big(a, b, (x, y) => x + y)); f.pc++; break; }
          case "SUB": { const b = s.pop(), a = s.pop(); s.push(typeof a === "number" && typeof b === "number" && Number.isSafeInteger(a - b) ? a - b : big(a, b, (x, y) => x - y)); f.pc++; break; }
          case "MUL": { const b = s.pop(), a = s.pop(); s.push(typeof a === "number" && typeof b === "number" && Number.isSafeInteger(a * b) ? a * b : big(a, b, (x, y) => x * y)); f.pc++; break; }
          case "DIV": { const b = s.pop(), a = s.pop(); if (b == 0) err("division par zéro"); s.push(b == -1 ? norm(-BigInt(a)) : big(a, b, (x, y) => x / y)); f.pc++; break; }
          case "MOD": { const b = s.pop(), a = s.pop(); if (b == 0) err("modulo par zéro"); s.push(b == -1 ? 0 : big(a, b, (x, y) => x % y)); f.pc++; break; }
          case "NEG": s.push(norm(-BigInt(s.pop()))); f.pc++; break;
          case "NOT": s.push(s.pop() == 0 ? 1 : 0); f.pc++; break;
          case "EQ": case "NE": case "LT": case "LE": case "GT": case "GE": {
            const b = s.pop(), a = s.pop();
            s.push(+({ EQ: a == b, NE: a != b, LT: a < b, LE: a <= b, GT: a > b, GE: a >= b })[op]); f.pc++; break;
          }
          case "JMP": f.pc = arg; break;
          case "JZ": f.pc = s.pop() == 0 ? arg : f.pc + 1; break;
          case "CALL": {
            if (frames.length >= 10000) err("dépassement de pile (plus de 10000 appels)");
            const c = prog.functions[arg], locals = s.splice(s.length - c.params, c.params);
            while (locals.length < c.locals) locals.push(0);
            frames.push({ fn: arg, pc: c.start, locals, stack: [] }); break;   // l'appelant reste suspendu sur le CALL
          }
          case "RET": {
            const r = s.pop();
            if (frames.length === 1) { exitCode = Number(BigInt.asUintN(8, BigInt(r))); throw new Stop("ok", "", exitCode); }
            frames.pop(); const c = frames[frames.length - 1]; c.stack.push(r); c.pc++; break;
          }
          case "NEW": { const a = heapAlloc(arg, prog.types[arg - 1].fields); s.push(a); snap("alloc", "NEW " + prog.types[arg - 1].name, (x) => (x === a ? 4 : 1), plain()); f.pc++; break; }
          case "NEW_ARRAY": {
            const n = s.pop(); if (n < 0) err("taille de tableau négative (" + n + ")");
            const a = heapAlloc(arg, n); s.push(a); snap("alloc", "NEW_ARRAY " + prog.types[arg - 1].name, (x) => (x === a ? 4 : 1), plain()); f.pc++; break;
          }
          case "GETFIELD": { const a = s.pop(); if (a === 0) err("référence null (lecture d'un champ)"); s.push(objs.get(a).slots[arg]); f.pc++; break; }
          case "PUTFIELD": { const v = s.pop(), a = s.pop(); if (a === 0) err("référence null (écriture d'un champ)"); objs.get(a).slots[arg] = v; f.pc++; break; }
          case "ALOAD": {
            const i = s.pop(), a = s.pop(); if (a === 0) err("référence null (lecture d'un tableau)");
            const o = objs.get(a); if (i < 0 || i >= o.slots.length) err(`indice ${i} hors limites (longueur ${o.slots.length})`);
            s.push(o.slots[i]); f.pc++; break;
          }
          case "ASTORE": {
            const v = s.pop(), i = s.pop(), a = s.pop(); if (a === 0) err("référence null (écriture d'un tableau)");
            const o = objs.get(a); if (i < 0 || i >= o.slots.length) err(`indice ${i} hors limites (longueur ${o.slots.length})`);
            o.slots[i] = v; f.pc++; break;
          }
          case "PRINT_INT": out.push(String(s.pop())); f.pc++; break;
          case "PRINT_BOOL": out.push(s.pop() ? "true" : "false"); f.pc++; break;
          default: err("instruction invalide " + op);
        }
      }
    } catch (e) {
      if (!(e instanceof Stop)) throw e;
      status = e.status; message = e.message; exitCode = e.code;
    }
    snap("end", "Fin de l'exécution", () => 1, plain());
    return { events, output: out, stats: st, status, message, exitCode, steps, totalBytes: total, half, isMS };
  }
  const api = { simulate };
  if (typeof module !== "undefined") module.exports = api; else root.GCSim = api;
})(typeof window !== "undefined" ? window : globalThis);
