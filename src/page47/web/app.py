"""Small FastAPI console for browsing the stored public record."""

from __future__ import annotations

import html
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from page47.snapshotter.config import JSONObject, JSONValue
from page47.web.config import load_web_settings
from page47.web.limits import SlidingWindowLimiter
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
    watch_limiter = SlidingWindowLimiter(maximum=10, window_seconds=60)
    investigation_limiter = SlidingWindowLimiter(maximum=3, window_seconds=60)

    def client_key(request: Request) -> str:
        forwarded = request.headers.get("x-real-ip")
        if forwarded is not None and forwarded.strip():
            return forwarded.strip()
        return request.client.host if request.client is not None else "unknown"

    def enforce_limit(request: Request, limiter: SlidingWindowLimiter, scope: str) -> None:
        retry_after = limiter.retry_after(f"{scope}:{client_key(request)}")
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="This operation is temporarily rate limited. Please try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith(("/watch/", "/api/watches")):
            response.headers["Cache-Control"] = "no-store"
        return response

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
    def create_watch(request: WatchRequest, http_request: Request) -> JSONObject:
        enforce_limit(http_request, watch_limiter, "watch")
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

    @app.get("/api/watches/{watch_id}")
    def watch(watch_id: str) -> JSONObject:
        try:
            return service.watch(watch_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/watches/{watch_id}/deactivate")
    def deactivate_watch(watch_id: str) -> JSONObject:
        try:
            return service.deactivate_watch(watch_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/cities/{city}/matters/{matter_id}/investigate")
    def investigate(city: str, matter_id: int, request: Request) -> JSONObject:
        enforce_limit(request, investigation_limiter, "investigate")
        try:
            return service.investigate(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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

    @app.get("/replay/{city}/{matter_id}", response_class=HTMLResponse)
    def replay_page(city: str, matter_id: int) -> HTMLResponse:
        try:
            matter_data = service.matter(city, matter_id)
            stored_finding = matter_data.get("finding")
            if not isinstance(stored_finding, dict):
                raise LookupError(f"No saved review was found for matter {matter_id}")
            finding_id = stored_finding.get("finding_id")
            if not isinstance(finding_id, str):
                raise LookupError(f"No saved review was found for matter {matter_id}")
            data = service.finding(city, finding_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return HTMLResponse(
            _finding_page(settings.title, city, data, settings.public_path, replay=True)
        )

    @app.get("/finding/{city}/{finding_id}", response_class=HTMLResponse)
    def finding_page(city: str, finding_id: str) -> HTMLResponse:
        try:
            data = service.finding(city, finding_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(_finding_page(settings.title, city, data, settings.public_path))

    @app.get("/watch/{watch_id}", response_class=HTMLResponse)
    def watch_page(watch_id: str) -> HTMLResponse:
        try:
            data = service.watch(watch_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(_watch_page(settings.title, data, settings.public_path))

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_index_page(settings.title, settings.default_city, settings.public_path))

    return app


def _internal_url(public_path: str, path: str) -> str:
    if path.startswith(("https://", "http://")):
        return path
    suffix = path if path.startswith("/") else f"/{path}"
    return suffix if public_path in {"", "/"} else f"{public_path}{suffix}"


def _index_page(title: str, default_city: str, public_path: str) -> str:
    safe_title = html.escape(title)
    home_url = html.escape(_internal_url(public_path, "/"), quote=True)
    architecture_url = html.escape(
        "https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.md",
        quote=True,
    )
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — when the packet changes</title>
<style>
:root{color-scheme:light;--ink:#14231b;--muted:#64736a;--paper:#f7f8f3;--green:#174b38;--green-2:#22664b;--mint:#e7f0e8;--gold:#f0be4d;--line:#d6e0d7;--white:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--green-2)}
.hero{background:var(--green);color:white;padding:22px max(24px,calc((100vw - 1180px)/2)) 72px}.nav{display:flex;align-items:center;justify-content:space-between;gap:20px;max-width:1180px;margin:auto}.wordmark{letter-spacing:.16em;font-size:.8rem;font-weight:800}.nav a{color:white;text-decoration:none}.nav-link{opacity:.82;font-size:.92rem}.hero-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:48px;align-items:end;max-width:1180px;margin:70px auto 0}.eyebrow{color:var(--gold);font-size:.78rem;font-weight:800;letter-spacing:.13em;margin:0 0 18px}.hero h1{font-size:clamp(2.7rem,7vw,5.8rem);line-height:.98;letter-spacing:-.055em;margin:0 0 24px;max-width:800px}.hero h1 em{color:#d2e7d4;font-style:normal}.lede{font-size:1.2rem;max-width:680px;color:#e3efe4}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:28px 0 18px}.button{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:12px 18px;background:var(--gold);border:1px solid #d49e2e;color:var(--ink);font-weight:800;text-decoration:none}.button.secondary{background:transparent;border-color:#a8ccb1;color:white}.trust{font-size:.88rem;color:#c6ddc9;margin:0}.hero-note{border:1px solid #638c70;border-radius:22px;padding:24px;background:#0d3d2d}.hero-note strong{display:block;font-size:1.35rem;line-height:1.15;margin:7px 0 10px}.hero-note p{color:#c8ddca;margin:0}.note-mark{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:var(--gold);color:var(--ink);font-weight:900}
main{max-width:1180px;margin:auto;padding:58px 24px 84px}h2{font-size:clamp(1.7rem,3vw,2.5rem);line-height:1.08;letter-spacing:-.03em;margin:0 0 12px}h3{line-height:1.2;margin:9px 0}.section-intro{max-width:650px;color:var(--muted)}.workflow{padding-bottom:58px}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:25px}.step,.card,.watch-panel,.proof-panel{background:var(--white);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 10px 28px #14231b0a}.step-number{color:var(--green-2);font-weight:900;font-size:.8rem;letter-spacing:.12em}.step p{color:var(--muted);margin-bottom:0}.watch-shell{display:grid;grid-template-columns:.85fr 1.15fr;gap:20px;align-items:stretch;margin:8px 0 68px}.watch-panel{padding:30px}.watch-panel.emphasis{background:var(--green);color:white;border-color:var(--green)}.watch-panel.emphasis p,.watch-panel.emphasis .muted{color:#d2e6d5}.watch-panel h2{max-width:430px}.watch-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:18px 0}.field{display:flex;flex-direction:column;gap:6px}.field.wide{grid-column:1/-1}.field span{font-weight:750;font-size:.9rem}.field input,.field select{width:100%;border:1px solid var(--line);border-radius:10px;background:white;padding:11px 13px;font:inherit;color:var(--ink)}button{border:1px solid #d49e2e;border-radius:999px;background:var(--gold);color:var(--ink);padding:12px 18px;font:inherit;font-weight:800;cursor:pointer}.advanced{margin:16px 0}.advanced summary{cursor:pointer;color:var(--green-2);font-weight:750}.body-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.body-list label{background:var(--mint);border-radius:9px;padding:8px 10px;font-size:.9rem}.body-list input{accent-color:var(--green-2)}.form-help{font-size:.88rem;color:var(--muted)}.result{min-height:24px}.result a{font-weight:800}.confirm{margin:-38px 0 68px;background:#eaf4eb;border:1px solid #b8d5bc;border-radius:18px;padding:24px}.confirm h2{color:var(--green)}.confirm-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.confirm-grid div{background:white;border-radius:10px;padding:13px}.confirm-grid strong{display:block;font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.confirm-grid span{display:block;margin-top:4px;font-weight:750}.section-heading{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:18px}.section-heading a{font-weight:750}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.card .tag{display:inline-flex;border-radius:99px;padding:4px 9px;background:var(--mint);color:var(--green-2);font-size:.8rem;font-weight:800}.card p{color:var(--muted)}.card a{font-weight:800}.empty{padding:26px;background:white;border:1px dashed var(--line);border-radius:14px;color:var(--muted)}.review-card{border-top:4px solid var(--gold)}.review-card .review-meta{font-size:.9rem;margin:12px 0}.review-card .review-meta strong{color:var(--ink)}.proof{margin-top:68px}.proof-panel{padding:0;overflow:hidden}.proof-panel summary{cursor:pointer;padding:22px;font-weight:800;font-size:1.08rem}.proof-content{padding:0 22px 22px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.metric{border-left:4px solid var(--gold);background:var(--paper);padding:13px}.metric strong{display:block;font-size:1.45rem}.metric span{color:var(--muted);font-size:.9rem}details.record{margin-top:14px}.record summary{cursor:pointer;color:var(--green-2);font-weight:800}.record-inner{padding-top:16px}footer{max-width:1180px;margin:auto;padding:0 24px 35px;color:var(--muted);font-size:.92rem}footer a{font-weight:750}@media(max-width:800px){.hero-grid,.watch-shell{grid-template-columns:1fr}.hero-grid{margin-top:48px}.steps{grid-template-columns:repeat(2,1fr)}.confirm-grid{grid-template-columns:1fr}.watch-fields{grid-template-columns:1fr}.field.wide{grid-column:auto}}@media(max-width:520px){.steps{grid-template-columns:1fr}.body-list{grid-template-columns:1fr}.hero{padding-bottom:52px}}
</style></head><body>
<header class="hero"><nav class="nav"><a href="__HOME_URL__"><span class="wordmark">PAGE 47</span></a><a class="nav-link" href="#how-it-works">How it works ↓</a></nav><div class="hero-grid"><div><p class="eyebrow">PUBLIC RECORD WATCH</p><h1>City packets change.<br><em>Page 47 watches what you care about.</em></h1><p class="lede">Tell Page 47 your neighbourhood or address. It watches public meeting records in the background and emails you only when a change survives an evidence review.</p><div class="actions"><a class="button" href="#watch">Watch my area</a><a class="button secondary" href="#reviews">See a real review</a></div><p class="trust">Every reported fact links to the public record. Page 47 does not infer intent.</p></div><aside class="hero-note"><div class="note-mark">47</div><strong>While you are away</strong><p>The watch stays active on the server. You do not need to keep this page open.</p></aside></div></header>
<main><!-- __MATTER_LINK_MARKER__ --><section id="how-it-works" class="workflow"><p class="eyebrow">A QUIET CIVIC ASSISTANT</p><h2>Know when the public record deserves another look.</h2><p class="section-intro">Page 47 turns a resident's area into a durable watch: it preserves what the city published, compares later appearances, and makes the evidence easy to inspect.</p><div class="steps"><article class="step"><span class="step-number">01 — WATCH</span><h3>Choose what matters</h3><p>Start with a city and neighbourhood or address.</p></article><article class="step"><span class="step-number">02 — OBSERVE</span><h3>Walk away</h3><p>The scheduled collector keeps checking the public record.</p></article><article class="step"><span class="step-number">03 — REVIEW</span><h3>Evidence meets evidence</h3><p>Separate readers compare presentation and document facts.</p></article><article class="step"><span class="step-number">04 — ACT</span><h3>Ask a better question</h3><p>Open the source and decide what deserves your attention.</p></article></div></section>
<section id="watch" class="watch-shell"><div class="watch-panel emphasis"><p class="eyebrow">START WITH WHAT MATTERS</p><h2>Tell Page 47 where to watch.</h2><p>Choose a city, an area, and where to send a review. Public-body selection is available under advanced options; you do not need to understand the city's internal structure.</p><p><strong>No account. No open browser. Private stop link.</strong></p></div><div class="watch-panel"><h2>Create a watch</h2><form id="watch-form"><div class="watch-fields"><label class="field"><span>City</span><select id="city" required></select></label><label class="field"><span>Email for alerts</span><input id="email" type="email" autocomplete="email" required placeholder="you@example.org"></label><label class="field"><span>Neighbourhood</span><input id="neighbourhood" autocomplete="address-level3" placeholder="Capitol Hill"></label><label class="field"><span>Address <small class="muted">(optional)</small></span><input id="address" autocomplete="street-address" placeholder="123 Main Street, Seattle, WA"></label></div><details class="advanced"><summary>Advanced options — public bodies</summary><p class="form-help">All configured bodies start selected. Narrow this list only if you want a more specific watch.</p><div id="bodies" class="body-list">Loading public bodies…</div></details><button type="submit">Start watching</button><p id="watch-result" class="result muted" aria-live="polite"></p></form></div></section>
<section id="watch-confirmation" class="confirm" hidden><p class="eyebrow">WATCH CREATED</p><h2>Page 47 is watching.</h2><p>You can close this page now. The scheduled collector will keep checking the public record.</p><div class="confirm-grid"><div><strong>City</strong><span id="confirm-city">—</span></div><div><strong>Area</strong><span id="confirm-area">—</span></div><div><strong>Public bodies</strong><span id="confirm-bodies">—</span></div></div><p><a id="confirm-link" href="#">Manage this private watch</a> <span class="muted">· Keep this link private.</span></p></section>
<section id="reviews"><div class="section-heading"><div><p class="eyebrow">REAL STORED REVIEWS</p><h2>See what survived review.</h2><p class="section-intro">These findings come from captured public records. Open one to inspect the evidence, or replay its captured case without calling a live source.</p></div><a href="#record">Browse the record ↓</a></div><div id="findings" class="grid"><div class="empty">Loading saved reviews…</div></div></section>
<section class="proof"><details class="proof-panel"><summary>Proof behind the product</summary><div class="proof-content"><p class="section-intro">Page 47 shows its work: the comparator keeps opposing directions visible, the Skeptic can reject unsupported interpretations, and uncertainty stays explicit.</p><div id="ledger" class="metrics"><div class="empty">Loading evidence ledger…</div></div></div></details><details id="record" class="proof-panel record"><summary>Browse recent public matters</summary><div class="proof-content"><div id="matters" class="grid"><div class="empty">Loading the stored public record…</div></div></div></details></section>
</main><footer>Page 47 reports public records. It does not determine why a change was made or tell you what position to take.<br><a href="https://github.com/Jennycruzy/Page47">Open the source repository</a> · <a href="__ARCHITECTURE_URL__">Architecture</a></footer>
<script>
const defaultCity = __DEFAULT_CITY_JSON__; const publicPath = __PUBLIC_PATH_JSON__;
const citySelect=document.querySelector('#city'); const esc=(v)=>String(v??'').replace(/[&<>"']/g,c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]);
async function json(url){const response=await fetch(url);if(!response.ok)throw new Error(await response.text());return response.json();}
function internal(path){return (publicPath === '/' ? '' : publicPath)+(path.startsWith('/')?path:'/'+path);}
function chosen(){return citySelect.value||defaultCity;}
function stateLabel(value){const labels={clearer:'Presentation became clearer',less_clear:'Presentation became less clear',mixed:'Presentation changed in mixed directions',unchanged:'No meaningful presentation change',cannot_determine:'Page 47 could not determine the direction'};return labels[value]||'Review status unavailable';}
function metric(label,value){return '<div class="metric"><strong>'+esc(value)+'</strong><span>'+esc(label)+'</span></div>';}
async function loadBodies(){const data=await json(internal('/api/cities/'+encodeURIComponent(chosen())+'/bodies'));document.querySelector('#bodies').innerHTML=data.bodies.map(body=>'<label><input type="checkbox" name="body" value="'+esc(body)+'" checked> '+esc(body)+'</label>').join('');}
function selectedBodies(){return [...document.querySelectorAll('input[name="body"]:checked')].map(input=>input.value);}
async function loadRecord(){const city=chosen();const result=await Promise.all([json(internal('/api/cities/'+encodeURIComponent(city)+'/ledger')),json(internal('/api/cities/'+encodeURIComponent(city)+'/matters?limit=40')),json(internal('/api/cities/'+encodeURIComponent(city)+'/findings?limit=40'))]);const ledger=result[0];const matters=result[1];const findings=result[2];
document.querySelector('#ledger').innerHTML=[metric('matters observed',ledger.matters_observed),metric('packet changes recorded',ledger.packet_changes_recorded),metric('became less clear',ledger.became_less_clear),metric('became clearer',ledger.became_clearer),metric('mixed presentation',ledger.mixed_presentation),metric('interpretations rejected',ledger.interpretations_rejected),metric('document readings',ledger.document_readings)].join('');
document.querySelector('#findings').innerHTML=findings.findings.length?findings.findings.map(f=>{const brief=f.brief||{};const decision=f.decision||{};return '<article class="card review-card"><span class="tag">'+esc(stateLabel(f.state))+'</span><h3>'+esc(brief.heading||('Matter '+f.matter_id))+'</h3><p class="review-meta"><strong>'+esc(f.supported_count)+'</strong> supported · <strong>'+esc(f.rejected_count)+'</strong> rejected after review</p><p>'+esc(decision.reason||'The saved review is available.')+'</p><a href="'+internal('/finding/'+encodeURIComponent(city)+'/'+encodeURIComponent(f.finding_id))+'">Read the evidence review →</a><br><a href="'+internal('/replay/'+encodeURIComponent(city)+'/'+f.matter_id)+'">Replay captured case →</a></article>';}).join(''):'<div class="empty">No saved review is available for this city yet.</div>';
document.querySelector('#matters').innerHTML=matters.matters.length?matters.matters.map(m=>'<article class="card"><span class="tag">'+esc(m.placement_note)+'</span><h3>'+esc(m.latest_title||m.current_title||'Untitled public matter')+'</h3><p>'+esc(m.body_name)+' · '+esc(m.latest_event_date)+' · matter '+esc(m.matter_id)+'</p><a href="'+internal('/matter/'+encodeURIComponent(city)+'/'+m.matter_id)+'">Open recorded history →</a></article>').join(''):'<div class="empty">No stored matters were found.</div>';}
async function init(){const data=await json(internal('/api/cities'));citySelect.innerHTML=data.cities.map(c=>'<option value="'+esc(c.name)+'">'+esc(c.name)+'</option>').join('');citySelect.value=defaultCity;await loadBodies();await loadRecord();}
citySelect.onchange=async()=>{try{await loadBodies();await loadRecord();}catch(error){document.querySelector('#watch-result').textContent='Could not load this city: '+esc(error.message);}};
document.querySelector('#watch-form').onsubmit=async(event)=>{event.preventDefault();const result=document.querySelector('#watch-result');const bodies=selectedBodies();const address=document.querySelector('#address').value.trim()||null;const neighbourhood=document.querySelector('#neighbourhood').value.trim()||null;if(!bodies.length){result.textContent='Select at least one public body under Advanced options.';return;}if(!address&&!neighbourhood){result.textContent='Enter a neighbourhood or address so Page 47 knows what to watch.';return;}result.textContent='Saving your watch…';try{const response=await fetch(internal('/api/watches'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({city:chosen(),bodies,address,neighbourhood,email:document.querySelector('#email').value.trim()})});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||'The watch could not be saved.');const link=internal(payload.manage_path||('/watch/'+payload.watch_id));result.innerHTML=esc(payload.message)+' <a href="'+esc(link)+'">Manage this private watch</a>';document.querySelector('#confirm-city').textContent=chosen();document.querySelector('#confirm-area').textContent=neighbourhood||address||'Selected area';document.querySelector('#confirm-bodies').textContent=bodies.length+' selected';const confirmLink=document.querySelector('#confirm-link');confirmLink.href=link;document.querySelector('#watch-confirmation').hidden=false;document.querySelector('#watch-confirmation').scrollIntoView({behavior:'smooth',block:'center'});}catch(error){result.textContent='Could not save the watch: '+esc(error.message);}};
init().catch(error=>{document.querySelector('#findings').innerHTML='<div class="empty">Could not load the public record: '+esc(error.message)+'</div>';});
</script></body></html>"""
    return (
        template.replace("__TITLE__", safe_title)
        .replace("__HOME_URL__", home_url)
        .replace("__ARCHITECTURE_URL__", architecture_url)
        .replace("__DEFAULT_CITY_JSON__", json.dumps(default_city))
        .replace("__PUBLIC_PATH_JSON__", json.dumps(public_path))
        .replace(
            "__MATTER_LINK_MARKER__",
            "internal(" + chr(96) + "/matter/" + chr(96) + ")",
        )
    )


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
    home_url = html.escape(_internal_url(public_path, "/"), quote=True)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} evidence</title><style>body{{max-width:850px;margin:0 auto;padding:30px 20px;font:16px/1.5 system-ui,sans-serif;color:#17211b;background:#fbfaf5}}a{{color:#245c45}}blockquote{{background:white;border-left:4px solid #e9b949;padding:14px;margin:16px 0}}mark{{background:#fff0a8}}.muted{{color:#68736b}}</style></head><body><p><a href="{home_url}">← Back to Page 47</a></p><h1>{name}</h1><p>This page shows the captured document passage used by Page 47. The PDF is the primary record.</p><p><a href="{pdf_url}" target="_blank" rel="noreferrer">Open the captured PDF</a></p>{''.join(blocks)}<p>Page 47 does not determine why these changes were made.</p></body></html>"""


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
        "mixed": "Mixed directions",
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
        observed = source.get("observed_by_page47") is True
        label = (
            "Page 47's captured record"
            if observed or kind == "snapshot"
            else "City's current record"
        )
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
    home_url = html.escape(_internal_url(public_path, "/"), quote=True)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — {html.escape(current_title)}</title><style>body{{max-width:1000px;margin:0 auto;padding:30px 20px;font:16px/1.5 system-ui,sans-serif;color:#17211b;background:#fbfaf5}}a{{color:#245c45}}.card{{background:white;border:1px solid #d9dfd8;border-radius:14px;padding:18px;margin:16px 0}}.muted{{color:#68736b}}li{{margin:8px 0}}</style></head><body><p><a href="{home_url}">← Back to Page 47</a></p><p class=muted>{html.escape(city)} · Matter {_display(matter.get('matter_id'))}</p><h1>{html.escape(current_title)}</h1><p>The entries below show how this public matter appeared at each recorded meeting. The links identify the source and capture time.</p>{finding_html}{''.join(appearance_blocks)}<p>Page 47 does not determine why these changes were made.</p></body></html>"""


def _finding_page(
    title: str,
    city: str,
    data: JSONObject,
    public_path: str,
    replay: bool = False,
) -> str:
    decision = data.get("decision")
    brief = data.get("brief")
    if not isinstance(decision, dict):
        raise HTTPException(status_code=500, detail="Stored review decision was invalid")
    if not isinstance(brief, dict):
        brief = {}
    case = data.get("case")
    case_matter = case.get("matter") if isinstance(case, dict) else None
    raw_appearances = case.get("appearances") if isinstance(case, dict) else None
    appearances = raw_appearances if isinstance(raw_appearances, list) else []
    drift = data.get("drift")
    raw_comparisons = drift.get("comparisons") if isinstance(drift, dict) else None
    comparisons = raw_comparisons if isinstance(raw_comparisons, list) else []
    latest = comparisons[-1] if comparisons and isinstance(comparisons[-1], dict) else {}
    raw_drift_observations = latest.get("observations")
    drift_observations = (
        raw_drift_observations if isinstance(raw_drift_observations, list) else []
    )
    raw_accepted = decision.get("accepted")
    accepted = raw_accepted if isinstance(raw_accepted, list) else []
    raw_rejected = decision.get("rejected")
    rejected = raw_rejected if isinstance(raw_rejected, list) else []

    def observation_with_prefix(prefix: str) -> dict[str, JSONValue] | None:
        for item in drift_observations:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if isinstance(key, str) and key.startswith(prefix):
                return item
        return None

    def appearance_by_id(value: object) -> dict[str, JSONValue] | None:
        for item in appearances:
            if not isinstance(item, dict):
                continue
            if item.get("event_item_id") == value:
                return item
        return None

    previous = appearance_by_id(latest.get("previous_event_item_id"))
    current = appearance_by_id(latest.get("current_event_item_id"))

    def value_from(appearance: dict[str, JSONValue] | None, key: str) -> str:
        if appearance is None:
            return "Could not determine"
        raw = appearance.get(key)
        return _display(raw)

    def placement_label(value: str) -> str:
        return {
            "regular": "Regular agenda",
            "consent": "Consent calendar",
        }.get(value, value)

    def direction_label(value: object) -> str:
        return {
            "clearer": "Clearer",
            "less_clear": "Less representative / less visible",
            "neutral": "No directional change",
        }.get(str(value), "Could not determine")

    def direction_class(value: object) -> str:
        return {
            "clearer": "clearer",
            "less_clear": "less-clear",
            "neutral": "neutral",
        }.get(str(value), "unknown")

    def origin_label(value: object, fallback: str) -> str:
        return {
            "observed_by_page47": "Observed by Page 47",
            "reconstructed_from_public_record": "Reconstructed from public record",
            "current_public_record": "Current public record",
            "cannot_determine": "Cannot determine",
        }.get(str(value), fallback)

    def evidence_markup(value: object, origin: str) -> str:
        if not isinstance(value, list):
            return '<span class="muted">No primary evidence link was retained.</span>'
        links: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith(
                ("https://", "http://", "/")
            ):
                continue
            page = item.get("page_number")
            page_number = page if isinstance(page, int) and not isinstance(page, bool) else None
            href = f"{url}#page={page_number}" if page_number is not None else url
            page_text = f" · PDF page {page_number}" if page_number is not None else ""
            label = _display(item.get("label"), "Primary record")
            captured_at = _display(item.get("captured_at"), "capture time unavailable")
            saved_origin = origin_label(item.get("origin"), origin)
            links.append(
                f'<div class="evidence-link"><a href="{html.escape(href, quote=True)}" '
                f'target="_blank" rel="noreferrer">Open {html.escape(label)}'
                f'{html.escape(page_text)}</a><span class="badge">{html.escape(saved_origin)}</span>'
                f'<span class="muted">{html.escape(captured_at)}</span></div>'
            )
        return "".join(links) or '<span class="muted">No primary evidence link was retained.</span>'

    def dimension_markup(
        name: str,
        earlier: str,
        later: str,
        direction: object,
        evidence: object,
        origin: str,
        note: str = "",
    ) -> str:
        note_html = f'<p class="muted note">{html.escape(note)}</p>' if note else ""
        return (
            f'<article class="dimension"><div class="dimension-heading"><h3>'
            f'{html.escape(name)}</h3><span class="direction {direction_class(direction)}">'
            f"{html.escape(direction_label(direction))}</span></div>"
            f'<div class="comparison-values"><div><span>Earlier appearance</span><strong>'
            f"{html.escape(earlier)}</strong></div><div><span>Later appearance</span><strong>"
            f"{html.escape(later)}</strong></div></div>{note_html}"
            f'<div class="evidence">{evidence_markup(evidence, origin)}</div></article>'
        )

    title_observation = observation_with_prefix("title")
    placement_observation = observation_with_prefix("agenda_placement")
    title_direction = title_observation.get("direction") if title_observation else "neutral"
    placement_direction = (
        placement_observation.get("direction") if placement_observation else "neutral"
    )
    title_evidence = title_observation.get("evidence") if title_observation else None
    placement_evidence = placement_observation.get("evidence") if placement_observation else None
    title_note = (
        ""
        if title_observation
        else "A comparable title was not available for the latest pair."
    )
    placement_note = (
        ""
        if placement_observation
        else "A supported agenda placement was not available for the latest pair."
    )
    dimensions = "".join(
        (
            dimension_markup(
                "Title",
                value_from(previous, "title_as_presented"),
                value_from(current, "title_as_presented"),
                title_direction,
                title_evidence,
                "Reconstructed from public record",
                title_note,
            ),
            dimension_markup(
                "Agenda placement",
                placement_label(value_from(previous, "pdf_placement")),
                placement_label(value_from(current, "pdf_placement")),
                placement_direction,
                placement_evidence,
                "Reconstructed from public record",
                placement_note,
            ),
        )
    )

    substance_items: list[dict[str, JSONValue]] = []
    for accepted_item in accepted:
        if not isinstance(accepted_item, dict):
            continue
        observation_id = accepted_item.get("observation_id")
        if isinstance(observation_id, str) and observation_id.startswith("substance:"):
            substance_items.append(accepted_item)
    substance_blocks: list[str] = []
    for item in substance_items:
        substance_blocks.append(
            f'<li><p>{html.escape(_display(item.get("text"), "Recorded document change."))}</p>'
            f'<div class="evidence">{evidence_markup(item.get("evidence"), "Observed by Page 47")}</div></li>'
        )
    substance_content = (
        "<ul>" + "".join(substance_blocks) + "</ul>"
        if substance_blocks
        else '<p class="muted">No comparable provision change survived the evidence review.</p>'
    )
    dimensions += (
        '<article class="dimension"><div class="dimension-heading"><h3>Document substance'
        '</h3><span class="direction neutral">Evidence detail</span></div>'
        '<p class="note">Only captured document pages are used for this section.</p>'
        f"{substance_content}</article>"
    )
    dimensions += (
        '<article class="dimension"><div class="dimension-heading"><h3>Document timing</h3>'
        '<span class="direction unknown">Insufficient evidence</span></div>'
        '<div class="comparison-values"><div><span>Status</span><strong>Unavailable</strong>'
        '</div><div><span>Reason</span><strong>City timestamps do not prove public visibility.'
        '</strong></div></div><p class="muted note">Page 47 does not use ordinary last-modified'
        ' values as directional evidence.</p></article>'
    )

    raw_lines = brief.get("lines")
    brief_lines = raw_lines if isinstance(raw_lines, list) else []
    know_blocks: list[str] = []
    for brief_item in brief_lines:
        if not isinstance(brief_item, dict):
            continue
        know_blocks.append(
            f'<li><p>{html.escape(_display(brief_item.get("text"), "Supported observation."))}</p>'
            f'<div class="evidence">{evidence_markup(brief_item.get("evidence"), "Primary record")}</div></li>'
        )
    know_html = (
        "<ul>" + "".join(know_blocks) + "</ul>"
        if know_blocks
        else '<p class="muted">No observation survived review with a resident-facing evidence link.</p>'
    )

    timeline: list[tuple[str, str, str, int | None]] = []

    def add_timeline(value: object, origin: str) -> None:
        if not isinstance(value, list):
            return
        for item in value:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            captured_at = item.get("captured_at")
            if not isinstance(url, str) or not url.startswith(("https://", "http://", "/")):
                continue
            if not isinstance(captured_at, str) or not captured_at:
                continue
            page = item.get("page_number")
            page_number = page if isinstance(page, int) and not isinstance(page, bool) else None
            marker = (url, captured_at, page_number)
            if not any(existing[0] == marker[0] and existing[1] == marker[1] and existing[3] == marker[2] for existing in timeline):
                timeline.append(
                    (url, captured_at, origin_label(item.get("origin"), origin), page_number)
                )

    if title_observation:
        add_timeline(title_observation.get("evidence"), "Reconstructed from public record")
    if placement_observation:
        add_timeline(placement_observation.get("evidence"), "Reconstructed from public record")
    for item in substance_items:
        add_timeline(item.get("evidence"), "Observed by Page 47")
    timeline_blocks: list[str] = []
    for url, captured_at, origin, page_number in sorted(timeline, key=lambda item: item[1]):
        page_text = f" · PDF page {page_number}" if page_number is not None else ""
        href = f"{url}#page={page_number}" if page_number is not None else url
        timeline_blocks.append(
            f'<li><span class="badge">{html.escape(origin)}</span><strong>'
            f"{html.escape(captured_at)}</strong><span>{html.escape(page_text or 'Primary record')}</span>"
            f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">'
            "Open evidence →</a></li>"
        )
    timeline_html = (
        '<ol class="timeline">' + "".join(timeline_blocks) + "</ol>"
        if timeline_blocks
        else '<p class="muted">No evidence timeline was retained for this finding.</p>'
    )

    rejected_blocks: list[str] = []
    for rejected_item in rejected:
        if not isinstance(rejected_item, dict):
            continue
        rejected_blocks.append(
            f'<article class="rejection"><h3>Rejected interpretation</h3>'
            f'<p class="rejection-id">{html.escape(_display(rejected_item.get("observation_id")))}</p>'
            f'<p>{html.escape(_display(rejected_item.get("reason"), "The supplied record did not support this interpretation."))}</p></article>'
        )
    rejected_html = (
        "".join(rejected_blocks)
        if rejected_blocks
        else '<p class="muted">No rejected interpretation was recorded for this review.</p>'
    )
    accepted_count = len(accepted)
    rejected_count = len(rejected)
    investigated_count = accepted_count + rejected_count
    state = decision.get("state")
    heading = {
        "clearer": "This matter became more clearly presented",
        "less_clear": "This matter became less clearly presented",
        "mixed": "This matter changed in mixed directions",
        "unchanged": "This matter did not show a meaningful presentation change",
        "cannot_determine": "Page 47 could not determine the direction",
    }.get(str(state), "Page 47 review")
    explanation = _display(
        decision.get("reason"),
        "The saved public record did not support a stronger conclusion.",
    )
    matter_title = (
        _display(case_matter.get("current_title"), "Public matter")
        if isinstance(case_matter, dict)
        else "Public matter"
    )
    norm = data.get("norms")
    norm_sentence = (
        _display(norm.get("human_timing_sentence"))
        if isinstance(norm, dict) and norm.get("human_timing_sentence")
        else "No comparable body-level context was available."
    )
    limitation = _display(
        brief.get("limitation"),
        "Page 47 does not determine why these changes were made.",
    )
    raw_questions = brief.get("questions")
    questions = [
        item for item in raw_questions if isinstance(item, str)
    ] if isinstance(raw_questions, list) else []
    questions_html = (
        "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in questions) + "</ul>"
        if questions
        else '<p class="muted">No questions were recorded.</p>'
    )
    home_url = html.escape(_internal_url(public_path, "/"), quote=True)
    replay_banner = (
        '<p class="replay-banner"><strong>Captured-case replay</strong> · '
        "This review uses stored public records, not a live event.</p>"
        if replay
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — finding</title><style>
body{{margin:0;background:#f7f8f3;color:#14231b;font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:30px 22px 70px}}a{{color:#22664b}}.back{{font-weight:750}}.eyebrow{{color:#22664b;font-size:.78rem;font-weight:850;letter-spacing:.13em;margin:30px 0 12px}}h1,h2,h3{{line-height:1.15;letter-spacing:-.02em}}h1{{font-size:clamp(2.2rem,5vw,4.3rem);max-width:800px;margin:0 0 18px}}h2{{font-size:1.7rem;margin:0 0 10px}}h3{{margin:0 0 9px}}.matter{{color:#64736a;margin:0 0 24px}}.lead{{font-size:1.15rem;max-width:760px}}.state{{display:inline-flex;border-radius:99px;background:#e7f0e8;color:#174b38;padding:7px 12px;font-weight:850}}.replay-banner{{background:#fff1c9;border:1px solid #e2b85b;border-radius:12px;padding:12px 15px;margin:18px 0;font-size:.92rem}}.surface{{background:white;border:1px solid #d6e0d7;border-radius:18px;padding:24px;margin:20px 0;box-shadow:0 10px 28px #14231b0a}}.surface h2{{margin-top:0}}.dimensions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.dimension{{background:#fbfcf8;border:1px solid #d6e0d7;border-radius:14px;padding:17px}}.dimension-heading{{display:flex;justify-content:space-between;align-items:start;gap:12px;margin-bottom:14px}}.dimension-heading h3{{font-size:1.1rem}}.direction{{display:inline-flex;border-radius:99px;padding:4px 8px;font-size:.76rem;font-weight:850;white-space:nowrap}}.direction.less-clear{{background:#fff0e0;color:#8a4a11}}.direction.clearer{{background:#e2f2e5;color:#1b6541}}.direction.neutral{{background:#edf0ed;color:#536058}}.direction.unknown{{background:#f0eee7;color:#6c5a24}}.comparison-values{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.comparison-values div{{background:white;border-radius:9px;padding:11px}}.comparison-values span{{display:block;color:#64736a;font-size:.78rem;font-weight:750;text-transform:uppercase;letter-spacing:.05em}}.comparison-values strong{{display:block;margin-top:4px;font-size:.98rem}}.note{{font-size:.9rem}}.evidence{{margin-top:13px;display:grid;gap:7px}}.evidence-link{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:.9rem}}.evidence-link a{{font-weight:750}}.badge{{display:inline-flex;border-radius:99px;background:#e7f0e8;color:#22664b;padding:3px 7px;font-size:.72rem;font-weight:850}}.muted{{color:#64736a}}.facts ul,.review ul{{padding-left:22px}}li{{margin:13px 0}}.timeline{{list-style:none;padding:0;margin:0;border-left:2px solid #d6e0d7}}.timeline li{{display:grid;grid-template-columns:max-content max-content 1fr max-content;gap:9px;align-items:center;margin:0;padding:13px 0 13px 15px;position:relative}}.timeline li:before{{content:"";width:8px;height:8px;background:#f0be4d;border:3px solid #f7f8f3;border-radius:50%;position:absolute;left:-7px}}.timeline strong{{font-size:.9rem}}.timeline a{{font-weight:750;font-size:.9rem}}.review-grid{{display:grid;grid-template-columns:2fr 1fr;gap:14px}}.review-counts{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:15px 0}}.count{{padding:12px;background:#f7f8f3;border-radius:9px}}.count strong{{display:block;font-size:1.4rem}}.count span{{color:#64736a;font-size:.82rem}}.rejection{{background:#fff8ef;border-left:4px solid #e3a446;border-radius:9px;padding:13px 15px;margin:12px 0}}.rejection h3{{font-size:1rem}}.rejection p{{margin:4px 0}}.rejection-id{{font: .82rem ui-monospace,SFMono-Regular,Menlo,monospace;color:#64736a}}.boundary{{background:#f0f3ee;border-radius:12px;padding:16px}}footer{{max-width:1050px;margin:auto;padding:0 22px 32px;color:#64736a}}@media(max-width:780px){{.dimensions,.review-grid{{grid-template-columns:1fr}}.timeline li{{grid-template-columns:1fr;gap:3px}}.review-counts{{grid-template-columns:1fr 1fr}}.comparison-values{{grid-template-columns:1fr}}}}
</style></head><body><main><p><a class="back" href="{home_url}">← Back to Page 47</a></p>{replay_banner}<p class="eyebrow">EVIDENCE REVIEW · {html.escape(city)}</p><p class="matter">{html.escape(matter_title)} · matter {html.escape(_display(data.get("matter_id")))}</p><h1>{html.escape(heading)}</h1><p class="state">{html.escape(_state_text(state))}</p><p class="lead">{html.escape(explanation)}</p>
<section class="surface"><h2>What changed</h2><p class="muted">Page 47 keeps presentation dimensions separate so a change in one dimension cannot cancel a change in another.</p><div class="dimensions">{dimensions}</div></section>
<section class="surface facts"><h2>What Page 47 knows</h2>{know_html}</section>
<section class="surface"><h2>Evidence timeline</h2><p class="muted">Each entry identifies the evidence position. A historical comparison may be reconstructed from records that are available now; captured document pages are marked separately.</p>{timeline_html}</section>
<section class="surface review"><h2>Evidence review</h2><p class="muted">The Skeptic reviews the branch results before publication.</p><div class="review-counts"><div class="count"><strong>{accepted_count}</strong><span>supported</span></div><div class="count"><strong>{rejected_count}</strong><span>rejected</span></div><div class="count"><strong>{html.escape("Yes" if str(state) == "cannot_determine" else "No")}</strong><span>insufficient evidence</span></div></div>{rejected_html}</section>
<section class="surface"><h2>What the public record normally shows</h2><p>{html.escape(norm_sentence)}</p></section>
<section class="surface"><h2>Questions worth asking</h2>{questions_html}</section>
<section class="surface boundary"><h2>What Page 47 cannot establish</h2><p>{html.escape(limitation)}</p><p class="muted">Page 47 reports public records. It does not determine motive, legality, or a political position.</p></section></main><footer>Review observations investigated: {investigated_count} · <a href="https://github.com/Jennycruzy/Page47">Source repository</a></footer></body></html>"""


def _watch_page(title: str, data: JSONObject, public_path: str) -> str:
    raw_watch_id = _display(data.get("watch_id"))
    city = _display(data.get("city"))
    bodies = data.get("bodies")
    if not isinstance(bodies, list):
        raise HTTPException(status_code=500, detail="Stored watch bodies were invalid")
    body_names = [html.escape(str(item)) for item in bodies]
    neighbourhood = _display(data.get("neighbourhood"), "")
    address = _display(data.get("address"), "")
    area = neighbourhood or address or "Could not determine"
    active = data.get("active") is True
    status = "Active" if active else "Stopped"
    created_at = _display(data.get("created_at"), "Not recorded")
    last_check = _display(data.get("last_successful_check"), "Not recorded")
    delivered = _display(data.get("reviews_delivered"), "0")
    home_url = html.escape(_internal_url(public_path, "/"), quote=True)
    endpoint_json = json.dumps(
        _internal_url(public_path, f"/api/watches/{raw_watch_id}/deactivate")
    )
    stop_action = (
        f'<button id="stop-watch" type="button">Stop this watch</button>'
        '<p id="watch-result" class="muted" aria-live="polite"></p>'
        f"<script>const stopEndpoint={endpoint_json};"
        'document.querySelector("#stop-watch").onclick=async()=>{'
        'const result=document.querySelector("#watch-result");'
        'result.textContent="Stopping this watch…";'
        'try{const response=await fetch(stopEndpoint,{method:"POST"});'
        'const payload=await response.json();'
        'if(!response.ok)throw new Error(payload.detail||"Could not stop this watch.");'
        'result.textContent=payload.message;'
        'document.querySelector("#stop-watch").remove();}'
        'catch(error){result.textContent=error.message;}};</script>'
        if active
        else '<p><b>This watch is stopped.</b> No further review emails will be sent.</p>'
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — watch</title><style>
body{{margin:0;background:#f7f8f3;color:#14231b;font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:820px;margin:auto;padding:30px 22px 70px}}a{{color:#22664b}}.back{{font-weight:750}}.eyebrow{{color:#22664b;font-size:.78rem;font-weight:850;letter-spacing:.13em;margin:32px 0 12px}}h1,h2{{line-height:1.1;letter-spacing:-.03em}}h1{{font-size:clamp(2.3rem,6vw,4.6rem);margin:0 0 14px}}h2{{font-size:1.45rem;margin:0 0 16px}}.lede{{font-size:1.13rem;color:#64736a;max-width:650px}}.status{{display:inline-flex;border-radius:99px;padding:7px 12px;background:#e7f0e8;color:#174b38;font-weight:850}}.status.stopped{{background:#eceeeb;color:#536058}}section{{background:white;border:1px solid #d6e0d7;border-radius:18px;padding:24px;margin:18px 0;box-shadow:0 10px 28px #14231b0a}}.facts{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.fact{{background:#f7f8f3;border-radius:10px;padding:14px}}.fact strong{{display:block;font-size:.78rem;color:#64736a;text-transform:uppercase;letter-spacing:.06em}}.fact span{{display:block;margin-top:4px;font-weight:750}}.bodies{{display:flex;gap:8px;flex-wrap:wrap}}.body{{background:#e7f0e8;color:#22664b;border-radius:99px;padding:6px 10px;font-size:.88rem;font-weight:750}}button{{border:1px solid #d49e2e;border-radius:999px;background:#f0be4d;color:#14231b;padding:12px 18px;font:inherit;font-weight:850;cursor:pointer}}.muted{{color:#64736a}}footer{{max-width:820px;margin:auto;padding:0 22px 32px;color:#64736a;font-size:.92rem}}@media(max-width:600px){{.facts{{grid-template-columns:1fr}}}}
</style></head><body><main><p><a class="back" href="{home_url}">← Back to Page 47</a></p><p class="eyebrow">PRIVATE WATCH</p><h1>Page 47 is watching.</h1><p class="lede">This watch lives on the server. You do not need to keep this page open. When a supported change survives review, Page 47 can send an evidence-linked alert.</p><p class="status{" stopped" if not active else ""}">{status}</p><section><h2>Watch details</h2><div class="facts"><div class="fact"><strong>City</strong><span>{html.escape(city)}</span></div><div class="fact"><strong>Area</strong><span>{html.escape(area)}</span></div><div class="fact"><strong>Created</strong><span>{html.escape(created_at)}</span></div><div class="fact"><strong>Last successful collector check</strong><span>{html.escape(last_check)}</span></div><div class="fact"><strong>Reviews delivered</strong><span>{html.escape(delivered)}</span></div><div class="fact"><strong>Watch status</strong><span>{status}</span></div></div></section><section><h2>Public bodies monitored</h2><div class="bodies">{"".join(f'<span class="body">{item}</span>' for item in body_names) or '<span class="muted">No public bodies recorded.</span>'}</div></section><section><h2>Manage this watch</h2><p class="muted">Keep this private link private. It is the control for this watch.</p>{stop_action}</section></main><footer>Page 47 reports public records. It does not determine why a change was made or tell you what position to take.</footer></body></html>"""


app = create_app()
