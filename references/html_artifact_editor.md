# Interactive HTML weld-map editor (artifact)

When a user wants to edit a `.weldb` panel **visually** — moving welds around a
grid rather than hand-editing YAML — build them an **HTML artifact**: a single
self-contained page that renders each view's grid as colored, editable cells and
exports the updated `.weldb` YAML for you to save.

This is the headless-friendly counterpart to the desktop Tkinter editor
(`weldb_visual_editor.py`), which only runs on a local machine with a display.
The artifact runs anywhere Claude can render one.

## How it works (and its constraints)

- **Artifacts cannot read the user's files.** You must **embed** the panel's data
  into the page when you generate it. Parse the `.weldb` file to a JSON object
  first (below) and paste it in as the `DOC` value.
- **The page cannot write files back.** The user edits, clicks **Export**, and
  copies (or downloads) the resulting YAML. You then save that text to the
  `.weldb` file with your own file tools.
- **Only the latest map is edited.** weldb history is append-only, so the editor
  makes the current (last) map's views editable; every earlier revision passes
  through the export unchanged. If the edit is a real layout change, append a new
  revision (bump `rev`, set today's date) rather than overwriting — do that in
  the YAML, or add a "new revision" step before handing off the file.

## Step 1 — turn the `.weldb` file into JSON for embedding

The weldb library is bundled with this skill; use it to parse (validates on the
way in), then print JSON:

```bash
python -c "import sys; sys.path.insert(0,'src'); import weldb, json; \
print(json.dumps(weldb.loads(open('N5.weldb').read())))"
```

Paste that JSON as the `DOC` constant in the template below.

## Step 2 — the template

Adapt this self-contained page. It has no external dependencies (works under the
artifact CSP), colors cells by weld type (same scheme as the desktop editor),
supports add/remove row & column per view, and exports weldb-valid YAML with a
small serializer that quotes every grid cell (so `*`/`@` never read as YAML
aliases/reserved characters).

```html
<div id="app"></div>
<script>
// ── Paste the panel JSON from step 1 here ──────────────────────────────────
const DOC = /* PANEL_JSON */ {
  "panel_name": "N5", "tube_mtrl": "SA-210 A1", "tube_od": 2.0, "tube_wall": 0.15,
  "units": "in", "elevation": "1850 in",
  "maps": [{ "rev": "R0", "date": "2026-01-01", "updated_by": "you", "comments": "init",
    "views": [
      { "name": "hot_side", "grid": [["_A","*T1","_B"],["","",""],["_A","*B1","_B"]] },
      { "name": "cold_side", "grid": [["","",""],["","",""],["","",""]] }
    ]}]
};
// ───────────────────────────────────────────────────────────────────────────

const FILL = { empty:"#ececec", point:"#d0f0d2", linear:"#cee0f6", area:"#fae4c8", label:"#ffffff" };
function cellFill(v){ v=(v||"").trim();
  if(!v) return FILL.empty;
  if(v[0]==="*") return FILL.point;
  if(v[0]==="_") return FILL.linear;
  if(v[0]==="@") return FILL.area;
  return FILL.label;
}
const curMap = DOC.maps[DOC.maps.length-1];

function render(){
  const app = document.getElementById("app");
  app.innerHTML = "";
  const h = document.createElement("div");
  h.innerHTML = `<h2 style="font-family:system-ui;margin:0 0 4px">${DOC.panel_name}
    — rev ${curMap.rev}</h2>
    <div style="font-family:system-ui;font-size:13px;color:#555;margin-bottom:12px">
    ${DOC.tube_mtrl} · OD ${DOC.tube_od} · wall ${DOC.tube_wall} · ${DOC.units}
    · elev ${DOC.elevation}</div>`;
  app.appendChild(h);

  curMap.views.forEach((view, vi) => {
    const box = document.createElement("div");
    box.style.margin = "0 0 20px";
    const bar = document.createElement("div");
    bar.style.cssText = "font-family:system-ui;font-weight:600;margin-bottom:6px";
    bar.textContent = view.name.replace(/_/g," ").toUpperCase();
    const btns = document.createElement("span");
    btns.style.cssText = "font-weight:400;margin-left:12px";
    [["+Row",()=>addRow(vi)],["−Row",()=>delRow(vi)],
     ["+Col",()=>addCol(vi)],["−Col",()=>delCol(vi)]].forEach(([t,fn])=>{
      const b=document.createElement("button"); b.textContent=t;
      b.style.cssText="margin-right:4px"; b.onclick=fn; btns.appendChild(b);
    });
    bar.appendChild(btns); box.appendChild(bar);

    const table = document.createElement("table");
    table.style.borderCollapse = "collapse";
    view.grid.forEach((row, r) => {
      const tr = document.createElement("tr");
      row.forEach((val, c) => {
        const td = document.createElement("td");
        td.style.border = "1px solid #999"; td.style.padding = "0";
        const inp = document.createElement("input");
        inp.value = val;
        inp.style.cssText = `width:70px;border:0;text-align:center;
          font-family:ui-monospace,monospace;background:${cellFill(val)};padding:4px`;
        inp.oninput = () => { view.grid[r][c] = inp.value; inp.style.background = cellFill(inp.value); };
        td.appendChild(inp); tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    box.appendChild(table); app.appendChild(box);
  });

  const out = document.createElement("div");
  out.innerHTML = `<button id="exp" style="font-family:system-ui;padding:6px 12px">
    Export .weldb YAML</button>
    <button id="dl" style="font-family:system-ui;padding:6px 12px;margin-left:6px">Download</button>
    <textarea id="yaml" style="display:block;width:100%;height:220px;margin-top:8px;
    font-family:ui-monospace,monospace;font-size:12px"></textarea>`;
  app.appendChild(out);
  document.getElementById("exp").onclick = () => { document.getElementById("yaml").value = docToYaml(DOC); };
  document.getElementById("dl").onclick = () => {
    const blob = new Blob([docToYaml(DOC)], {type:"text/yaml"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = DOC.panel_name + ".weldb"; a.click();
  };
}

function width(v){ return Math.max(...v.grid.map(r=>r.length), 1); }
function addRow(vi){ const v=curMap.views[vi]; v.grid.push(Array(width(v)).fill("")); render(); }
function delRow(vi){ const v=curMap.views[vi]; if(v.grid.length>1){ v.grid.pop(); render(); } }
function addCol(vi){ curMap.views[vi].grid.forEach(r=>r.push("")); render(); }
function delCol(vi){ const v=curMap.views[vi];
  if(width(v)>1){ v.grid.forEach(r=>{ if(r.length) r.pop(); }); render(); } }

// ── weldb-aware YAML serializer ────────────────────────────────────────────
function needsQuote(s){
  if(s==="") return true;
  if(/^\s|\s$/.test(s)) return true;
  if(/^[-?:,\[\]{}#&*!|>'"%@`]/.test(s)) return true;
  if(/:\s|\s#|[:#]/.test(s)) return true;
  if(/^(true|false|null|yes|no|on|off|~)$/i.test(s)) return true;
  if(/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(s)) return true;
  return false;
}
function qStr(s){ return '"' + String(s).replace(/\\/g,"\\\\").replace(/"/g,'\\"') + '"'; }
function scalar(v){
  if(typeof v==="number") return String(v);
  if(typeof v==="boolean") return v?"true":"false";
  if(v==null) return "null";
  return needsQuote(String(v)) ? qStr(v) : String(v);
}
function docToYaml(doc){
  let out = "";
  for(const [k,v] of Object.entries(doc)){
    if(k==="maps" || k==="weld_overrides") continue;
    out += k + ": " + scalar(v) + "\n";
  }
  if(doc.weld_overrides){
    out += "weld_overrides:\n";
    for(const [key,fields] of Object.entries(doc.weld_overrides)){
      out += "  " + (needsQuote(key)?qStr(key):key) + ":\n";
      for(const [fk,fv] of Object.entries(fields)) out += "    " + fk + ": " + scalar(fv) + "\n";
    }
  }
  out += "maps:\n";
  for(const m of doc.maps){
    out += "  - rev: " + scalar(m.rev) + "\n";
    for(const mk of ["date","updated_by","comments"])
      if(mk in m) out += "    " + mk + ": " + scalar(m[mk]) + "\n";
    out += "    views:\n";
    for(const view of m.views){
      out += "      - name: " + scalar(view.name) + "\n";
      out += "        grid:\n";
      for(const row of view.grid)
        out += "          - [" + row.map(qStr).join(", ") + "]\n";
    }
  }
  return out;
}

render();
</script>
```

## Step 3 — save the result

When the user pastes back (or hands you) the exported YAML, **round-trip it
through the library before saving** so a hand-tweak can't corrupt the file:

```bash
python -c "import sys; sys.path.insert(0,'src'); import weldb; \
weldb.loads(open('N5_edited.weldb').read()); print('valid')"
```

Then write it to the panel's `.weldb` file, and re-render the PDF
(`scripts/render_pdf.py`) or rebuild the CSVs (`scripts/build_weld_csvs.py`) if
those artifacts are being kept.

## Keep it faithful to the request

The template covers the common case (edit the current map's grids). Extend it as
the task needs — a read-only view of historical revisions, a legend, a
weld-count tally, an "append as new revision" button — but don't silently drop
data: the serializer must round-trip every field the input file had.
