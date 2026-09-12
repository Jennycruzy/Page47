"""Public-facing presentation layer for Page 47.

The application routes and record service live in :mod:`page47.web.app` and
:mod:`page47.web.service`. This module keeps the resident-facing surfaces
together so the landing page, watch flow, and evidence pages share one visual
system instead of looking like separate tools.
"""

from __future__ import annotations

import html
import json

from page47.snapshotter.config import JSONObject, JSONValue

_SITE_CSS = r"""
:root {
  color-scheme: light;
  --ink: #17372d;
  --ink-strong: #0d281f;
  --forest: #164b3a;
  --forest-deep: #0d3428;
  --moss: #2f7b5b;
  --mint: #e5f0e8;
  --lime: #c9ef72;
  --coral: #e97b5b;
  --cream: #f5f2ea;
  --paper: #fcfbf8;
  --warm: #fff4d7;
  --line: #dce1d9;
  --line-dark: #426d5a;
  --muted: #6c7771;
  --white: #ffffff;
  --danger: #a34832;
  --shadow-sm: 0 8px 24px rgba(18, 49, 38, .06);
  --shadow-md: 0 18px 48px rgba(18, 49, 38, .1);
  --radius-sm: 12px;
  --radius-md: 20px;
  --radius-lg: 30px;
  --sans: "Manrope", "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --mono: "IBM Plex Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.6;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}
::selection { background: var(--lime); color: var(--ink-strong); }
a { color: var(--moss); text-underline-offset: 3px; }
a:hover { color: var(--ink-strong); }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible,
summary:focus-visible { outline: 3px solid var(--coral); outline-offset: 4px; }
button, input, select { font: inherit; }
button { cursor: pointer; }

.site-header {
  position: relative;
  overflow: hidden;
  background: var(--forest-deep);
  color: var(--white);
}
.site-header::before {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 82% 0%, rgba(201, 239, 114, .14), transparent 31%),
    linear-gradient(115deg, transparent 0 70%, rgba(255,255,255,.035) 70% 70.2%, transparent 70.2% 100%);
  content: "";
  pointer-events: none;
}
.site-nav, .hero-wrap, .site-main, .site-footer {
  width: min(1180px, calc(100% - 48px));
  margin: 0 auto;
}
.site-nav {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 78px;
  gap: 24px;
  border-bottom: 1px solid rgba(211, 234, 213, .16);
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: var(--white);
  font-family: var(--mono);
  font-size: .76rem;
  font-weight: 500;
  letter-spacing: .12em;
  text-decoration: none;
  text-transform: uppercase;
}
.brand-mark {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid rgba(201, 239, 114, .75);
  border-radius: 50%;
  color: var(--lime);
  font-size: .68rem;
  letter-spacing: -.08em;
}
.nav-links { display: flex; align-items: center; gap: 28px; }
.nav-links a {
  color: rgba(255,255,255,.72);
  font-size: .84rem;
  text-decoration: none;
}
.nav-links a:hover { color: var(--white); }
.nav-cta {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 15px;
  border: 1px solid rgba(201, 239, 114, .62);
  border-radius: 99px;
  color: var(--lime) !important;
  font-weight: 800;
}

.hero-wrap { position: relative; z-index: 1; padding: 92px 0 48px; }
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(340px, .9fr);
  align-items: center;
  gap: clamp(48px, 8vw, 118px);
}
.kicker {
  margin: 0 0 18px;
  color: var(--moss);
  font-family: var(--mono);
  font-size: .7rem;
  font-weight: 500;
  letter-spacing: .15em;
  line-height: 1.4;
  text-transform: uppercase;
}
.site-header .kicker { color: var(--lime); }
.display {
  max-width: 750px;
  margin: 0;
  color: var(--white);
  font-size: clamp(3rem, 6vw, 5.9rem);
  font-weight: 700;
  letter-spacing: -.075em;
  line-height: .98;
}
.display em { color: var(--lime); font-style: normal; }
.hero-lede {
  max-width: 625px;
  margin: 27px 0 0;
  color: rgba(235, 245, 235, .76);
  font-size: clamp(1.04rem, 1.8vw, 1.23rem);
  line-height: 1.65;
}
.button-row { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 32px; }
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 46px;
  padding: 0 19px;
  border: 1px solid transparent;
  border-radius: 99px;
  background: var(--lime);
  color: var(--ink-strong);
  font-size: .88rem;
  font-weight: 800;
  text-decoration: none;
  transition: transform .2s ease, background .2s ease, border-color .2s ease;
}
.button:hover { background: #d9fa8b; color: var(--ink-strong); transform: translateY(-2px); }
.button--quiet {
  border-color: rgba(211, 234, 213, .35);
  background: transparent;
  color: var(--white);
}
.button--quiet:hover { border-color: rgba(211,234,213,.8); background: rgba(255,255,255,.08); color: var(--white); }
.trust-line { margin: 17px 0 0; color: rgba(235,245,235,.56); font-size: .79rem; }

.hero-art { position: relative; min-height: 440px; }
.hero-art::before {
  position: absolute;
  top: 11%;
  right: -7%;
  width: 240px;
  height: 240px;
  border: 1px solid rgba(201,239,114,.23);
  border-radius: 50%;
  content: "";
}
.hero-art::after {
  position: absolute;
  right: 13%;
  bottom: 3%;
  width: 86px;
  height: 86px;
  border: 1px solid rgba(233,123,91,.58);
  border-radius: 50%;
  content: "";
}
.watch-card {
  position: absolute;
  z-index: 1;
  top: 9%;
  right: 2%;
  width: min(100%, 390px);
  padding: 23px;
  border: 1px solid rgba(211,234,213,.22);
  border-radius: var(--radius-md);
  background: rgba(18, 67, 51, .87);
  box-shadow: 0 26px 70px rgba(0,0,0,.2);
  backdrop-filter: blur(12px);
  animation: rise-in .8s cubic-bezier(.2,.8,.2,1) both;
}
.watch-card::before { position: absolute; inset: 10px; border: 1px solid rgba(201,239,114,.08); border-radius: 14px; content: ""; pointer-events: none; }
.watch-card-top, .card-meta, .review-meta, .fact-label, .timeline-label {
  font-family: var(--mono);
  font-size: .66rem;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.watch-card-top { display: flex; justify-content: space-between; color: rgba(235,245,235,.6); }
.live-dot { color: var(--lime); }
.live-dot::before { display: inline-block; width: 6px; height: 6px; margin: 0 7px 1px 0; border-radius: 50%; background: var(--lime); content: ""; box-shadow: 0 0 0 4px rgba(201,239,114,.12); animation: soft-pulse 2s ease-in-out infinite; }
.watch-card h2 { max-width: 300px; margin: 46px 0 8px; color: var(--white); font-size: 2.1rem; letter-spacing: -.055em; line-height: 1.03; }
.watch-card > p { margin: 0; color: rgba(235,245,235,.67); font-size: .9rem; }
.watch-rail { display: grid; gap: 0; margin-top: 30px; }
.watch-step { display: grid; grid-template-columns: 25px 1fr auto; gap: 10px; align-items: center; min-height: 48px; border-top: 1px solid rgba(211,234,213,.14); color: rgba(235,245,235,.76); font-size: .83rem; }
.watch-step span:first-child { color: var(--lime); font-family: var(--mono); font-size: .65rem; }
.watch-step strong { color: var(--white); font-size: .78rem; font-weight: 700; }
.watch-step small { color: rgba(235,245,235,.5); font-family: var(--mono); font-size: .62rem; }
.hero-proof {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin-top: 84px;
  border-top: 1px solid rgba(211,234,213,.2);
}
.hero-proof-item { min-height: 94px; padding: 20px 20px 5px 0; border-right: 1px solid rgba(211,234,213,.15); }
.hero-proof-item:not(:first-child) { padding-left: 22px; }
.hero-proof-item:last-child { border-right: 0; }
.hero-proof-item strong { display: block; color: var(--white); font-size: 1.22rem; letter-spacing: -.03em; }
.hero-proof-item span { color: rgba(235,245,235,.53); font-family: var(--mono); font-size: .64rem; letter-spacing: .05em; text-transform: uppercase; }

.site-main { padding: 110px 0 130px; }
.section { margin-top: 110px; }
.section:first-child { margin-top: 0; }
.section-head { display: flex; align-items: end; justify-content: space-between; gap: 30px; margin-bottom: 30px; }
.section-head h2, .section-title { max-width: 700px; margin: 0; color: var(--ink-strong); font-size: clamp(2rem, 4vw, 3.55rem); font-weight: 700; letter-spacing: -.065em; line-height: 1.04; }
.section-head p:not(.kicker), .section-intro { max-width: 590px; margin: 16px 0 0; color: var(--muted); font-size: 1rem; }
.section-head > a { flex: none; font-size: .84rem; font-weight: 800; }
.intro-grid { display: grid; grid-template-columns: 1.1fr .9fr; gap: 70px; align-items: start; }
.intro-copy .section-title { max-width: 590px; }
.intro-copy p:last-child { max-width: 540px; margin-top: 24px; color: var(--muted); font-size: 1.03rem; }
.margin-note { padding: 19px 0 0 24px; border-left: 1px solid var(--coral); }
.margin-note strong { display: block; color: var(--ink-strong); font-size: 1rem; }
.margin-note p { margin: 9px 0 0; color: var(--muted); font-size: .9rem; }
.feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.feature-card, .surface, .setup-card, .fallback-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--white);
  box-shadow: var(--shadow-sm);
}
.feature-card { min-height: 240px; padding: 26px; transition: transform .2s ease, box-shadow .2s ease; }
.feature-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-md); }
.feature-index { color: var(--coral); font-family: var(--mono); font-size: .68rem; letter-spacing: .1em; }
.feature-card h3 { margin: 72px 0 8px; color: var(--ink-strong); font-size: 1.2rem; letter-spacing: -.035em; }
.feature-card p { margin: 0; color: var(--muted); font-size: .9rem; }
.process-section { padding: 42px; border-radius: var(--radius-lg); background: var(--cream); }
.process-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin-top: 34px; }
.process-item { position: relative; padding: 0 22px 0 0; }
.process-item:not(:first-child) { padding-left: 22px; border-left: 1px solid #cfd5cb; }
.process-item::after { position: absolute; top: 10px; right: -4px; width: 8px; height: 8px; border-radius: 50%; background: var(--coral); content: ""; }
.process-item:last-child::after { display: none; }
.process-no { color: var(--moss); font-family: var(--mono); font-size: .68rem; }
.process-item h3 { margin: 28px 0 7px; color: var(--ink-strong); font-size: 1.03rem; letter-spacing: -.025em; }
.process-item p { margin: 0; color: var(--muted); font-size: .84rem; }

.review-section { padding-top: 18px; }
.featured-review { min-height: 250px; }
.featured-review-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  align-items: end;
  padding: 34px;
  border: 1px solid var(--line-dark);
  border-radius: var(--radius-md);
  background: var(--forest);
  color: var(--white);
  box-shadow: var(--shadow-md);
}
.featured-review-card h3 { max-width: 690px; margin: 20px 0 10px; font-size: clamp(1.65rem, 3vw, 2.7rem); letter-spacing: -.06em; line-height: 1.06; }
.featured-review-card p { max-width: 680px; margin: 0; color: rgba(235,245,235,.69); font-size: .94rem; }
.featured-review-card .button { color: var(--ink-strong); white-space: nowrap; }
.review-meta-row { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; color: rgba(235,245,235,.55); font-family: var(--mono); font-size: .68rem; letter-spacing: .06em; text-transform: uppercase; }
.state-chip, .tag, .origin-badge, .direction-chip, .status-chip {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  border-radius: 99px;
  font-family: var(--mono);
  font-size: .65rem;
  font-weight: 500;
  letter-spacing: .05em;
  line-height: 1.2;
  text-transform: uppercase;
}
.state-chip { padding: 8px 10px; background: var(--lime); color: var(--ink-strong); }
.tag { padding: 6px 9px; background: var(--mint); color: var(--moss); }
.origin-badge { padding: 5px 8px; background: var(--mint); color: var(--moss); }
.direction-chip { padding: 6px 9px; background: #edf0ec; color: #58665e; }
.direction-chip.less-clear { background: #ffeadf; color: #91452b; }
.direction-chip.clearer { background: #e0f2dd; color: #236543; }
.direction-chip.unknown { background: #f5edd8; color: #776126; }
.status-chip { padding: 7px 9px; background: var(--mint); color: var(--moss); }
.empty, .error-box { padding: 23px; border-radius: var(--radius-sm); background: var(--white); color: var(--muted); }
.empty { border: 1px dashed var(--line); }
.error-box { border: 1px solid #e7b5a5; background: #fff2ed; color: var(--danger); }

.proof-section { padding-top: 18px; }
.proof-band { display: grid; grid-template-columns: 1fr 1.3fr; gap: 40px; align-items: start; padding: 38px; border-radius: var(--radius-lg); background: var(--ink-strong); color: var(--white); }
.proof-band .section-title { color: var(--white); font-size: clamp(1.9rem, 3.5vw, 3rem); }
.proof-band .section-intro { color: rgba(235,245,235,.64); }
.proof-stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.proof-stat { padding: 19px; border: 1px solid rgba(211,234,213,.16); border-radius: var(--radius-sm); background: rgba(255,255,255,.045); }
.proof-stat strong { display: block; color: var(--lime); font-size: 1.6rem; letter-spacing: -.05em; }
.proof-stat span { display: block; margin-top: 5px; color: rgba(235,245,235,.55); font-family: var(--mono); font-size: .63rem; letter-spacing: .06em; text-transform: uppercase; }
.proof-links { display: flex; flex-wrap: wrap; gap: 12px 18px; margin-top: 24px; }
.proof-links a { color: var(--lime); font-size: .79rem; font-weight: 700; }
.role-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 14px; }
.role-card { padding: 17px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--paper); }
.role-card strong { display: block; color: var(--ink-strong); font-family: var(--mono); font-size: .63rem; letter-spacing: .06em; text-transform: uppercase; }
.role-card span { display: block; margin-top: 22px; color: var(--muted); font-size: .78rem; line-height: 1.45; }
.closing-cta { display: flex; align-items: end; justify-content: space-between; gap: 30px; padding: 40px 0 0; border-top: 1px solid var(--line); }
.closing-cta .section-title { max-width: 640px; }
.reveal { opacity: 0; transform: translateY(16px); }
.reveal.is-visible { animation: reveal-in .65s cubic-bezier(.2,.8,.2,1) both; animation-delay: var(--delay, 0ms); }

.inner-header { background: var(--forest-deep); color: var(--white); }
.inner-header .site-nav { border-bottom-color: rgba(211,234,213,.16); }
.inner-copy { padding: 54px 0 62px; }
.inner-wrap { width: min(1180px, calc(100% - 48px)); margin: 0 auto; }
.breadcrumb { margin: 0 0 25px; color: rgba(235,245,235,.55); font-family: var(--mono); font-size: .66rem; letter-spacing: .08em; text-transform: uppercase; }
.breadcrumb a { color: rgba(235,245,235,.72); text-decoration: none; }
.inner-title { max-width: 800px; margin: 0; color: var(--white); font-size: clamp(2.65rem, 6vw, 5rem); letter-spacing: -.075em; line-height: .99; }
.inner-lede { max-width: 670px; margin: 20px 0 0; color: rgba(235,245,235,.68); font-size: 1.05rem; }
.site-footer { padding: 0 0 34px; color: var(--muted); font-size: .82rem; }
.site-footer a { font-weight: 700; }
.footer-rule { height: 1px; margin-bottom: 20px; background: var(--line); }

.setup-main { width: min(1080px, calc(100% - 48px)); margin: 0 auto; padding: 70px 0 120px; }
.setup-layout { display: grid; grid-template-columns: .8fr 1.2fr; gap: 22px; align-items: start; }
.setup-card { padding: 30px; }
.setup-card--dark { position: sticky; top: 24px; border-color: var(--forest); background: var(--forest); color: var(--white); }
.setup-card--dark h2 { color: var(--white); }
.setup-card--dark p { color: rgba(235,245,235,.68); }
.setup-card h2 { margin: 0; color: var(--ink-strong); font-size: 1.65rem; letter-spacing: -.05em; line-height: 1.1; }
.setup-card p { color: var(--muted); font-size: .92rem; }
.setup-list { display: grid; gap: 17px; margin: 30px 0 0; padding: 0; list-style: none; }
.setup-list li { display: grid; grid-template-columns: 27px 1fr; gap: 11px; color: rgba(235,245,235,.75); font-size: .88rem; }
.setup-list li::before { display: grid; width: 22px; height: 22px; place-items: center; border-radius: 50%; background: var(--lime); color: var(--ink-strong); content: "✓"; font-size: .7rem; font-weight: 900; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 17px; margin-top: 23px; }
.field { display: flex; flex-direction: column; gap: 7px; }
.field--wide { grid-column: 1 / -1; }
.field label, .field > span { color: var(--ink-strong); font-size: .8rem; font-weight: 800; }
.field small, .form-help { color: var(--muted); font-size: .75rem; line-height: 1.5; }
.field input, .field select { width: 100%; min-height: 46px; padding: 0 13px; border: 1px solid var(--line); border-radius: 10px; outline: none; background: var(--paper); color: var(--ink); transition: border-color .2s ease, box-shadow .2s ease, background .2s ease; }
.field input:focus, .field select:focus { border-color: var(--moss); background: var(--white); box-shadow: 0 0 0 4px rgba(47,123,91,.11); }
.advanced { margin-top: 23px; padding-top: 18px; border-top: 1px solid var(--line); }
.advanced summary { cursor: pointer; color: var(--moss); font-size: .82rem; font-weight: 800; }
.body-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 13px; }
.body-list label { padding: 10px 11px; border: 1px solid var(--line); border-radius: 9px; background: var(--mint); color: var(--ink); font-size: .77rem; }
.body-list input { accent-color: var(--moss); }
.form-actions { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-top: 24px; }
.form-actions .button { border: 0; }
.button--dark { background: var(--forest); color: var(--white); }
.button--dark:hover { background: var(--forest-deep); color: var(--white); }
.result { min-height: 22px; margin: 0; color: var(--muted); font-size: .78rem; }
.result.error { color: var(--danger); }
.result.success { color: var(--moss); }
.confirm-card { margin-top: 24px; padding: 25px; border: 1px solid #b7d6bd; border-radius: var(--radius-md); background: var(--mint); }
.confirm-card h2 { color: var(--forest); }
.confirm-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
.confirm-grid > div { padding: 13px; border-radius: 10px; background: var(--white); }
.confirm-grid strong { display: block; color: var(--muted); font-family: var(--mono); font-size: .61rem; letter-spacing: .06em; text-transform: uppercase; }
.confirm-grid span { display: block; margin-top: 6px; color: var(--ink-strong); font-size: .83rem; font-weight: 800; }

.detail-main { width: min(1120px, calc(100% - 48px)); margin: 0 auto; padding: 68px 0 120px; }
.review-hero { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(240px, .5fr); gap: 40px; align-items: end; padding-bottom: 42px; border-bottom: 1px solid var(--line); }
.review-hero h1 { max-width: 800px; margin: 19px 0 14px; color: var(--ink-strong); font-size: clamp(2.5rem, 5.6vw, 5rem); letter-spacing: -.075em; line-height: .99; }
.review-hero .lead { max-width: 750px; margin: 17px 0 0; color: var(--muted); font-size: 1.08rem; }
.review-matter { margin: 0; color: var(--muted); font-family: var(--mono); font-size: .68rem; letter-spacing: .05em; text-transform: uppercase; }
.review-sidecar { padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--cream); }
.review-sidecar strong { display: block; color: var(--ink-strong); font-size: 1.55rem; letter-spacing: -.05em; }
.review-sidecar span { display: block; margin-top: 4px; color: var(--muted); font-family: var(--mono); font-size: .63rem; letter-spacing: .04em; text-transform: uppercase; }
.replay-banner { display: flex; align-items: center; gap: 10px; margin: 0 0 24px; padding: 12px 15px; border: 1px solid #e4c67d; border-radius: 10px; background: var(--warm); color: #67531e; font-size: .82rem; }
.replay-banner strong { color: var(--ink-strong); }
.detail-actions { display: flex; flex-wrap: wrap; gap: 12px 18px; margin-top: 21px; font-size: .8rem; font-weight: 800; }
.surface { margin-top: 24px; padding: 30px; }
.surface > h2 { margin: 0; color: var(--ink-strong); font-size: 1.65rem; letter-spacing: -.05em; line-height: 1.1; }
.surface > h2 + .section-intro, .surface > h2 + p { margin-top: 10px; }
.surface > p { color: var(--muted); font-size: .9rem; }
.glance-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 20px; }
.glance-item { padding: 15px; border-radius: 10px; background: var(--cream); }
.glance-item strong { display: block; color: var(--ink-strong); font-size: 1.25rem; letter-spacing: -.04em; }
.glance-item span { display: block; margin-top: 3px; color: var(--muted); font-family: var(--mono); font-size: .62rem; letter-spacing: .05em; text-transform: uppercase; }
.dimensions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 22px; }
.dimension { min-height: 190px; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--paper); }
.dimension--wide { grid-column: 1 / -1; }
.dimension-heading { display: flex; justify-content: space-between; align-items: start; gap: 12px; }
.dimension-heading h3 { margin: 0; color: var(--ink-strong); font-size: 1rem; letter-spacing: -.025em; }
.comparison-values { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 20px; }
.comparison-values > div { min-height: 72px; padding: 11px; border-radius: 8px; background: var(--white); }
.comparison-values span { display: block; color: var(--muted); font-family: var(--mono); font-size: .61rem; letter-spacing: .04em; text-transform: uppercase; }
.comparison-values strong { display: block; margin-top: 6px; color: var(--ink-strong); font-size: .86rem; line-height: 1.4; }
.note { margin: 15px 0 0; color: var(--muted); font-size: .78rem; }
.evidence { display: grid; gap: 8px; margin-top: 17px; }
.evidence-link { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; font-size: .78rem; }
.evidence-link a { font-weight: 800; }
.evidence-link .muted { font-family: var(--mono); font-size: .62rem; }
.facts ul, .question-list { margin: 18px 0 0; padding-left: 20px; }
.facts li, .question-list li { margin: 11px 0; color: var(--ink); font-size: .9rem; }
.facts li p { margin: 0; }
.timeline { display: grid; gap: 0; margin: 23px 0 0; padding: 0; list-style: none; border-left: 1px solid var(--line-dark); }
.timeline li { position: relative; display: grid; grid-template-columns: max-content 1fr max-content; gap: 15px; align-items: center; margin: 0; padding: 16px 0 16px 22px; }
.timeline li::before { position: absolute; left: -5px; width: 9px; height: 9px; border: 3px solid var(--paper); border-radius: 50%; background: var(--coral); content: ""; }
.timeline strong { color: var(--ink-strong); font-family: var(--mono); font-size: .68rem; font-weight: 500; }
.timeline span:not(.origin-badge) { color: var(--muted); font-family: var(--mono); font-size: .63rem; }
.timeline a { font-size: .76rem; font-weight: 800; }
.review-counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
.count { padding: 16px; border-radius: 10px; background: var(--cream); }
.count strong { display: block; color: var(--ink-strong); font-size: 1.6rem; letter-spacing: -.05em; }
.count span { display: block; margin-top: 3px; color: var(--muted); font-family: var(--mono); font-size: .62rem; letter-spacing: .04em; text-transform: uppercase; }
.rejection { margin-top: 11px; padding: 16px 18px; border-left: 3px solid var(--coral); border-radius: 0 10px 10px 0; background: #fff5ed; }
.rejection h3 { margin: 0; color: var(--ink-strong); font-size: .91rem; }
.rejection p { margin: 5px 0 0; color: var(--muted); font-size: .82rem; }
.rejection-id { font-family: var(--mono); font-size: .63rem !important; }
.role-line { color: var(--muted); font-size: .84rem; line-height: 2.2; }
.boundary { border-color: #d9d2c0; background: var(--cream); }
.boundary p { color: var(--ink); }

.record-main { width: min(1080px, calc(100% - 48px)); margin: 0 auto; padding: 65px 0 120px; }
.record-intro { max-width: 760px; color: var(--muted); font-size: 1.03rem; }
.appearance-list { display: grid; gap: 14px; margin-top: 31px; }
.appearance { position: relative; padding: 25px 28px 25px 32px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--white); box-shadow: var(--shadow-sm); }
.appearance::before { position: absolute; top: 28px; left: -5px; width: 9px; height: 9px; border: 3px solid var(--paper); border-radius: 50%; background: var(--coral); content: ""; }
.appearance h2 { margin: 0; color: var(--ink-strong); font-size: 1.34rem; letter-spacing: -.04em; }
.appearance-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 9px 0 0; color: var(--muted); font-family: var(--mono); font-size: .65rem; letter-spacing: .03em; text-transform: uppercase; }
.appearance h3 { margin: 24px 0 7px; color: var(--ink-strong); font-size: .88rem; }
.attachment-list { margin: 0; padding-left: 18px; color: var(--muted); font-size: .84rem; }
.attachment-list li { margin: 7px 0; }

.evidence-main { width: min(920px, calc(100% - 48px)); margin: 0 auto; padding: 65px 0 120px; }
.evidence-note { display: flex; align-items: start; gap: 13px; margin: 24px 0; padding: 16px 18px; border-radius: var(--radius-sm); background: var(--cream); color: var(--muted); font-size: .85rem; }
.evidence-note::before { flex: none; width: 9px; height: 9px; margin-top: 8px; border-radius: 50%; background: var(--coral); content: ""; }
.pdf-link { display: inline-flex; margin: 3px 0 28px; font-size: .85rem; font-weight: 800; }
blockquote { margin: 14px 0; padding: 19px 22px; border-left: 3px solid var(--coral); border-radius: 0 12px 12px 0; background: var(--white); box-shadow: var(--shadow-sm); }
blockquote b { color: var(--moss); font-family: var(--mono); font-size: .67rem; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; }
mark { background: #fff0a4; color: var(--ink-strong); }

.watch-main { width: min(820px, calc(100% - 48px)); margin: 0 auto; padding: 65px 0 120px; }
.watch-status { display: inline-flex; padding: 7px 10px; border-radius: 99px; background: var(--mint); color: var(--moss); font-family: var(--mono); font-size: .66rem; letter-spacing: .05em; text-transform: uppercase; }
.watch-status.stopped { background: #eef0ed; color: var(--muted); }
.watch-facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 20px; }
.watch-fact { padding: 15px; border-radius: 10px; background: var(--cream); }
.watch-fact strong { display: block; color: var(--muted); font-family: var(--mono); font-size: .61rem; letter-spacing: .05em; text-transform: uppercase; }
.watch-fact span { display: block; margin-top: 5px; color: var(--ink-strong); font-size: .86rem; font-weight: 800; }
.body-pills { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 18px; }
.body-pill { padding: 7px 10px; border-radius: 99px; background: var(--mint); color: var(--moss); font-size: .75rem; font-weight: 800; }
.stop-button { min-height: 44px; padding: 0 17px; border: 1px solid #d3a06a; border-radius: 99px; background: var(--warm); color: #72501d; font-weight: 800; }
.stop-button:hover { background: #ffe9ae; }
.stop-button:disabled { cursor: wait; opacity: .6; }

@keyframes rise-in { from { opacity: 0; transform: translateY(18px) rotate(1deg); } to { opacity: 1; transform: translateY(0) rotate(0); } }
@keyframes reveal-in { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes soft-pulse { 0%, 100% { opacity: .65; } 50% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; } }
@media (max-width: 900px) {
  .hero-grid, .intro-grid, .setup-layout, .review-hero, .proof-band { grid-template-columns: 1fr; }
  .hero-art { min-height: 390px; max-width: 520px; }
  .setup-card--dark { position: static; }
  .role-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 700px) {
  .site-nav, .hero-wrap, .site-main, .site-footer, .inner-wrap, .setup-main, .detail-main, .record-main, .evidence-main, .watch-main { width: min(100% - 32px, 620px); }
  .site-nav { min-height: 68px; }
  .nav-links { gap: 14px; }
  .nav-links a:not(.nav-cta) { display: none; }
  .hero-wrap { padding-top: 65px; }
  .display { font-size: clamp(2.75rem, 14vw, 4.8rem); }
  .hero-proof { grid-template-columns: repeat(2, 1fr); margin-top: 61px; }
  .hero-proof-item:nth-child(2) { border-right: 0; }
  .hero-proof-item:nth-child(3), .hero-proof-item:nth-child(4) { border-top: 1px solid rgba(211,234,213,.15); }
  .hero-proof-item:nth-child(3) { padding-left: 0; }
  .hero-proof-item:nth-child(4) { border-right: 0; }
  .site-main { padding-top: 75px; }
  .section { margin-top: 75px; }
  .section-head, .closing-cta { display: block; }
  .section-head > a { display: inline-block; margin-top: 16px; }
  .feature-grid, .process-grid, .dimensions { grid-template-columns: 1fr; }
  .process-section, .proof-band, .surface, .setup-card { padding: 23px; }
  .process-item { padding: 17px 0 0 !important; border-left: 0 !important; border-top: 1px solid #cfd5cb; }
  .process-item:first-child { padding-top: 0 !important; border-top: 0; }
  .process-item::after { display: none; }
  .process-item h3 { margin-top: 13px; }
  .featured-review-card { grid-template-columns: 1fr; padding: 24px; }
  .proof-stats, .glance-grid, .review-counts, .confirm-grid, .watch-facts { grid-template-columns: 1fr 1fr; }
  .role-grid { grid-template-columns: 1fr 1fr; }
  .dimension--wide { grid-column: auto; }
  .timeline li { grid-template-columns: 1fr; gap: 5px; }
  .timeline a { margin-top: 4px; }
  .form-grid, .body-list { grid-template-columns: 1fr; }
  .field--wide { grid-column: auto; }
  .hero-art { min-height: 355px; }
  .watch-card { right: 0; }
}
@media (max-width: 430px) {
  .nav-cta { padding: 0 11px; }
  .hero-art { min-height: 330px; }
  .watch-card { padding: 18px; }
  .watch-card h2 { margin-top: 31px; font-size: 1.7rem; }
  .proof-stats, .glance-grid, .review-counts, .confirm-grid, .watch-facts { grid-template-columns: 1fr; }
}
"""


