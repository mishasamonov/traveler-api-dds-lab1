"""Laboratory 8: data model diagram (before / after), rendered by headless Edge like the other screenshots."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import render

CSS = """
body{margin:0;padding:18px;background:#fff;font-family:'Segoe UI',sans-serif;color:#1f2328}
.wrap{display:flex;gap:26px;align-items:stretch}
.side{flex:1;border:1px solid #d0d7de;border-radius:10px;padding:14px 16px;background:#f6f8fa}
h2{margin:0 0 10px;font-size:19px}
.sub{font-size:13.5px;color:#57606a;margin:-6px 0 12px}
.t{background:#fff;border:1.5px solid #0969da;border-radius:7px;margin:0 0 12px;overflow:hidden}
.t .h{background:#0969da;color:#fff;font-weight:600;padding:5px 10px;font-size:15px}
.t.doc{border-color:#1a7f37}.t.doc .h{background:#1a7f37}
.c{font:13.5px/1.5 'Cascadia Mono',Consolas,monospace;padding:6px 10px;white-space:pre}
.k{color:#cf222e}.n{color:#57606a}.j{color:#8250df}
.arrow{font-size:13px;color:#57606a;margin:-6px 0 8px 18px}
ul{margin:4px 0 0 18px;padding:0;font-size:14px;line-height:1.45}
.mid{display:flex;align-items:center;font-size:40px;color:#57606a}
"""

BODY = """
<div class="wrap">
<div class="side">
  <h2>До: дві таблиці (лабораторні 2-7)</h2>
  <div class="sub">на кожному з 16 шардів db_0..db_f</div>
  <div class="t"><div class="h">travel_plans</div><div class="c"><span class="k">id</span>          uuid PK
title       varchar(200)
description text
start_date  date        end_date date
budget      numeric(10,2) currency varchar(3)
is_public   boolean
version     integer   <span class="n">-- optimistic lock</span>
created_at, updated_at timestamptz</div></div>
  <div class="arrow">&#9650; FK travel_plan_id ON DELETE CASCADE (1 : N)</div>
  <div class="t"><div class="h">locations</div><div class="c"><span class="k">id</span>             uuid PK
<span class="k">travel_plan_id</span> uuid FK
name, address, notes
latitude numeric(10,6), longitude numeric(11,6)
visit_order    integer
arrival_date, departure_date timestamptz
budget, version, created_at
<span class="n">UNIQUE (travel_plan_id, visit_order)</span>
<span class="n">       DEFERRABLE INITIALLY IMMEDIATE</span></div></div>
  <ul><li>план з локаціями = 2 запити</li><li>нова локація: BEGIN, FOR UPDATE, MAX, INSERT, COMMIT</li>
  <li>зміна порядку: SET CONSTRAINTS DEFERRED + масовий UPDATE</li></ul>
</div>
<div class="mid">&#10132;</div>
<div class="side">
  <h2>Після: один документ на план (лабораторна 8)</h2>
  <div class="sub">plan_documents на тих самих 16 шардах</div>
  <div class="t doc"><div class="h">plan_documents</div><div class="c"><span class="k">id</span>         uuid PK      <span class="n">-- ключ шардування</span>
version    integer      <span class="n">-- optimistic lock плану</span>
created_at timestamptz  <span class="n">-- B-tree (created_at DESC, id)</span>
updated_at timestamptz
<span class="j">doc        jsonb</span>        <span class="n">-- CHECK plan_document_valid(doc, id)</span></div>
  <div class="c" style="background:#f0fff4;border-top:1px solid #d0d7de">{
  <span class="j">"title"</span>: "Baseline trip 7", <span class="j">"description"</span>: "...",
  <span class="j">"start_date"</span>: null, <span class="j">"end_date"</span>: null,
  <span class="j">"budget"</span>: 1000.00, <span class="j">"currency"</span>: "EUR", <span class="j">"is_public"</span>: false,
  <span class="j">"locations"</span>: [            <span class="n">-- GIN jsonb_path_ops</span>
    { <span class="j">"id"</span>: "...7", <span class="j">"name"</span>: "Location 1", <span class="j">"visit_order"</span>: 1,
      <span class="j">"latitude"</span>: 48.8566, ..., <span class="j">"version"</span>: 1, <span class="j">"created_at"</span>: "..." },
    { ... <span class="j">"visit_order"</span>: 2 }, { ... <span class="j">"visit_order"</span>: 3 }
  ]
}</div></div>
  <ul><li>план з локаціями = 1 читання за PK</li><li>нова локація: 1 атомарний UPDATE з jsonb_set</li>
  <li>зміна порядку: перестановка масиву під блокуванням рядка</li>
  <li>travel_plans_view і locations_view повертають старі рядки</li></ul>
</div>
</div>
"""

if __name__ == '__main__':
    page = f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><body>{BODY}</body>'
    render('d01-model', page, 1500)
