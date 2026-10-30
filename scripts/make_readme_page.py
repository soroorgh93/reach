"""Builds web/readme.html, the README as a page of the site (/readme), from README.md.

    pip install markdown && python scripts/make_readme_page.py

Run it again whenever README.md changes. Links to files the site does not serve become plain text; links to the
privacy page and the judges' brief point at their pages on the site; outside links open in a new tab.
"""
import html, re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SITE = {"web/privacy.html": "./privacy", "JUDGE.md": "./judge"}


def body_html(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc", "md_in_html"], extension_configs={"toc": {"toc_depth": "2"}})
    out = md.convert(md_text)
    toc = [(t["id"], t["name"]) for t in md.toc_tokens]

    def link(m):
        href, inner = html.unescape(m.group(1)), m.group(2)
        if href in SITE:
            return f'<a href="{SITE[href]}">{inner}</a>'
        if href.startswith(("http://", "https://")):
            return f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inner}</a>'
        if href.startswith("#"):
            return m.group(0)
        return inner                                            # a file in the repository: shown as text
    out = re.sub(r'<a href="([^"]+)">(.*?)</a>', link, out, flags=re.S)
    out = out.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    out = out.replace('src="web/assets/', 'src="./assets/')               # the README's pictures, as the site serves them
    return out, toc


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Reach README</title>
<meta name="description" content="What Reach is, how Qloo is used, how a session is made, how to run it, and the evidence behind it.">
<meta name="theme-color" content="#04050b">
<meta property="og:image" content="./assets/readme/social.jpg">
<link rel="icon" type="image/png" href="./icons/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{ --night: #04050b; --glass: rgba(237,231,218,.04); --ivory: #ede7da; --dim: rgba(237,231,218,.66); --faint: rgba(237,231,218,.42); --line: rgba(237,231,218,.10);
  --gold: #c9a24a; --gold2: #f1cf7d; --teal: #3fd1c0;
  --display: "Cormorant Garamond", Georgia, serif; --body: "IBM Plex Sans", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 24px; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
