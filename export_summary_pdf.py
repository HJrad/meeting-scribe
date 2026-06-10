#!/usr/bin/env python3
"""Export a meeting summary (.md) to a branded, CTO/PM-grade PDF.

Branding is partner-driven: each meeting in config/meetings.yaml carries a
`partner:` key, resolved against config/partners.yaml for logo + colours.
So a TicketMate meeting gets the TicketMate logo/theme, an iHaus meeting gets
the iHaus logo/theme, etc. Unknown/missing partner -> `default`.

Usage:
    python export_summary_pdf.py ONBOARDING_MEETING_002
    python export_summary_pdf.py ONBOARDING_MEETING_002 --partner ihaus   # override
"""
import sys, os, base64, argparse, subprocess, re
import yaml
from markdown_it import MarkdownIt

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTDIR = os.environ.get("FONTDIR", os.path.join(ROOT, "assets", "fonts"))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

DOC_LABEL = "Onboarding & Killer-Features Briefing"
DOC_AUDIENCE = "Prepared for CTO / Project Management"


def b64_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def font_face(file, weight):
    return (f"@font-face{{font-family:'Switzer';font-weight:{weight};font-style:normal;"
            f"src:url('data:font/woff2;base64,{b64_file(os.path.join(FONTDIR, file))}') format('woff2');}}")


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_logo_uri(logo_rel):
    if not logo_rel:
        return None
    path = os.path.join(ROOT, logo_rel)
    if not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg"}.get(ext.lstrip("."), "image/png")
    return f"data:{mime};base64,{b64_file(path)}"


def badge_html(body):
    """Wrap known status strings in coloured pills."""
    rules = [
        ("b-red", ["urgent", "today"]),
        ("b-amber", ["not started", "queued", "pending", "to be", "sending today", "send"]),
        ("b-green", ["finished", "built", "api finished", "field present", "done", "ready"]),
        ("b-blue", ["in progress", "ongoing", "requested", "partly"]),
    ]
    statuses = ["Urgent", "Not started / queued", "In progress (GUI mostly there)",
                "Field present; conversion logic pending", "Test env to be provided",
                "Open construction site", "Function-loop extension built", "API finished",
                "Sending today", "Pending send", "In progress", "Partly done", "Requested"]
    for w in sorted(statuses, key=len, reverse=True):
        low = w.lower()
        cls = "b-blue"
        for c, keys in rules:
            if any(k in low for k in keys):
                cls = c
                break
        body = re.sub(r"<td>" + re.escape(w) + r"</td>",
                      f"<td><span class='badge {cls}'>{w}</span></td>", body)
    return body


