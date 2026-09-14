"""FastAPI application for the Page 47 resident and evidence surfaces."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from page47.snapshotter.config import JSONObject
from page47.web import frontend
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

    @app.get("/favicon.svg")
    def favicon() -> Response:
        return Response(
            content=frontend.favicon_svg(),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
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
        return HTMLResponse(
            frontend.evidence_page(settings.title, city, data, settings.public_path)
        )

    @app.get("/matter/{city}/{matter_id}", response_class=HTMLResponse)
    def matter_page(city: str, matter_id: int) -> HTMLResponse:
        try:
            data = service.matter(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return HTMLResponse(frontend.matter_page(settings.title, city, data, settings.public_path))

    def saved_review(city: str, matter_id: int) -> tuple[str, JSONObject]:
        matter_data = service.matter(city, matter_id)
        stored_finding = matter_data.get("finding")
        if not isinstance(stored_finding, dict):
            raise LookupError(f"No saved review was found for matter {matter_id}")
        finding_id = stored_finding.get("finding_id")
        if not isinstance(finding_id, str):
            raise LookupError(f"No saved review was found for matter {matter_id}")
        return finding_id, service.finding(city, finding_id)

    @app.get("/replay/{city}/{matter_id}", response_class=HTMLResponse)
    def replay_page(city: str, matter_id: int) -> HTMLResponse:
        try:
            _, data = saved_review(city, matter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return HTMLResponse(
            frontend.finding_page(settings.title, city, data, settings.public_path, replay=True)
        )

    @app.get("/explore", response_class=HTMLResponse)
    def explore_page() -> HTMLResponse:
        """Open the strongest saved review without requiring an internal ID."""
        priority = {"less_clear": 0, "mixed": 1, "clearer": 2, "unchanged": 3}
        candidates: list[tuple[int, int, str, str]] = []
        for city_index, city in enumerate(settings.cities):
            try:
                payload = service.findings(city.name, 200)
            except (LookupError, ValueError, FileNotFoundError):
                continue
            raw_findings = payload.get("findings")
            if not isinstance(raw_findings, list):
                continue
            for item in raw_findings:
                if not isinstance(item, dict):
                    continue
                finding_id = item.get("finding_id")
                matter_id = item.get("matter_id")
                if not isinstance(finding_id, str) or not isinstance(matter_id, int):
                    continue
                candidates.append(
                    (priority.get(str(item.get("state")), 4), city_index, city.name, finding_id)
                )
        if not candidates:
            return HTMLResponse(
                frontend.captured_review_unavailable_page(settings.title, settings.public_path)
            )
        _, _, city_name, finding_id = sorted(candidates)[0]
        try:
            data = service.finding(city_name, finding_id)
        except LookupError:
            return HTMLResponse(
                frontend.captured_review_unavailable_page(settings.title, settings.public_path)
            )
        return HTMLResponse(
            frontend.finding_page(
                settings.title, city_name, data, settings.public_path, replay=True
            )
        )

    @app.get("/finding/{city}/{finding_id}", response_class=HTMLResponse)
    def finding_page(city: str, finding_id: str) -> HTMLResponse:
        try:
            data = service.finding(city, finding_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(frontend.finding_page(settings.title, city, data, settings.public_path))

    @app.get("/watch", response_class=HTMLResponse)
    def watch_setup_page() -> HTMLResponse:
        return HTMLResponse(
            frontend.watch_setup_page(settings.title, settings.default_city, settings.public_path)
        )

    @app.get("/watch/{watch_id}", response_class=HTMLResponse)
    def watch_page(watch_id: str) -> HTMLResponse:
        try:
            data = service.watch(watch_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return HTMLResponse(frontend.watch_page(settings.title, data, settings.public_path))

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(
            frontend.index_page(settings.title, settings.default_city, settings.public_path)
        )

    return app


app = create_app()