body {{ margin: 0; background: radial-gradient(70% 50% at 50% 0%, #0c111d 0%, var(--night) 70%) no-repeat, var(--night); color: var(--ivory); font-family: var(--body); font-size: 16px; line-height: 1.7; -webkit-font-smoothing: antialiased; }}
a {{ color: var(--gold2); text-underline-offset: 3px; text-decoration-color: rgba(241,207,125,.35); }} a:hover {{ color: #fff; text-decoration-color: var(--gold2); }}
:focus-visible {{ outline: 2px solid var(--gold2); outline-offset: 3px; }}
.wrap {{ max-width: 1240px; margin: 0 auto; padding: 0 clamp(16px, 4vw, 48px) 80px; }}
header {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 22px 0; flex-wrap: wrap; }}
.brand {{ display: flex; align-items: center; gap: 10px; font-family: var(--display); font-size: 26px; color: var(--ivory); text-decoration: none; }}
.brand img {{ width: 32px; height: 32px; border-radius: 50%; box-shadow: 0 0 0 1px rgba(201,162,74,.5), 0 0 22px rgba(201,162,74,.35); }}
nav.top {{ display: flex; flex-wrap: wrap; gap: 8px; }}
nav.top a {{ font-size: 14px; color: var(--ivory); text-decoration: none; padding: 7px 15px; border-radius: 999px; border: 1px solid var(--line); background: var(--glass); }}
nav.top a:hover {{ border-color: rgba(201,162,74,.6); }}
nav.top a.go {{ background: linear-gradient(180deg, #f1cf7d, #c9a24a); color: #120d02; border: 0; font-weight: 600; }}
img {{ max-width: 100%; height: auto; }}
.lead p[align] {{ text-align: center; }}
.lead p:first-child img {{ display: block; width: 100%; border-radius: 22px; box-shadow: 0 0 0 1px var(--line), 0 50px 120px -50px rgba(201,162,74,.35); }}
.lead p:nth-child(2) {{ max-width: 760px; margin: 38px auto 0; font-size: 19px; line-height: 1.7; color: var(--dim); }}
.lead p:nth-child(2) b {{ color: var(--ivory); font-weight: 500; }}
.lead p:nth-child(2) br {{ display: none; }}
.lead p:nth-child(3) {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 10px 5px; margin: 28px 0 0; font-size: 0; }}
.lead p:nth-child(3) a {{ font-size: 14px; text-decoration: none; color: var(--ivory); padding: 8px 16px; border-radius: 999px; border: 1px solid rgba(201,162,74,.45); background: var(--glass); }}
.lead p:nth-child(3) a b {{ font-weight: 500; }} .lead p:nth-child(3) a:hover {{ border-color: var(--gold2); }}
.lead p:nth-child(4) {{ text-align: center; margin: 34px 0 0; }} .lead p:nth-child(4) sub {{ display: block; margin-top: 4px; font-size: 13px; color: var(--faint); }} .lead p:nth-child(4) img {{ width: 300px; }}
.layout {{ display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 64px; margin-top: 72px; align-items: start; }}
.toc {{ position: sticky; top: 24px; font-size: 14px; border-inline-start: 1px solid var(--line); padding-inline-start: 16px; }}
.toc b {{ display: block; font-weight: 500; color: var(--faint); margin-bottom: 8px; }}
.toc a {{ display: block; color: var(--dim); text-decoration: none; padding: 5px 0; line-height: 1.35; }}
.toc a:hover, .toc a.on {{ color: var(--ivory); }} .toc a.on {{ box-shadow: -17px 0 0 -15px var(--gold2); }}
article {{ min-width: 0; }}
article > *:not(h2):not(.tablewrap):not(p[align]):not(details) {{ max-width: 74ch; }}
h1, h2, h3 {{ font-family: var(--display); font-weight: 500; letter-spacing: -0.01em; text-wrap: balance; }}
article h2 {{ font-size: clamp(36px, 4vw, 54px); line-height: 1.02; margin: 88px 0 22px; }}
article h2:first-child {{ margin-top: 0; }}
article p[align] {{ text-align: center; margin: 22px 0; }}
article p[align] img {{ display: block; margin: 0 auto; border-radius: 20px; box-shadow: 0 0 0 1px var(--line), 0 40px 90px -50px rgba(0,0,0,.9); }}
article sub {{ display: block; max-width: 70ch; margin: 0 auto; font-size: 14px; line-height: 1.6; color: var(--faint); vertical-align: baseline; }}
article p, article li {{ color: rgba(237,231,218,.86); }}
article strong, article b {{ font-weight: 600; color: var(--ivory); }}
article em {{ color: var(--ivory); }}
article ul, article ol {{ padding-inline-start: 22px; }} article li {{ margin: 8px 0; }} article li::marker {{ color: var(--gold); }}
code {{ font-family: var(--mono); font-size: .84em; background: rgba(237,231,218,.07); color: #f3e6c4; padding: 1px 6px; border-radius: 6px; overflow-wrap: anywhere; }}
pre {{ background: #0a0d17; box-shadow: 0 0 0 1px var(--line); color: #e9ebf2; padding: 18px 20px; border-radius: 16px; overflow-x: auto; font-size: 14px; line-height: 1.6; }}
pre code {{ background: none; padding: 0; color: inherit; font-size: inherit; overflow-wrap: normal; }}
.tablewrap {{ overflow-x: auto; margin: 22px 0; border-radius: 18px; background: var(--glass); box-shadow: 0 0 0 1px var(--line); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; line-height: 1.55; }}
th, td {{ text-align: start; vertical-align: top; padding: 12px 16px; border-bottom: 1px solid var(--line); }}
th {{ font-weight: 500; color: var(--gold2); }} tr:last-child td {{ border-bottom: 0; }}
td code {{ font-size: 12.5px; }}
details {{ border-top: 1px solid var(--line); }} details:last-of-type {{ border-bottom: 1px solid var(--line); }}
summary {{ cursor: pointer; list-style: none; padding: 20px 44px 20px 0; position: relative; font-family: var(--display); font-size: 27px; line-height: 1.2; }}
summary b {{ font-weight: 500; color: var(--ivory); }}
summary::-webkit-details-marker {{ display: none; }}
summary::after {{ content: ""; position: absolute; right: 8px; top: 50%; width: 12px; height: 12px; border-right: 1.5px solid var(--gold2); border-bottom: 1.5px solid var(--gold2); transform: translateY(-70%) rotate(45deg); transition: transform .25s ease; }}
details[open] summary::after {{ transform: translateY(-30%) rotate(225deg); }}
summary:hover b {{ color: var(--gold2); }}
details > *:not(summary) {{ max-width: 74ch; }} details[open] {{ padding-bottom: 18px; }}
footer {{ margin-top: 90px; padding-top: 22px; border-top: 1px solid var(--line); font-size: 14px; color: var(--faint); display: flex; flex-wrap: wrap; gap: 8px 20px; justify-content: space-between; }}
@media (max-width: 960px) {{ .layout {{ grid-template-columns: 1fr; gap: 0; margin-top: 40px; }} .toc {{ position: static; border: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 40px; }}
  .toc b {{ width: 100%; margin: 0 0 2px; }} .toc a {{ padding: 5px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--glass); }} .toc a.on {{ box-shadow: none; }}
  .lead p:first-child img {{ border-radius: 14px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header><a class="brand" href="./"><img src="./icons/favicon.png" alt="">Reach</a>
    <nav class="top" aria-label="Reach"><a href="./judge">Judges' brief</a><a href="./privacy">Privacy</a><a class="go" href="./?app=1">Open the app</a></nav></header>
  <div class="lead">
{lead}
  </div>
  <div class="layout">
    <nav class="toc" aria-label="Contents"><b>Contents</b>{toc}</nav>
    <article>
{body}
    </article>
  </div>
  <footer><span>Reach, open source under the MIT licence. Built for the Qloo Agentic Hackathon 2026.</span><span id="repo"></span></footer>
</div>
<script>
// the contents follow the reading; the source link appears when the server knows it
const links = [...document.querySelectorAll(".toc a")], heads = links.map(a => document.getElementById(a.hash.slice(1))).filter(Boolean);
const mark = () => {{ let i = 0; heads.forEach((h, k) => {{ if (h.getBoundingClientRect().top < 120) i = k; }}); links.forEach((a, k) => a.classList.toggle("on", k === i)); }};
addEventListener("scroll", mark, {{ passive: true }}); mark();
fetch("/api/health").then(r => r.json()).then(h => {{ if (h && h.repo) {{ const a = document.createElement("a"); a.href = h.repo; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Source code"; document.getElementById("repo").appendChild(a); }} }}).catch(() => {{}});
</script>
</body>
</html>
"""


def main():
    md_text = (ROOT / "README.md").read_text(encoding="utf-8")
    lead_md, _, rest = md_text.partition("<!-- contents -->")      # the banner and the opening lines go above the contents
    lead, _ = body_html(lead_md)
    body, toc = body_html(rest)
    body = body.replace("<img ", '<img loading="lazy" ')                  # the film and diagrams load as the reader reaches them
    page = PAGE.format(lead=lead, toc="".join(f'<a href="#{i}">{html.escape(html.unescape(n))}</a>' for i, n in toc), body=body)
    (ROOT / "web" / "readme.html").write_text(page, encoding="utf-8")
    print("web/readme.html", len(page), "bytes,", len(toc), "sections")


if __name__ == "__main__":
    main()