def build_html(md_text, meeting, partner, title_meta):
    primary = partner.get("primary", "#2800FF")
    ink = partner.get("ink", "#181834")
    accent = partner.get("accent", primary)
    logo_uri = resolve_logo_uri(partner.get("logo"))
    wordmark = partner.get("wordmark_html", partner.get("display_name", "TicketMate"))

    md = MarkdownIt("gfm-like", {"linkify": False, "html": True})
    body = badge_html(md.render(md_text))

    faces = "".join([
        font_face("Switzer-Light.woff2", 300),
        font_face("Switzer-Regular.woff2", 400),
        font_face("Switzer-Medium.woff2", 500),
        font_face("Switzer-Semibold.woff2", 600),
        font_face("Switzer-Bold.woff2", 700),
    ])

    logo_img = (f"<img class='mark' src='{logo_uri}'/>" if logo_uri else "")

    css = f"""
{faces}
*{{box-sizing:border-box;}}
@page{{size:A4;margin:12mm;}}
html,body{{font-family:'Switzer',-apple-system,Arial,sans-serif;color:{ink};font-size:10.5px;line-height:1.5;margin:0;-webkit-font-smoothing:antialiased;}}
table.page{{width:100%;border-collapse:collapse;}}
table.page > thead td, table.page > tfoot td, table.page > tbody > tr > td{{padding:0;border:none;}}

/* letterhead (repeats each page via thead) */
.lh{{display:flex;align-items:center;justify-content:space-between;
  border-bottom:2.5px solid {primary};padding:0 0 7px;margin-bottom:9mm;}}
.lh .brand{{display:flex;align-items:center;gap:10px;}}
.lh .mark{{width:30px;height:30px;border-radius:5px;}}
.lh .wm{{font-weight:700;font-size:16px;letter-spacing:-.3px;color:{ink};}}
.lh .wm span{{color:{primary};}}
.lh .doc{{text-align:right;font-size:8px;font-weight:600;color:#84848C;text-transform:uppercase;letter-spacing:1.3px;line-height:1.7;}}
.lh .doc b{{color:{primary};}}

.ft{{display:flex;align-items:center;justify-content:space-between;
  border-top:1px solid #D9D9D9;padding-top:6px;margin-top:9mm;
  font-size:7.5px;color:#84848C;letter-spacing:.4px;}}
.ft .conf{{text-transform:uppercase;font-weight:700;color:{primary};}}

/* cover meta strip under H1 */
h1{{font-size:28px;font-weight:700;letter-spacing:-.5px;margin:2px 0 0;color:{ink};}}
h2{{font-size:14.5px;font-weight:600;margin:24px 0 8px;padding:7px 11px;color:#fff;background:{primary};border-radius:5px;letter-spacing:.2px;page-break-after:avoid;}}
h3{{font-size:12px;font-weight:600;margin:15px 0 5px;color:{primary};padding-left:9px;border-left:3px solid {primary};page-break-after:avoid;}}
p,li{{font-weight:400;}}
strong{{font-weight:600;color:{ink};}}
em{{color:{accent};font-style:italic;}}
ul,ol{{margin:5px 0 10px;padding-left:20px;}}
li{{margin:2.5px 0;}}
li::marker{{color:{primary};}}
hr{{border:none;border-top:1px dashed #D9D9D9;margin:18px 0;}}
code{{background:#EEEDFF;color:{primary};padding:1px 5px;border-radius:3px;font-family:'SF Mono',Menlo,monospace;font-size:9px;font-weight:500;}}
blockquote{{border-left:3px solid {primary};background:#F6F6FF;margin:10px 0;padding:8px 14px;border-radius:0 5px 5px 0;color:{accent};font-size:10px;}}
blockquote p{{margin:0;}}

/* content tables */
.body table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:8.7px;border:1px solid #E8E8E8;border-radius:6px;overflow:hidden;}}
.body thead{{display:table-header-group;}}
.body th{{background:{ink};color:#fff;font-weight:600;text-align:left;padding:7px 8px;font-size:8.3px;letter-spacing:.3px;text-transform:uppercase;}}
.body td{{border-bottom:1px solid #E8E8E8;padding:6px 8px;vertical-align:top;}}
.body tr{{page-break-inside:avoid;}}
.body tbody tr:nth-child(even) td{{background:#FAFAFA;}}
.badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:7.6px;font-weight:600;white-space:nowrap;letter-spacing:.2px;}}
.b-green{{background:#E3F9E5;color:#0B7A2E;}}
.b-blue{{background:#EAEAFE;color:{primary};}}
.b-amber{{background:#FFF3CD;color:#9A6A00;}}
.b-red{{background:#FDE3E3;color:#C81E1E;}}
"""

    head = f"""<div class="lh">
  <div class="brand">{logo_img}<div class="wm">{wordmark}</div></div>
  <div class="doc"><b>{DOC_LABEL}</b><br/>{DOC_AUDIENCE}</div>
</div>"""

    foot = f"""<div class="ft">
  <div class="conf">Confidential — Internal</div>
  <div>{partner.get('display_name','TicketMate')} · {title_meta}</div>
</div>"""

    return f"""<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>
<body><table class="page">
<thead><tr><td>{head}</td></tr></thead>
<tfoot><tr><td>{foot}</td></tr></tfoot>
<tbody><tr><td><div class="body">{body}</div></td></tr></tbody>
</table></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meeting_id")
    ap.add_argument("--partner", default=None, help="override partner key")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    meetings = load_yaml(os.path.join(ROOT, "config/meetings.yaml"))["meetings"]
    partners = load_yaml(os.path.join(ROOT, "config/partners.yaml"))["partners"]

    if args.meeting_id not in meetings:
        sys.exit(f"meeting '{args.meeting_id}' not in config/meetings.yaml. "
                 f"Known: {', '.join(meetings)}")
    meeting = meetings[args.meeting_id]

    pkey = args.partner or meeting.get("partner") or "default"
    partner = partners.get(pkey, partners["default"])

    stem = os.path.splitext(meeting["source_audio"])[0]
    md_path = os.path.join(ROOT, "output/meetings", f"{stem}_summary.md")
    if not os.path.exists(md_path):
        sys.exit(f"summary not found: {md_path}")
    pdf_path = os.path.join(ROOT, "output/meetings", f"{stem}_summary.pdf")
    html_path = os.path.join(ROOT, "output/meetings", f".{stem}_summary.build.html")

    md_text = open(md_path, encoding="utf-8").read()
    title_meta = f"{meeting.get('title', stem)} · {meeting.get('date', '')}"
    html = build_html(md_text, meeting, partner, title_meta)
    open(html_path, "w", encoding="utf-8").write(html)

    res = subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                          f"--print-to-pdf={pdf_path}", html_path],
                         capture_output=True, text=True)
    if not os.path.exists(pdf_path):
        sys.exit("Chrome failed:\n" + res.stderr)
    os.remove(html_path)
    print(f"[{pkey}] {os.path.basename(md_path)} -> {pdf_path} "
          f"({os.path.getsize(pdf_path)//1024} KB)")
    if args.open:
        subprocess.run(["open", pdf_path])


if __name__ == "__main__":
    main()