def _url(public_path: str, path: str) -> str:
    if path.startswith(("https://", "http://")):
        return path
    prefix = "" if public_path in {"", "/"} else public_path.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{prefix}{suffix}" or "/"


def _display(value: object, fallback: str = "Could not determine") -> str:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    text = str(value).strip()
    return text if text else fallback


def _safe_href(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    href = value.strip()
    return href if href.startswith(("https://", "http://", "/")) else None


def _as_dict(value: object) -> dict[str, JSONValue]:
    return value if isinstance(value, dict) else {}


def _json_list(value: object) -> list[JSONValue]:
    return value if isinstance(value, list) else []


def _object_list(value: object) -> list[dict[str, JSONValue]]:
    return [item for item in _json_list(value) if isinstance(item, dict)]


def _page(title: str, body: str, script: str = "") -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0d3428"><meta name="referrer" content="no-referrer">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<title>{safe_title}</title><style>{_SITE_CSS}</style></head><body>{body}{script}</body></html>"""


def _site_nav(home_url: str, watch_url: str) -> str:
    return f"""<nav class="site-nav"><a class="brand" href="{home_url}"><span class="brand-mark">47</span><span>Page 47</span></a><div class="nav-links"><a href="{home_url}#how-it-works">How it works</a><a href="{home_url}#review">Reviews</a><a class="nav-cta" href="{watch_url}">Start a watch <span aria-hidden="true">↗</span></a></div></nav>"""


def index_page(title: str, default_city: str, public_path: str) -> str:
    home_url = html.escape(_url(public_path, "/"), quote=True)
    watch_url = html.escape(_url(public_path, "/watch"), quote=True)
    explore_url = html.escape(_url(public_path, "/explore"), quote=True)
    architecture_url = html.escape(
        "https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.md", quote=True
    )
    body = f"""
<header class="site-header"><div class="site-nav-wrap">{_site_nav(home_url, watch_url)}</div>
  <div class="hero-wrap"><div class="hero-grid"><div>
    <p class="kicker">PUBLIC RECORD WATCH</p>
    <h1 class="display">City packets change.<br><em>Page 47 watches what you care about.</em></h1>
    <p class="hero-lede">Tell Page 47 your neighbourhood or address. It watches public meeting records in the background and emails you only when a change survives an evidence review.</p>
    <div class="button-row"><a class="button" href="{watch_url}">Watch my area <span aria-hidden="true">↗</span></a><a id="hero-review-link" class="button button--quiet" href="{explore_url}">Open a real review</a></div>
    <p class="trust-line">Every reported fact links to the public record. Page 47 does not infer intent.</p>
  </div><div class="hero-art" aria-label="A Page 47 watch follows a public record in the background">
    <div class="watch-card"><div class="watch-card-top"><span>PAGE 47 / ACTIVE WATCH</span><span class="live-dot">RUNNING</span></div><h2>One place.<br>Kept in view.</h2><p>The resident steps away. The record does not.</p><div class="watch-rail"><div class="watch-step"><span>01</span><strong>Capture public record</strong><small>stored</small></div><div class="watch-step"><span>02</span><strong>Compare appearances</strong><small>separate</small></div><div class="watch-step"><span>03</span><strong>Challenge the finding</strong><small>skeptic</small></div><div class="watch-step"><span>04</span><strong>Return the evidence</strong><small>linked</small></div></div></div>
  </div></div><div class="hero-proof" aria-label="Page 47 proof points"><div class="hero-proof-item"><strong>5 roles</strong><span>bounded evidence review</span></div><div class="hero-proof-item"><strong>2 cities</strong><span>Seattle + Denver</span></div><div class="hero-proof-item"><strong>28 / 28</strong><span>controlled states correct</span></div><div class="hero-proof-item"><strong>0</strong><span>motive claims published</span></div></div></div>
</header>
<main class="site-main">
  <section class="section intro-grid" id="why"><div class="intro-copy"><p class="kicker">A quieter way to stay informed</p><h2 class="section-title">Not another civic dashboard. A watch that keeps working after you leave.</h2><p>Public decisions are spread across agendas, consent calendars, attachments, and revised packets. Page 47 turns that moving record into a durable, evidence-linked trail for one place at a time.</p></div><aside class="margin-note"><strong>For residents, neighbourhood groups, local journalists, and civic organisations.</strong><p>You choose what matters. Page 47 keeps the record, makes the comparison, and tells you what it can—and cannot—establish.</p></aside></section>
  <section class="section" id="how-it-works"><div class="section-head"><div><p class="kicker">How the service works</p><h2>Four quiet steps between you and a changing packet.</h2></div></div><div class="feature-grid"><article class="feature-card"><span class="feature-index">01 / WATCH</span><h3>Choose a place</h3><p>Start with a city and neighbourhood or address. No knowledge of committee structure required.</p></article><article class="feature-card"><span class="feature-index">02 / OBSERVE</span><h3>Leave the tab</h3><p>The scheduled collector keeps the public record and preserves changed bytes with capture time and hash.</p></article><article class="feature-card"><span class="feature-index">03 / REVIEW</span><h3>Let evidence disagree</h3><p>Separate readers inspect presentation, process, and substance. A Skeptic can veto the attractive interpretation.</p></article></div></section>
  <section class="section process-section"><p class="kicker">From record to resident</p><h2 class="section-title">The useful part is what Page 47 refuses to pretend.</h2><div class="process-grid"><article class="process-item"><span class="process-no">01</span><h3>Capture</h3><p>Keep what was publicly available at the time Page 47 saw it.</p></article><article class="process-item"><span class="process-no">02</span><h3>Compare</h3><p>Show title, placement, substance, and timing as separate dimensions.</p></article><article class="process-item"><span class="process-no">03</span><h3>Challenge</h3><p>Reject motive claims and explanations the supplied record cannot support.</p></article><article class="process-item"><span class="process-no">04</span><h3>Return</h3><p>Give residents primary links and questions—not a political instruction.</p></article></div></section>
  <section class="section review-section" id="review"><div class="section-head"><div><p class="kicker">The receipt</p><h2>Start with the evidence, not the machinery.</h2><p>Open a stored review to see exactly what changed, what survived challenge, and where the record runs out.</p></div><a href="{explore_url}">Open the strongest saved review ↗</a></div><div id="featured-review" class="featured-review" aria-live="polite"><div class="empty">Loading the stored public record…</div></div></section>
  <section class="section proof-section" id="proof"><div class="proof-band"><div><p class="kicker">Why this holds up</p><h2 class="section-title">Evidence first. Uncertainty in the open.</h2><p class="section-intro">Page 47 keeps the decision boundary visible instead of compressing it into a risk score.</p><div class="proof-links"><a href="{architecture_url}">Read the architecture ↗</a><a href="https://github.com/Jennycruzy/Page47/blob/main/docs/controlled-evaluation-audit.md">Read the evaluation ↗</a></div></div><div class="proof-stats"><div class="proof-stat"><strong>Observed</strong><span>Page 47 captured both states</span></div><div class="proof-stat"><strong>Reconstructed</strong><span>Historical public record only</span></div><div class="proof-stat"><strong>Cannot determine</strong><span>Evidence is not sufficient</span></div><div class="proof-stat"><strong>Mixed</strong><span>Opposing dimensions stay visible</span></div></div></div><div class="section-head" style="margin-top:58px"><div><p class="kicker">The review engine</p><h2>Five bounded roles. One accountable brief.</h2></div></div><div class="role-grid"><div class="role-card"><strong>Archivist</strong><span>Keeps the appearances in order.</span></div><div class="role-card"><strong>Substance</strong><span>Reads captured document pages.</span></div><div class="role-card"><strong>Process</strong><span>Checks title and placement.</span></div><div class="role-card"><strong>Skeptic</strong><span>Can say no before publication.</span></div><div class="role-card"><strong>Brief Writer</strong><span>Returns evidence and agency.</span></div></div></section>
  <section class="section closing-cta"><div><p class="kicker">Start with one place</p><h2 class="section-title">The public record is already moving. Put Page 47 on it.</h2></div><a class="button button--dark" href="{watch_url}">Start a watch <span aria-hidden="true">↗</span></a></section>
</main><footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Page 47</a> reports public records. It does not determine why a change was made or tell you what position to take. · <a href="{architecture_url}">Architecture</a> · <a href="https://github.com/Jennycruzy/Page47">Source</a></footer>
"""
    script = """
<script>
const publicPath = __PUBLIC_PATH__;
const featured = document.querySelector('#featured-review');
const heroReviewLink = document.querySelector('#hero-review-link');
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const internal = (path) => (publicPath === '/' ? '' : publicPath) + (path.startsWith('/') ? path : '/' + path);
const stateLabel = (value) => ({less_clear:'Presentation became less clear',mixed:'Presentation changed in mixed directions',clearer:'Presentation became clearer',unchanged:'No meaningful presentation change',cannot_determine:'Page 47 could not determine the direction'}[value] || 'Review status unavailable');
async function json(url) { const response = await fetch(url); if (!response.ok) throw new Error('Request failed'); return response.json(); }
function reviewCard(city, finding) {
  const brief = finding.brief || {}; const decision = finding.decision || {};
  const findingUrl = internal('/finding/' + encodeURIComponent(city) + '/' + encodeURIComponent(finding.finding_id));
  const matterUrl = internal('/matter/' + encodeURIComponent(city) + '/' + encodeURIComponent(finding.matter_id));
  const label = stateLabel(finding.state);
  return '<article class="featured-review-card"><div><div class="review-meta-row"><span class="state-chip">' + esc(label) + '</span><span>' + esc(city) + ' · matter ' + esc(finding.matter_id) + '</span></div><h3>' + esc(brief.heading || 'A stored Page 47 review') + '</h3><p>' + esc(decision.reason || 'The saved review is ready to inspect.') + '</p><p class="review-meta-row" style="margin-top:18px"><span>' + esc(finding.supported_count || 0) + ' supported</span><span>' + esc(finding.rejected_count || 0) + ' rejected after review</span></p></div><div><a class="button" href="' + findingUrl + '">Read the evidence ↗</a><p style="margin-top:13px;text-align:right"><a style="color:rgba(235,245,235,.72);font-size:.76rem;font-weight:700" href="' + matterUrl + '">View matter history</a></p></div></article>';
}
async function loadFeatured() {
  try {
    const cityData = await json(internal('/api/cities'));
    const cities = Array.isArray(cityData.cities) ? cityData.cities : [];
    const responses = await Promise.allSettled(cities.map((city) => json(internal('/api/cities/' + encodeURIComponent(city.name) + '/findings?limit=40'))));
    const priority = {less_clear:0,mixed:1,clearer:2,unchanged:3,cannot_determine:4}; const candidates = [];
    responses.forEach((response, index) => { if (response.status !== 'fulfilled') return; const items = Array.isArray(response.value.findings) ? response.value.findings : []; items.forEach((item) => candidates.push({city:cities[index].name, item})); });
    candidates.sort((left, right) => (priority[left.item.state] ?? 5) - (priority[right.item.state] ?? 5));
    if (!candidates.length) { featured.innerHTML = '<div class="empty">No stored review is available yet. The collector is still building the record.</div>'; return; }
    const chosen = candidates[0]; featured.innerHTML = reviewCard(chosen.city, chosen.item);
    heroReviewLink.href = internal('/finding/' + encodeURIComponent(chosen.city) + '/' + encodeURIComponent(chosen.item.finding_id)); heroReviewLink.textContent = 'Read the featured review ↗';
  } catch (error) { featured.innerHTML = '<div class="error-box">The stored review could not be loaded. The watch service is still available.</div>'; }
}
loadFeatured();
const revealItems = document.querySelectorAll('.section, .feature-card, .process-item, .proof-band, .role-card, .closing-cta');
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: .12 });
  revealItems.forEach((element, index) => {
    element.classList.add('reveal');
    element.style.setProperty('--delay', Math.min(index * 35, 210) + 'ms');
    observer.observe(element);
  });
} else {
  revealItems.forEach((element) => element.classList.add('is-visible'));
}
</script>
""".replace("__PUBLIC_PATH__", json.dumps(public_path))
    return _page(f"{title} — when the packet changes", body, script)


def watch_setup_page(title: str, default_city: str, public_path: str) -> str:
    home_url = html.escape(_url(public_path, "/"), quote=True)
    body = f"""
<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}<div class="inner-copy"><p class="breadcrumb"><a href="{home_url}">Page 47</a> / New watch</p><h1 class="inner-title">Put one place on watch.</h1><p class="inner-lede">Choose the place. Page 47 handles the record while you get on with your day.</p></div></div></header>
<main class="setup-main"><div class="setup-layout"><aside class="setup-card setup-card--dark"><p class="kicker">A watch, not a dashboard</p><h2>Tell us what you care about. We’ll keep the public record in view.</h2><p>No account is required. Your private management link lets you check the watch or stop it later.</p><ul class="setup-list"><li>Capture public records and changed documents with time and hash.</li><li>Compare title, placement, substance, and available timing separately.</li><li>Alert only when a supported change survives evidence review.</li></ul></aside><section class="setup-card"><p class="kicker">One minute to start</p><h2>Create your watch</h2><p>Use a neighbourhood, an address, or both. Public bodies begin selected for the city; narrow them only under advanced options.</p><form id="watch-form"><div class="form-grid"><div class="field"><span><label for="city">City</label></span><select id="city" required aria-describedby="city-help"></select><small id="city-help">Page 47 currently monitors Seattle and Denver.</small></div><div class="field"><span><label for="email">Email for alerts</label></span><input id="email" type="email" autocomplete="email" required placeholder="you@example.org" aria-describedby="email-help"><small id="email-help">Used only for evidence-linked alerts.</small></div><div class="field"><span><label for="neighbourhood">Neighbourhood</label></span><input id="neighbourhood" autocomplete="address-level3" placeholder="Capitol Hill" aria-describedby="area-help"></div><div class="field"><span><label for="address">Address <small>(optional)</small></label></span><input id="address" autocomplete="street-address" placeholder="123 Main Street, Seattle, WA" aria-describedby="area-help"></div></div><p id="area-help" class="form-help">At least one area field is required. Page 47 uses it to match relevant public records.</p><details class="advanced"><summary>Advanced options — public bodies</summary><p class="form-help">All configured bodies start selected. Narrow this only if you want a specific committee.</p><div id="bodies" class="body-list" aria-live="polite">Loading public bodies…</div></details><div class="form-actions"><button class="button button--dark" id="watch-submit" type="submit">Start watching <span aria-hidden="true">↗</span></button><p id="watch-result" class="result" aria-live="polite"></p></div></form></section></div><section id="watch-confirmation" class="confirm-card" hidden><p class="kicker">Watch created</p><h2>Page 47 is watching.</h2><p>You can close this page now. The collector will keep checking the public record.</p><div class="confirm-grid"><div><strong>City</strong><span id="confirm-city">—</span></div><div><strong>Area</strong><span id="confirm-area">—</span></div><div><strong>Public bodies</strong><span id="confirm-bodies">—</span></div></div><p><a id="confirm-link" href="#">Manage this private watch ↗</a> <span class="form-help">Keep this link private.</span></p></section></main>
<footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Back to Page 47</a> · Your watch is private and accountless.</footer>
"""
    script = """
<script>
const publicPath = __PUBLIC_PATH__; const defaultCity = __DEFAULT_CITY__; const citySelect = document.querySelector('#city');
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const internal = (path) => (publicPath === '/' ? '' : publicPath) + (path.startsWith('/') ? path : '/' + path);
const errorText = (error) => error instanceof Error ? error.message : String(error);
async function json(url) { const response = await fetch(url); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'The request failed.'); return payload; }
function message(text, kind) { const result = document.querySelector('#watch-result'); result.className = 'result' + (kind ? ' ' + kind : ''); result.textContent = text; }
function selectedBodies() { return [...document.querySelectorAll('input[name="body"]:checked')].map((input) => input.value); }
async function loadBodies() { const container = document.querySelector('#bodies'); container.setAttribute('aria-busy','true'); container.innerHTML = '<span class="form-help">Loading public bodies…</span>'; try { const data = await json(internal('/api/cities/' + encodeURIComponent(citySelect.value) + '/bodies')); const bodies = Array.isArray(data.bodies) ? data.bodies : []; container.innerHTML = bodies.length ? bodies.map((body) => '<label><input type="checkbox" name="body" value="' + esc(body) + '" checked> ' + esc(body) + '</label>').join('') : '<span class="form-help">No monitored bodies are available.</span>'; } catch (error) { container.innerHTML = '<span class="result error">Could not load public bodies: ' + esc(errorText(error)) + '</span>'; } finally { container.removeAttribute('aria-busy'); } }
async function init() { const data = await json(internal('/api/cities')); const cities = Array.isArray(data.cities) ? data.cities : []; citySelect.innerHTML = cities.map((city) => '<option value="' + esc(city.name) + '">' + esc(city.name) + '</option>').join(''); citySelect.value = cities.some((city) => city.name === defaultCity) ? defaultCity : (cities[0]?.name || ''); await loadBodies(); }
citySelect.onchange = () => loadBodies();
document.querySelector('#watch-form').onsubmit = async (event) => { event.preventDefault(); const bodies = selectedBodies(); const address = document.querySelector('#address').value.trim() || null; const neighbourhood = document.querySelector('#neighbourhood').value.trim() || null; if (!bodies.length) { message('Select at least one public body under Advanced options.', 'error'); return; } if (!address && !neighbourhood) { message('Enter a neighbourhood or address so Page 47 knows what to watch.', 'error'); return; } const button = document.querySelector('#watch-submit'); button.disabled = true; button.textContent = 'Saving…'; message('Saving your watch…'); try { const response = await fetch(internal('/api/watches'), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({city:citySelect.value,bodies,address,neighbourhood,email:document.querySelector('#email').value.trim()})}); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'The watch could not be saved.'); const link = internal(payload.manage_path || ('/watch/' + payload.watch_id)); message(payload.message || 'Watch saved.', 'success'); document.querySelector('#confirm-city').textContent = citySelect.value; document.querySelector('#confirm-area').textContent = neighbourhood || address || 'Selected area'; document.querySelector('#confirm-bodies').textContent = bodies.length + ' selected'; document.querySelector('#confirm-link').href = link; document.querySelector('#watch-confirmation').hidden = false; document.querySelector('#watch-confirmation').scrollIntoView({behavior:'smooth',block:'center'}); } catch (error) { message('Could not save the watch: ' + errorText(error), 'error'); } finally { button.disabled = false; button.innerHTML = 'Start watching <span aria-hidden="true">↗</span>'; } };
init().catch((error) => { document.querySelector('#bodies').innerHTML = '<span class="result error">The watch form is unavailable: ' + esc(errorText(error)) + '</span>'; });
</script>
""".replace("__PUBLIC_PATH__", json.dumps(public_path)).replace(
        "__DEFAULT_CITY__", json.dumps(default_city)
    )
    return _page(f"{title} — start a watch", body, script)


def captured_review_unavailable_page(title: str, public_path: str) -> str:
    home_url = html.escape(_url(public_path, "/"), quote=True)
    watch_url = html.escape(_url(public_path, "/watch"), quote=True)
    body = f"""<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}<div class="inner-copy"><p class="breadcrumb"><a href="{home_url}">Page 47</a> / Review</p><h1 class="inner-title">The record is still being assembled.</h1><p class="inner-lede">There is no saved review available yet. The collector is watching the configured public sources, and the live watch path is ready.</p></div></div></header><main class="evidence-main"><article class="fallback-card" style="padding:30px"><p class="kicker">Captured review</p><h2 class="section-title" style="font-size:2.2rem">Come back to a review with a receipt.</h2><p class="record-intro">When a stored review is available, this link opens the same evidence page a resident uses: separate dimensions, captured sources, the Skeptic’s decision, and the limits of what Page 47 knows.</p><a class="button button--dark" href="{watch_url}">Put a place on watch ↗</a></article></main><footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Back to Page 47</a></footer>"""
    return _page(f"{title} — captured review", body)


def _origin_label(value: object, fallback: str) -> str:
    return {
        "observed_by_page47": "Observed by Page 47",
        "reconstructed_from_public_record": "Reconstructed from public record",
        "current_public_record": "Current public record",
        "cannot_determine": "Cannot determine",
    }.get(str(value), fallback)


def _evidence_markup(value: object, fallback_origin: str) -> str:
    if not isinstance(value, list):
        return '<span class="form-help">No primary evidence link was retained.</span>'
    links: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://", "/")):
            continue
        page = item.get("page_number")
        page_number = page if isinstance(page, int) and not isinstance(page, bool) else None
        href = f"{url}#page={page_number}" if page_number is not None else url
        page_text = f" · PDF page {page_number}" if page_number is not None else ""
        label = _display(item.get("label"), "Primary record")
        captured_at = _display(item.get("captured_at"), "capture time unavailable")
        origin = _origin_label(item.get("origin"), fallback_origin)
        links.append(
            f'<div class="evidence-link"><a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">Open {html.escape(label)}{html.escape(page_text)}</a><span class="origin-badge">{html.escape(origin)}</span><span class="muted">{html.escape(captured_at)}</span></div>'
        )
    return "".join(links) or '<span class="form-help">No primary evidence link was retained.</span>'


def evidence_page(title: str, city: str, data: JSONObject, public_path: str) -> str:
    attachment = _as_dict(data.get("attachment"))
    if not attachment:
        raise ValueError("Stored attachment evidence was invalid")
    name = html.escape(_display(attachment.get("name"), "Captured public document"))
    pdf_source = _safe_href(data.get("pdf_url"))
    pdf_url = html.escape(_url(public_path, pdf_source or "#"), quote=True)
    anchors = data.get("anchors")
    blocks: list[str] = []
    if isinstance(anchors, list):
        for item in anchors:
            if not isinstance(item, dict):
                continue
            page = html.escape(_display(item.get("page_number")))
            excerpt = html.escape(_display(item.get("excerpt")))
            blocks.append(
                f"<blockquote><b>PDF page {page}</b><br><mark>{excerpt}</mark></blockquote>"
            )
    if not blocks:
        blocks.append(
            '<p class="form-help">The stored reader found no page passage for this document.</p>'
        )
    home_url = html.escape(_url(public_path, "/"), quote=True)
    body = f"""<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}<div class="inner-copy"><p class="breadcrumb"><a href="{home_url}">Page 47</a> / {html.escape(city)} / Evidence</p><h1 class="inner-title">{name}</h1><p class="inner-lede">The exact captured passage used in the review, with the primary document one click away.</p></div></div></header><main class="evidence-main"><div class="evidence-note">This page shows the captured document passage used by Page 47. The PDF is the primary record; the excerpt is provided to make the relevant page easy to inspect.</div><a class="pdf-link" href="{pdf_url}" target="_blank" rel="noreferrer">Open the captured PDF in a new tab ↗</a>{"".join(blocks)}<div class="surface boundary"><p>Page 47 reports the public record. It does not determine why this change was made.</p></div></main><footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Back to Page 47</a></footer>"""
    return _page(f"{title} — evidence", body)


def matter_page(title: str, city: str, data: JSONObject, public_path: str) -> str:
    case = _as_dict(data.get("case"))
    matter = _as_dict(case.get("matter"))
    appearances = case.get("appearances")
    if not matter or not isinstance(appearances, list):
        raise ValueError("Stored matter record was incomplete")
    current_title = html.escape(_display(matter.get("current_title"), "Untitled public matter"))
    blocks: list[str] = []
    for appearance in appearances:
        if not isinstance(appearance, dict):
            continue
        attachments: list[str] = []
        raw_attachments = appearance.get("attachments")
        if isinstance(raw_attachments, list):
            for attachment in raw_attachments:
                if not isinstance(attachment, dict):
                    continue
                attachment_id = attachment.get("attachment_id")
                name = html.escape(_display(attachment.get("name"), "Unnamed attachment"))
                if isinstance(attachment_id, int) and not isinstance(attachment_id, bool):
                    link = _url(public_path, f"/evidence/{city}/attachment/{attachment_id}")
                    attachments.append(
                        f'<li>{name} · <a href="{html.escape(link, quote=True)}">View captured document ↗</a></li>'
                    )
                else:
                    attachments.append(f"<li>{name} · document not available</li>")
        attachment_html = (
            '<ul class="attachment-list">' + "".join(attachments) + "</ul>"
            if attachments
            else '<p class="form-help">No attachment was stored for this appearance.</p>'
        )
        pdf_pages = appearance.get("pdf_evidence_pages")
        page_numbers = (
            ", ".join(str(page) for page in pdf_pages if isinstance(page, int))
            if isinstance(pdf_pages, list)
            else ""
        )
        source = appearance.get("source")
        source_html = ""
        source_url = _safe_href(source.get("url")) if isinstance(source, dict) else None
        if source_url is not None:
            source_html = f'<a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noreferrer">Open source record ↗</a>'
        blocks.append(
            f'<article class="appearance"><h2>{html.escape(_display(appearance.get("title_as_presented"), "Title not available"))}</h2><div class="appearance-meta"><span>{html.escape(_display(appearance.get("event_date")))}</span><span>{html.escape(_display(appearance.get("body_name")))}</span><span>{html.escape(_display(appearance.get("pdf_placement"), "placement unavailable"))}</span></div><p class="form-help" style="margin-top:15px">{html.escape("PDF pages: " + page_numbers if page_numbers else "PDF section: could not determine")}</p>{source_html}<h3>Attached public documents</h3>{attachment_html}</article>'
        )
    finding = data.get("finding")
    finding_link = ""
    if isinstance(finding, dict) and isinstance(finding.get("finding_id"), str):
        finding_url = _url(public_path, f"/finding/{city}/{finding['finding_id']}")
        finding_link = f'<a class="button button--dark" href="{html.escape(finding_url, quote=True)}">Read the saved review ↗</a>'
    home_url = html.escape(_url(public_path, "/"), quote=True)
    body = f"""<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}<div class="inner-copy"><p class="breadcrumb"><a href="{home_url}">Page 47</a> / {html.escape(city)} / Matter</p><h1 class="inner-title">{current_title}</h1><p class="inner-lede">A chronological view of how this public matter appeared in the records Page 47 captured.</p>{finding_link}</div></div></header><main class="record-main"><p class="kicker">Recorded appearances · matter {html.escape(_display(matter.get("matter_id")))}</p><p class="record-intro">Each entry keeps the title, meeting, body, placement, source, and available captured documents together. The links identify the source and capture boundary.</p><div class="appearance-list">{"".join(blocks)}</div><div class="surface boundary"><p>Page 47 reports public records. It does not determine why these changes were made.</p></div></main><footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Back to Page 47</a></footer>"""
    return _page(f"{title} — matter", body)


def _state_text(value: object) -> str:
    return {
        "clearer": "Clearer",
        "unchanged": "Unchanged",
        "less_clear": "Less clear",
        "mixed": "Mixed directions",
        "cannot_determine": "Could not determine",
    }.get(str(value), "Could not determine")


def finding_page(
    title: str, city: str, data: JSONObject, public_path: str, replay: bool = False
) -> str:
    decision = _as_dict(data.get("decision"))
    brief = _as_dict(data.get("brief"))
    case = _as_dict(data.get("case"))
    case_matter = _as_dict(case.get("matter"))
    appearances = _object_list(case.get("appearances"))
    drift = _as_dict(data.get("drift"))
    comparisons = _object_list(drift.get("comparisons"))
    latest = comparisons[-1] if comparisons and isinstance(comparisons[-1], dict) else {}
    observations = _object_list(latest.get("observations"))
    accepted = _object_list(decision.get("accepted"))
    rejected = _object_list(decision.get("rejected"))

    def observation_with_prefix(prefix: str) -> dict[str, JSONValue] | None:
        for item in observations:
            if (
                isinstance(item, dict)
                and isinstance(item.get("key"), str)
                and str(item["key"]).startswith(prefix)
            ):
                return item
        return None

    def appearance_by_id(value: object) -> dict[str, JSONValue] | None:
        for item in appearances:
            if isinstance(item, dict) and item.get("event_item_id") == value:
                return item
        return None

    def value_from(appearance: dict[str, JSONValue] | None, key: str) -> str:
        return _display(appearance.get(key)) if appearance is not None else "Could not determine"

    def placement_label(value: str) -> str:
        return {"regular": "Regular agenda", "consent": "Consent calendar"}.get(value, value)

    def direction_label(value: object) -> str:
        return {
            "clearer": "Clearer",
            "less_clear": "Less representative / less visible",
            "neutral": "No directional change",
        }.get(str(value), "Could not determine")

    def direction_class(value: object) -> str:
        return {"clearer": "clearer", "less_clear": "less-clear", "neutral": "neutral"}.get(
            str(value), "unknown"
        )

    def dimension(
        name: str,
        earlier: str,
        later: str,
        direction: object,
        evidence: object,
        note: str = "",
        wide: bool = False,
    ) -> str:
        note_html = f'<p class="note">{html.escape(note)}</p>' if note else ""
        wide_class = " dimension--wide" if wide else ""
        return f'<article class="dimension{wide_class}"><div class="dimension-heading"><h3>{html.escape(name)}</h3><span class="direction-chip {direction_class(direction)}">{html.escape(direction_label(direction))}</span></div><div class="comparison-values"><div><span>Earlier appearance</span><strong>{html.escape(earlier)}</strong></div><div><span>Later appearance</span><strong>{html.escape(later)}</strong></div></div>{note_html}<div class="evidence">{_evidence_markup(evidence, "Reconstructed from public record")}</div></article>'

    title_observation = observation_with_prefix("title")
    placement_observation = observation_with_prefix("agenda_placement")
    previous = appearance_by_id(latest.get("previous_event_item_id"))
    current = appearance_by_id(latest.get("current_event_item_id"))
    dimensions: list[str] = [
        dimension(
            "Title",
            value_from(previous, "title_as_presented"),
            value_from(current, "title_as_presented"),
            title_observation.get("direction") if title_observation else "neutral",
            title_observation.get("evidence") if title_observation else None,
            "A comparable title was not available for the latest pair."
            if title_observation is None
            else "",
        )
    ]
    dimensions.append(
        dimension(
            "Agenda placement",
            placement_label(value_from(previous, "pdf_placement")),
            placement_label(value_from(current, "pdf_placement")),
            placement_observation.get("direction") if placement_observation else "neutral",
            placement_observation.get("evidence") if placement_observation else None,
            "A supported agenda placement was not available for the latest pair."
            if placement_observation is None
            else "",
        )
    )
    substance_items: list[dict[str, JSONValue]] = [
        item
        for item in accepted
        if isinstance(item, dict)
        and isinstance(item.get("observation_id"), str)
        and str(item["observation_id"]).startswith("substance:")
    ]
    substance_blocks = [
        f'<li><p>{html.escape(_display(item.get("text"), "Recorded document change."))}</p><div class="evidence">{_evidence_markup(item.get("evidence"), "Reconstructed from public record")}</div></li>'
        for item in substance_items
    ]
    substance_html = (
        "<ul>" + "".join(substance_blocks) + "</ul>"
        if substance_blocks
        else '<p class="note">No comparable provision change survived the evidence review.</p>'
    )
    dimensions.append(
        f'<article class="dimension dimension--wide"><div class="dimension-heading"><h3>Document substance</h3><span class="direction-chip">Evidence detail</span></div><p class="note">Only captured document pages are used for this section.</p>{substance_html}</article>'
    )
    dimensions.append(
        '<article class="dimension dimension--wide"><div class="dimension-heading"><h3>Document timing</h3><span class="direction-chip unknown">Insufficient evidence</span></div><div class="comparison-values"><div><span>Status</span><strong>Unavailable</strong></div><div><span>Reason</span><strong>City timestamps do not prove public visibility.</strong></div></div><p class="note">Page 47 does not use ordinary last-modified values as directional evidence.</p></article>'
    )

    know_lines = _object_list(brief.get("lines"))
    know_blocks = [
        f'<li><p>{html.escape(_display(item.get("text"), "Supported observation."))}</p><div class="evidence">{_evidence_markup(item.get("evidence"), "Primary record")}</div></li>'
        for item in know_lines
        if isinstance(item, dict)
    ]
    know_html = (
        "<ul>" + "".join(know_blocks) + "</ul>"
        if know_blocks
        else '<p class="note">No observation survived review with a resident-facing evidence link.</p>'
    )

    timeline: list[tuple[str, str, str, int | None, str | None]] = []

    def add_timeline(value: object, fallback_origin: str) -> None:
        if not isinstance(value, list):
            return
        for item in value:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            captured_at = item.get("captured_at")
            if (
                not isinstance(url, str)
                or not url.startswith(("https://", "http://", "/"))
                or not isinstance(captured_at, str)
                or not captured_at
            ):
                continue
            page = item.get("page_number")
            page_number = page if isinstance(page, int) and not isinstance(page, bool) else None
            raw_hash = item.get("content_sha256") or item.get("response_sha256")
            content_hash = raw_hash if isinstance(raw_hash, str) and raw_hash else None
            if any(
                existing[0] == url
                and existing[1] == captured_at
                and existing[3] == page_number
                and existing[4] == content_hash
                for existing in timeline
            ):
                continue
            timeline.append(
                (
                    url,
                    captured_at,
                    _origin_label(item.get("origin"), fallback_origin),
                    page_number,
                    content_hash,
                )
            )

    if title_observation:
        add_timeline(title_observation.get("evidence"), "Reconstructed from public record")
    if placement_observation:
        add_timeline(placement_observation.get("evidence"), "Reconstructed from public record")
    for item in substance_items:
        add_timeline(item.get("evidence"), "Reconstructed from public record")
    timeline_blocks: list[str] = []
    for url, captured_at, origin, page_number, content_hash in sorted(
        timeline, key=lambda item: item[1]
    ):
        page_text = f" · PDF page {page_number}" if page_number is not None else ""
        hash_text = f" · SHA-256 {content_hash[:12]}…" if content_hash else ""
        href = f"{url}#page={page_number}" if page_number is not None else url
        timeline_blocks.append(
            f'<li><span class="origin-badge">{html.escape(origin)}</span><strong>{html.escape(captured_at)}</strong><span>{html.escape((page_text + hash_text) or "Primary record")}</span><a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">Open evidence ↗</a></li>'
        )
    timeline_html = (
        '<ol class="timeline">' + "".join(timeline_blocks) + "</ol>"
        if timeline_blocks
        else '<p class="note">No evidence timeline was retained for this finding.</p>'
    )

    rejected_blocks = [
        f'<article class="rejection"><h3>Rejected interpretation</h3><p class="rejection-id">{html.escape(_display(item.get("observation_id")))}</p><p>{html.escape(_display(item.get("reason"), "The supplied record did not support this interpretation."))}</p></article>'
        for item in rejected
        if isinstance(item, dict)
    ]
    rejected_html = (
        "".join(rejected_blocks)
        if rejected_blocks
        else '<p class="note">No rejected interpretation was recorded for this review.</p>'
    )
    state = decision.get("state")
    accepted_count = len(accepted)
    rejected_count = len(rejected)
    investigated_count = accepted_count + rejected_count
    heading = {
        "clearer": "This matter became more clearly presented",
        "less_clear": "This matter became less clearly presented",
        "mixed": "This matter changed in mixed directions",
        "unchanged": "This matter did not show a meaningful presentation change",
        "cannot_determine": "Page 47 could not determine the direction",
    }.get(str(state), "Page 47 review")
    explanation = _display(
        decision.get("reason"), "The saved public record did not support a stronger conclusion."
    )
    matter_title = _display(case_matter.get("current_title"), "Public matter")
    norm = _as_dict(data.get("norms"))
    norm_sentence = (
        _display(norm.get("human_timing_sentence"))
        if norm.get("human_timing_sentence")
        else "No comparable body-level context was available."
    )
    limitation = _display(
        brief.get("limitation"), "Page 47 does not determine why these changes were made."
    )
    raw_questions = brief.get("questions")
    questions = (
        [item for item in raw_questions if isinstance(item, str)]
        if isinstance(raw_questions, list)
        else []
    )
    questions_html = (
        '<ul class="question-list">'
        + "".join(f"<li>{html.escape(item)}</li>" for item in questions)
        + "</ul>"
        if questions
        else '<p class="note">No questions were recorded.</p>'
    )
    replay_html = (
        '<div class="replay-banner"><strong>Captured-case replay</strong><span>This review uses stored public records, not a live event.</span></div>'
        if replay
        else ""
    )
    actions: list[str] = []
    finding_id = data.get("finding_id")
    matter_id = data.get("matter_id")
    if replay and isinstance(finding_id, str):
        actions.append(
            f'<a href="{html.escape(_url(public_path, f"/finding/{city}/{finding_id}"), quote=True)}">Open the saved finding ↗</a>'
        )
    if isinstance(matter_id, int) and not isinstance(matter_id, bool):
        actions.append(
            f'<a href="{html.escape(_url(public_path, f"/matter/{city}/{matter_id}"), quote=True)}">View matter history ↗</a>'
        )
    actions_html = '<div class="detail-actions">' + "".join(actions) + "</div>" if actions else ""
    home_url = html.escape(_url(public_path, "/"), quote=True)
    body = f"""<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}</div></header><main class="detail-main">{replay_html}<section class="review-hero"><div><p class="breadcrumb"><a href="{home_url}">Page 47</a> / {html.escape(city)} / Evidence review</p><p class="review-matter">{html.escape(matter_title)} · matter {html.escape(_display(matter_id))}</p><h1>{html.escape(heading)}</h1><span class="state-chip">{html.escape(_state_text(state))}</span><p class="lead">{html.escape(explanation)}</p>{actions_html}</div><aside class="review-sidecar"><strong>{len(timeline)}</strong><span>evidence links retained</span><strong style="margin-top:20px">{accepted_count} / {rejected_count}</strong><span>supported / rejected</span></aside></section><section class="surface"><h2>The review at a glance</h2><p>Page 47 keeps the decision, evidence origin, and uncertainty visible so a reader can inspect the reasoning.</p><div class="glance-grid"><div class="glance-item"><strong>{len(timeline)}</strong><span>evidence links</span></div><div class="glance-item"><strong>{accepted_count}</strong><span>supported</span></div><div class="glance-item"><strong>{rejected_count}</strong><span>rejected after review</span></div></div></section><section class="surface"><h2>What changed</h2><p>Presentation dimensions stay separate so a change in one cannot cancel a change in another.</p><div class="dimensions">{"".join(dimensions)}</div></section><section class="surface facts"><h2>What Page 47 knows</h2>{know_html}</section><section class="surface"><h2>Evidence timeline</h2><p>Each entry identifies the evidence position. Historical comparisons may be reconstructed; captured document pages are marked separately.</p>{timeline_html}</section><section class="surface"><h2>Evidence review</h2><p>The Skeptic reviews the branch results before publication.</p><div class="review-counts"><div class="count"><strong>{accepted_count}</strong><span>supported</span></div><div class="count"><strong>{rejected_count}</strong><span>rejected</span></div><div class="count"><strong>{html.escape("Yes" if str(state) == "cannot_determine" else "No")}</strong><span>insufficient evidence</span></div></div>{rejected_html}</section><section class="surface"><h2>How this review was assembled</h2><p>Each role has a bounded evidence view. The Skeptic can reject an attractive interpretation, but cannot add facts or links.</p><p class="role-line"><span class="tag">Archivist</span> records appearances · <span class="tag">Substance</span> reads captured pages · <span class="tag">Process</span> reads title and placement · <span class="tag">Skeptic</span> accepts or rejects observations · <span class="tag">Brief Writer</span> returns resident questions.</p></section><section class="surface"><h2>What the public record normally shows</h2><p>{html.escape(norm_sentence)}</p></section><section class="surface"><h2>Questions worth asking</h2>{questions_html}</section><section class="surface boundary"><h2>What Page 47 cannot establish</h2><p>{html.escape(limitation)}</p><p class="note">Page 47 reports public records. It does not determine motive, legality, or a political position.</p></section></main><footer class="site-footer"><div class="footer-rule"></div>Review observations investigated: {investigated_count} · <a href="https://github.com/Jennycruzy/Page47">Source repository</a></footer>"""
    return _page(f"{title} — evidence review", body)


def watch_page(title: str, data: JSONObject, public_path: str) -> str:
    watch_id = _display(data.get("watch_id"))
    city = _display(data.get("city"))
    bodies = _json_list(data.get("bodies"))
    active = data.get("active") is True
    status = "Active" if active else "Stopped"
    area = (
        _display(data.get("neighbourhood"), "")
        or _display(data.get("address"), "")
        or "Could not determine"
    )
    home_url = html.escape(_url(public_path, "/"), quote=True)
    explore_url = html.escape(_url(public_path, "/explore"), quote=True)
    stop_action = (
        f'<button class="stop-button" id="stop-watch" type="button">Stop this watch</button><p id="watch-result" class="result" aria-live="polite"></p><script>const stopEndpoint={json.dumps(_url(public_path, f"/api/watches/{watch_id}/deactivate"))};document.querySelector("#stop-watch").onclick=async()=>{{const button=document.querySelector("#stop-watch");const result=document.querySelector("#watch-result");button.disabled=true;button.textContent="Stopping…";try{{const response=await fetch(stopEndpoint,{{method:"POST"}});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||"Could not stop this watch.");result.textContent=payload.message||"This watch is stopped.";document.querySelector("#watch-status").textContent="Stopped";document.querySelector("#watch-status").classList.add("stopped");button.remove();}}catch(error){{button.disabled=false;button.textContent="Stop this watch";result.textContent=error.message;}}}};</script>'
        if active
        else '<p class="form-help"><strong>This watch is stopped.</strong> No further review emails will be sent.</p>'
    )
    body_pills = "".join(
        f'<span class="body-pill">{html.escape(str(item))}</span>' for item in bodies
    )
    body = f"""<header class="inner-header"><div class="inner-wrap">{_site_nav(home_url, html.escape(_url(public_path, "/watch"), quote=True))}</div></header><main class="watch-main"><p class="breadcrumb"><a href="{home_url}">Page 47</a> / Private watch</p><p class="kicker">Private watch</p><h1 class="section-title">Page 47 is watching.</h1><p class="inner-lede" style="color:var(--muted)">This watch lives on the server. You do not need to keep this page open. When a supported change survives review, Page 47 can send an evidence-linked alert.</p><p id="watch-status" class="watch-status{" stopped" if not active else ""}">{status}</p><p style="margin-top:17px"><a href="{explore_url}">Read a captured review ↗</a></p><section class="surface"><h2>Watch details</h2><div class="watch-facts"><div class="watch-fact"><strong>City</strong><span>{html.escape(city)}</span></div><div class="watch-fact"><strong>Area</strong><span>{html.escape(area)}</span></div><div class="watch-fact"><strong>Created</strong><span>{html.escape(_display(data.get("created_at"), "Not recorded"))}</span></div><div class="watch-fact"><strong>Last successful collector check</strong><span>{html.escape(_display(data.get("last_successful_check"), "Not recorded"))}</span></div><div class="watch-fact"><strong>Reviews delivered</strong><span>{html.escape(_display(data.get("reviews_delivered"), "0"))}</span></div><div class="watch-fact"><strong>Status</strong><span>{status}</span></div></div></section><section class="surface"><h2>Public bodies monitored</h2><div class="body-pills">{body_pills or '<span class="form-help">No public bodies recorded.</span>'}</div></section><section class="surface"><h2>Manage this watch</h2><p>Keep this private link private. It is the control for this watch.</p>{stop_action}</section></main><footer class="site-footer"><div class="footer-rule"></div><a href="{home_url}">Back to Page 47</a> · Page 47 does not determine motive or tell you what position to take.</footer>"""
    return _page(f"{title} — private watch", body)
