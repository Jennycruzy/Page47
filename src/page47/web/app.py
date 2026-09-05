"""Small FastAPI console for browsing the stored public record."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from page47.snapshotter.config import JSONObject
from page47.web.config import load_web_settings
from page47.web.service import WatchInput, WebService


class WatchRequest(BaseModel):
    city: str = Field(min_length=1)
    bodies: list[str] = Field(min_length=1)
    address: str | None = None
    neighbourhood: str | None = None
    email: str = Field(min_length=3)


def _config_path() -> Path:
    configured = os.environ.get("PAGE47_WEB_CONFIG")
    if configured is not None and configured.strip():
        return Path(configured)
    working_path = Path("config/web.yaml")
    if working_path.exists():
        return working_path
    return Path(__file__).resolve().parents[3] / "config" / "web.yaml"


def create_app(config_path: Path | None = None) -> FastAPI:
    settings = load_web_settings(config_path if config_path is not None else _config_path())
    service = WebService(settings)
    app = FastAPI(title=settings.title, docs_url="/docs", redoc_url=None)

    @app.get("/healthz")
    def health() -> JSONObject:
        return {"status": "ok", "service": settings.title}

    @app.get("/api/cities")
    def cities() -> JSONObject:
        return service.cities()

    @app.get("/api/cities/{city}/bodies")
    def bodies(city: str) -> JSONObject:
        try:
            return service.bodies(city)
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/cities/{city}/matters")
    def matters(city: str, limit: int = Query(default=50, ge=1, le=200)) -> JSONObject:
        try:
            return service.matters(city, limit)
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/cities/{city}/matters/{matter_id}")
    def matter(city: str, matter_id: int) -> JSONObject:
        try:
            return service.matter(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.get("/api/cities/{city}/findings")
    def findings(city: str, limit: int = Query(default=50, ge=1, le=200)) -> JSONObject:
        try:
            return service.findings(city, limit)
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/cities/{city}/findings/{finding_id}")
    def finding(city: str, finding_id: str) -> JSONObject:
        try:
            return service.finding(city, finding_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/cities/{city}/ledger")
    def ledger(city: str) -> JSONObject:
        try:
            return service.ledger(city)
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/cities/{city}/norms")
    def norms(city: str) -> JSONObject:
        try:
            return service.norms(city)
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/watches")
    def create_watch(request: WatchRequest) -> JSONObject:
        try:
            return service.create_watch(
                WatchInput(
                    city=request.city,
                    bodies=tuple(request.bodies),
                    address=request.address,
                    neighbourhood=request.neighbourhood,
                    email=request.email,
                )
            )
        except (LookupError, ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/cities/{city}/matters/{matter_id}/investigate")
    def investigate(city: str, matter_id: int) -> JSONObject:
        try:
            return service.investigate(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.get("/evidence/{city}/attachment/{attachment_id}/file")
    def attachment_file(city: str, attachment_id: int) -> Response:
        try:
            body, source = service.attachment_file(city, attachment_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(
            content=body,
            media_type="application/pdf",
            headers={"X-Page47-Captured-At": source.captured_at},
        )

    @app.get("/evidence/{city}/attachment/{attachment_id}", response_class=HTMLResponse)
    def attachment_evidence(city: str, attachment_id: int) -> HTMLResponse:
        try:
            data = service.attachment_evidence(city, attachment_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(_evidence_page(settings.title, city, data, settings.public_path))

    @app.get("/matter/{city}/{matter_id}", response_class=HTMLResponse)
    def matter_page(city: str, matter_id: int) -> HTMLResponse:
        try:
            data = service.matter(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return HTMLResponse(_matter_page(settings.title, city, data, settings.public_path))

    @app.get("/finding/{city}/{finding_id}", response_class=HTMLResponse)
    def finding_page(city: str, finding_id: str) -> HTMLResponse:
        try:
            data = service.finding(city, finding_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(_finding_page(settings.title, city, data, settings.public_path))

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_index_page(settings.title, settings.default_city, settings.public_path))

    return app


def _internal_url(public_path: str, path: str) -> str:
    if path.startswith(("https://", "http://")):
        return path
    return f"{public_path}{path if path.startswith('/') else f'/{path}'}"


def _index_page(title: str, default_city: str, public_path: str) -> str:
    safe_title = html.escape(title)
    default_city_json = json.dumps(default_city)
    public_path_json = json.dumps(public_path)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{ color-scheme: light; --ink:#17211b; --muted:#68736b; --paper:#fbfaf5; --green:#245c45; --gold:#e9b949; --line:#d9dfd8; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:16px/1.5 system-ui,sans-serif; color:var(--ink); background:var(--paper); }}
header {{ padding:28px max(24px,calc((100vw - 1120px)/2)); background:var(--green); color:white; }}
main {{ max-width:1120px; margin:0 auto; padding:28px 24px 60px; }} h1,h2 {{ line-height:1.15; }} h1 {{ margin:0 0 8px; font-size:clamp(2rem,5vw,4rem); }}
.lede {{ max-width:720px; font-size:1.1rem; }} .toolbar {{ display:flex; gap:12px; flex-wrap:wrap; margin:22px 0; }}
select,button,input {{ border:1px solid var(--line); border-radius:10px; background:white; padding:11px 13px; font:inherit; }} button {{ cursor:pointer; background:var(--gold); border-color:#c79526; font-weight:700; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:16px; }} .card {{ background:white; border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 4px 16px #17211b0b; }}
.card a {{ color:var(--green); font-weight:700; }} .tag {{ display:inline-block; padding:3px 8px; border-radius:99px; background:#edf2ee; color:var(--green); font-size:.85rem; }}
.muted {{ color:var(--muted); }} .ledger {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin:16px 0 30px; }} .metric {{ padding:14px; border-left:4px solid var(--gold); background:white; }} .metric strong {{ display:block; font-size:1.6rem; }}
.empty {{ padding:28px; background:white; border:1px dashed var(--line); border-radius:14px; }} footer {{ max-width:1120px; margin:auto; padding:24px; color:var(--muted); }} .body-list {{ display:flex; gap:12px; flex-wrap:wrap; margin:12px 0 18px; }} .body-list label {{ background:#edf2ee; border-radius:9px; padding:8px 10px; }} .watch-fields {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:16px; }} .watch-fields label {{ display:flex; flex-direction:column; gap:5px; }}
</style></head><body><header><h1>{safe_title}</h1><div>See how public matters were described over time.</div></header>
<main><p class="lede">Page 47 reads the public record for residents, neighbourhood groups, and local reporters. Each result links back to the city record. It does not determine why changes were made.</p>
<div class="toolbar"><label>City <select id="city"></select></label><button id="refresh">Refresh record</button></div>
<section class="card"><h2>Watch a neighbourhood</h2><p class="muted">Choose a public body and an address or neighbourhood. Page 47 will check the stored public record and email one review when a matter is worth a look.</p><form id="watch-form"><div id="bodies" class="body-list">Loading public bodies…</div><div class="watch-fields"><label>Address <input id="address" autocomplete="street-address" placeholder="123 Main Street, Seattle, WA"></label><label>Neighbourhood <input id="neighbourhood" placeholder="Neighbourhood name"></label><label>Email <input id="email" type="email" required placeholder="you@example.org"></label></div><button type="submit">Save this watch</button><p id="watch-result" class="muted" aria-live="polite"></p></form></section>
<section><h2>What the record shows</h2><div id="ledger" class="ledger"></div></section>
<section><h2>Recent public matters</h2><div id="matters" class="grid"><div class="empty">Loading the stored public record…</div></div></section>
<section><h2>Reviewed items</h2><div id="findings" class="grid"><div class="empty">Loading saved reviews…</div></div></section>
</main><footer>Page 47 reports public records. A record that was never published is outside what this tool can see.<br>Page 47 does not determine why these changes were made.</footer>
<script>
const defaultCity = {default_city_json}; const publicPath = {public_path_json};
const citySelect=document.querySelector('#city'); const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
async function json(url) {{ const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }}
function internal(path) {{ return publicPath + (path.startsWith('/') ? path : `/${{path}}`); }}
function chosen() {{ return citySelect.value || defaultCity; }}
function metric(label,value) {{ return `<div class="metric"><strong>${{esc(value)}}</strong><span>${{esc(label)}}</span></div>`; }}
async function loadBodies() {{ const city=chosen(); const data=await json(internal(`/api/cities/${{encodeURIComponent(city)}}/bodies`)); document.querySelector('#bodies').innerHTML=data.bodies.map((body,index)=>`<label><input type="checkbox" name="body" value="${{esc(body)}}" ${{index===0?'checked':''}}> ${{esc(body)}}</label>`).join(''); }}
async function load() {{ const city=chosen(); const [ledger,matters,findings]=await Promise.all([json(internal(`/api/cities/${{encodeURIComponent(city)}}/ledger`)),json(internal(`/api/cities/${{encodeURIComponent(city)}}/matters?limit=40`)),json(internal(`/api/cities/${{encodeURIComponent(city)}}/findings?limit=40`)]);
document.querySelector('#ledger').innerHTML=[metric('matters observed',ledger.matters_observed),metric('packet changes recorded',ledger.packet_changes_recorded),metric('became less clear',ledger.became_less_clear),metric('became clearer',ledger.became_clearer),metric('interpretations rejected',ledger.interpretations_rejected),metric('claims about intent',ledger.claims_about_intent)].join('');
document.querySelector('#matters').innerHTML=matters.matters.length?matters.matters.map(m=>`<article class="card"><span class="tag">${{esc(m.placement_note)}}</span><h3>${{esc(m.latest_title||m.current_title||'Untitled public matter')}}</h3><p class="muted">${{esc(m.body_name)}} · ${{esc(m.latest_event_date)}} · item ${{esc(m.matter_id)}}</p><a href="${{internal(`/matter/${{encodeURIComponent(city)}}/${{m.matter_id}}`)}}">Open record</a></article>`).join(''):'<div class="empty">No stored matters were found.</div>';
document.querySelector('#findings').innerHTML=findings.findings.length?findings.findings.map(f=>`<article class="card"><span class="tag">${{esc(f.state)}}</span><h3>Item ${{esc(f.matter_id)}}</h3><p>${{esc(f.supported_count)}} recorded observations supported · ${{esc(f.rejected_count)}} rejected in review</p><a href="${{internal(`/finding/${{encodeURIComponent(city)}}/${{encodeURIComponent(f.finding_id)}}`)}}">Read the review</a></article>`).join(''):'<div class="empty">No reviewed items have been saved yet.</div>'; }}
async function init() {{ const data=await json(internal('/api/cities')); citySelect.innerHTML=data.cities.map(c=>`<option>${{esc(c.name)}}</option>`).join(''); citySelect.value=defaultCity; await loadBodies(); await load(); }}
document.querySelector('#refresh').onclick=load; citySelect.onchange=async()=>{{await loadBodies(); await load();}}; document.querySelector('#watch-form').onsubmit=async(event)=>{{event.preventDefault(); const result=document.querySelector('#watch-result'); const bodies=[...document.querySelectorAll('input[name="body"]:checked')].map(input=>input.value); const address=document.querySelector('#address').value.trim()||null; const neighbourhood=document.querySelector('#neighbourhood').value.trim()||null; if(!address&&!neighbourhood){{result.textContent='Enter an address or neighbourhood.'; return;}} result.textContent='Saving…'; try {{ const response=await fetch(internal('/api/watches'),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{city:chosen(),bodies,address,neighbourhood,email:document.querySelector('#email').value.trim()}})}}); const payload=await response.json(); if(!response.ok) throw new Error(payload.detail||'The watch could not be saved.'); result.textContent=payload.message; }} catch(error) {{result.textContent=`Could not save the watch: ${{esc(error.message)}}`;}} }}; init().catch(e=>{{document.querySelector('#matters').innerHTML=`<div class="empty">Could not load the record: ${{esc(e.message)}}`;}});
</script></body></html>"""


