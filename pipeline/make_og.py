#!/usr/bin/env python3
"""Render site/og.png (1200x630 link preview) from work/summary.json with headless Chrome/Chromium.
usage: CHROME=/path/to/chrome python3 pipeline/make_og.py"""
import glob, json, os, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(os.path.join(ROOT, "work", "summary.json")))
T = S["totals"]
fmt = lambda n: f"{n:,}".replace(",", " ")
mx = max(t["n"] for t in S["tracks"])
bars = "".join(
    f'<div class="r"><span class="k">{t["id"]:02d}</span><span class="l">{t["partner"] if t["industry"] == "Спецтрек" else t["industry"]}</span>'
    f'<span class="bt"><span class="b" style="width:{int(215 * t["n"] / mx)}px"></span><span class="v">{t["n"]}</span></span></div>'
    for t in S["tracks"])
html = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@500&family=Unbounded:wght@600;700&display=swap">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:1200px;height:630px;background:#F1F4F3;color:#13201C;font-family:"Golos Text",system-ui,sans-serif}}
.w{{display:grid;grid-template-columns:1fr 520px;gap:48px;padding:56px 64px;height:100%}}
.e{{font:600 16px/1 "Golos Text";letter-spacing:.08em;text-transform:uppercase;color:#687873}}
h1{{font:700 64px/1.02 Unbounded,sans-serif;letter-spacing:-.02em;margin:22px 0 22px}} h1 em{{font-style:normal;color:#0B6E69}}
p{{font-size:22px;line-height:1.4;color:#3F4F4A;margin:0;max-width:30ch}}
.k4{{display:flex;gap:34px;margin-top:40px}} .k4 b{{display:block;font:600 36px/1 "Golos Text";color:#0B6E69}} .k4 span{{font-size:16px;color:#687873}}
.c{{align-self:center;background:#fff;border:1px solid #D3DBD8;border-radius:18px;padding:24px 26px;display:grid;gap:9px}}
.r{{display:grid;grid-template-columns:28px 190px 1fr;align-items:center;gap:8px}}
.bt{{display:flex;align-items:center;gap:8px}}
.r .k{{font:500 13px "JetBrains Mono";color:#687873}} .r .l{{font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.r .b{{height:16px;background:#0B6E69;border-radius:0 4px 4px 0;display:inline-block}}
.r .v{{font:500 13px "JetBrains Mono";color:#3F4F4A}}
.r:nth-child(7) .b{{background:#D29A1E}}
</style></head><body><div class="w"><div>
<div class="e">HackAlem.ai · финал 23.09.2026</div>
<h1>Атлас решений <em>HackAlem</em></h1>
<p>Как команды решали 12 кейсов: подходы, сильные решения, README и коммиты каждого проекта.</p>
<div class="k4"><div><b>{fmt(T['case_repos'])}</b><span>решений</span></div><div><b>12</b><span>кейсов</span></div><div><b>{fmt(T['commits'])}</b><span>коммитов</span></div></div>
</div><div class="c">{bars}</div></div></body></html>"""
chrome = os.environ.get("CHROME") or next(iter(sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))), "chromium")
with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
    f.write(html)
out = os.path.join(ROOT, "site", "og.png")
subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,630",
                "--virtual-time-budget=6000", f"--screenshot={out}", "file://" + f.name], check=True, capture_output=True)
os.unlink(f.name)
print("wrote", out)