def _evidence_page(title: str, city: str, data: JSONObject, public_path: str) -> str:
    attachment = data.get("attachment")
    if not isinstance(attachment, dict):
        raise HTTPException(status_code=500, detail="Stored attachment evidence was invalid")
    name = html.escape(str(attachment.get("name") or "Captured public document"))
    pdf_url = html.escape(_internal_url(public_path, str(data.get("pdf_url"))))
    anchors = data.get("anchors")
    blocks: list[str] = []
    if isinstance(anchors, list):
        for item in anchors:
            if not isinstance(item, dict):
                continue
            page = html.escape(str(item.get("page_number")))
            excerpt = html.escape(str(item.get("excerpt")))
            blocks.append(f"<blockquote><b>PDF page {page}</b><br><mark>{excerpt}</mark></blockquote>")
    if not blocks:
        blocks.append("<p class=muted>The stored text reader found no page passage for this document.</p>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} evidence</title><style>body{{max-width:850px;margin:0 auto;padding:30px 20px;font:16px/1.5 system-ui,sans-serif;color:#17211b;background:#fbfaf5}}a{{color:#245c45}}blockquote{{background:white;border-left:4px solid #e9b949;padding:14px;margin:16px 0}}mark{{background:#fff0a8}}.muted{{color:#68736b}}</style></head><body><p><a href="{html.escape(public_path + '/', quote=True)}">← Back to Page 47</a></p><h1>{name}</h1><p>This page shows the captured document passage used by Page 47. The PDF is the primary record.</p><p><a href="{pdf_url}" target="_blank" rel="noreferrer">Open the captured PDF</a></p>{''.join(blocks)}<p>Page 47 does not determine why these changes were made.</p></body></html>"""


def _display(value: object, fallback: str = "Could not determine") -> str:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    text = str(value).strip()
    return text if text else fallback


def _state_text(value: object) -> str:
    return {
        "clearer": "Clearer",
        "unchanged": "Unchanged",
        "less_clear": "Less clear",
        "cannot_determine": "Could not determine",
    }.get(str(value), "Could not determine")


def _source_link(source: object, label: str | None = None) -> str:
    if not isinstance(source, dict):
        return ""
    url = source.get("url")
    captured_at = source.get("captured_at")
    kind = source.get("kind")
    if not isinstance(url, str) or not url.startswith(("https://", "http://", "/")):
        return ""
    if not isinstance(captured_at, str) or not captured_at:
        return ""
    if label is None:
        label = "City's current record" if kind == "api" else "Page 47's captured record"
    return (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noreferrer">'
        f"{html.escape(label)}</a> <span class=muted>({html.escape(captured_at)})</span>"
    )


def _evidence_links(value: object) -> str:
    if not isinstance(value, list):
        return ""
    links: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://", "/")):
            continue
        label = _display(item.get("label"), "Primary record")
        page = item.get("page_number")
        page_text = f" — PDF page {page}" if isinstance(page, int) else ""
        href = f"{url}#page={page}" if isinstance(page, int) else url
        captured_at = _display(item.get("captured_at"))
        links.append(
            f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">'
            f"See {html.escape(label)}{html.escape(page_text)}</a> "
            f'<span class=muted>({html.escape(captured_at)})</span>'
        )
    return " · ".join(links)


def _matter_page(title: str, city: str, data: JSONObject, public_path: str) -> str:
    case = data.get("case")
    if not isinstance(case, dict):
        raise HTTPException(status_code=500, detail="Stored matter record was invalid")
    matter = case.get("matter")
    appearances = case.get("appearances")
    if not isinstance(matter, dict) or not isinstance(appearances, list):
        raise HTTPException(status_code=500, detail="Stored matter record was incomplete")
    current_title = _display(matter.get("current_title"), "Untitled public matter")
    appearance_blocks: list[str] = []
    for appearance in appearances:
        if not isinstance(appearance, dict):
            continue
        attachment_blocks: list[str] = []
        raw_attachments = appearance.get("attachments")
        if isinstance(raw_attachments, list):
            for attachment in raw_attachments:
                if not isinstance(attachment, dict):
                    continue
                attachment_id = attachment.get("attachment_id")
                name = _display(attachment.get("name"), "Unnamed attachment")
                if isinstance(attachment_id, int):
                    attachment_link = f'<a href="{html.escape(_internal_url(public_path, f"/evidence/{city}/attachment/{attachment_id}"), quote=True)}">View captured document</a>'
                else:
                    attachment_link = "Captured document was not available"
                attachment_blocks.append(f"<li>{html.escape(name)} — {attachment_link}</li>")
        attachments_html = (
            "<ul>" + "".join(attachment_blocks) + "</ul>"
            if attachment_blocks
            else "<p class=muted>No attachment was stored for this appearance.</p>"
        )
        pdf_source = _source_link(appearance.get("pdf_source"), "Agenda PDF")
        source = _source_link(appearance.get("source"))
        pages = appearance.get("pdf_evidence_pages")
        page_numbers = [str(page) for page in pages if isinstance(page, int)] if isinstance(pages, list) else []
        page_text = "PDF pages: " + ", ".join(page_numbers) if page_numbers else "PDF section: could not determine"
        source_text = " · ".join(item for item in (source, pdf_source) if item)
        appearance_blocks.append(
            f"<article class=card><h2>{html.escape(_display(appearance.get('title_as_presented'), 'Title not available'))}</h2>"
            f"<p><b>Meeting:</b> {html.escape(_display(appearance.get('event_date')))} · "
            f"<b>Body:</b> {html.escape(_display(appearance.get('body_name')))}</p>"
            f"<p><b>Placement:</b> {html.escape(_display(appearance.get('pdf_placement')))} · "
            f"{html.escape(page_text)}</p><p>{source_text}</p>"
            f"<h3>Attached public documents</h3>{attachments_html}</article>"
        )
    finding = data.get("finding")
    finding_html = ""
    if isinstance(finding, dict):
        finding_id = finding.get("finding_id")
        if isinstance(finding_id, str):
            finding_html = (
                f'<p><a href="{html.escape(_internal_url(public_path, f"/finding/{city}/{finding_id}"), quote=True)}">Read the saved review</a></p>'
            )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — {html.escape(current_title)}</title><style>body{{max-width:1000px;margin:0 auto;padding:30px 20px;font:16px/1.5 system-ui,sans-serif;color:#17211b;background:#fbfaf5}}a{{color:#245c45}}.card{{background:white;border:1px solid #d9dfd8;border-radius:14px;padding:18px;margin:16px 0}}.muted{{color:#68736b}}li{{margin:8px 0}}</style></head><body><p><a href="{html.escape(public_path + '/', quote=True)}">← Back to Page 47</a></p><p class=muted>{html.escape(city)} · Matter {_display(matter.get('matter_id'))}</p><h1>{html.escape(current_title)}</h1><p>The entries below show how this public matter appeared at each recorded meeting. The links identify the source and capture time.</p>{finding_html}{''.join(appearance_blocks)}<p>Page 47 does not determine why these changes were made.</p></body></html>"""


def _finding_page(title: str, city: str, data: JSONObject, public_path: str) -> str:
    decision = data.get("decision")
    brief = data.get("brief")
    if not isinstance(decision, dict):
        raise HTTPException(status_code=500, detail="Stored review decision was invalid")
    accepted = decision.get("accepted")
    accepted_blocks: list[str] = []
    if isinstance(accepted, list):
        for item in accepted:
            if not isinstance(item, dict):
                continue
            text = html.escape(_display(item.get("text"), "The review recorded an observation."))
            links = _evidence_links(item.get("evidence"))
            link_html = links or "<span class=muted>Primary link could not be rendered.</span>"
            accepted_blocks.append(f"<li><p>{text}</p><p>{link_html}</p></li>")
    if not accepted_blocks:
        accepted_blocks.append("<li>No observation survived review with a primary record link.</li>")
    questions: list[str] = []
    raw_questions = brief.get("questions") if isinstance(brief, dict) else None
    if isinstance(raw_questions, list):
        questions = [html.escape(item) for item in raw_questions if isinstance(item, str)]
    questions_html = (
        "<ul>" + "".join(f"<li>{item}</li>" for item in questions) + "</ul>"
        if questions
        else "<p class=muted>No questions were recorded.</p>"
    )
    norm = data.get("norms")
    norm_html = ""
    if isinstance(norm, dict):
        norm_html = f"<p>{html.escape(_display(norm.get('human_timing_sentence')))}</p>"
    heading = (
        _display(brief.get("heading"), "Worth a look")
        if isinstance(brief, dict)
        else "Worth a look"
    )
    limitation = _display(brief.get("limitation")) if isinstance(brief, dict) else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — review</title><style>body{{max-width:850px;margin:0 auto;padding:30px 20px;font:16px/1.5 system-ui,sans-serif;color:#17211b;background:#fbfaf5}}a{{color:#245c45}}section{{background:white;border:1px solid #d9dfd8;border-radius:14px;padding:18px;margin:16px 0}}.state{{font-size:1.25rem;color:#245c45}}.muted{{color:#68736b}}li{{margin:14px 0}}</style></head><body><p><a href="{html.escape(public_path + '/', quote=True)}">← Back to Page 47</a></p><p class=muted>{html.escape(city)} · Matter {_display(data.get('matter_id'))}</p><h1>{html.escape(heading)}</h1><p class=state>Presentation drift: {html.escape(_state_text(decision.get('state')))}</p><p>{html.escape(_display(decision.get('reason')))}</p><section><h2>What the review supports</h2><ol>{''.join(accepted_blocks)}</ol></section><section><h2>What the record normally shows</h2>{norm_html or '<p class=muted>No body comparison was available.</p>'}</section><section><h2>Questions worth asking</h2>{questions_html}</section><section><h2>What Page 47 does not decide</h2><p>{html.escape(limitation or 'Page 47 does not determine why these changes were made.')}</p><p>Page 47 does not determine why these changes were made.</p></section><p>Supported observations: {html.escape(_display(data.get('supported_count')))} · Interpretations not used after review: {html.escape(_display(data.get('rejected_count'), '0'))}</p></body></html>"""


app = create_app()
