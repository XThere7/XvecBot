#!/usr/bin/env python3
"""End-to-end verification for the public BotBase documentation.

Run this from the repository root with the API and Next.js dev servers up:

    python3 docs-tests/verify_docs.py

Useful overrides:

    DOCS_BASE_URL=http://localhost:3000 \
    BOTBASE_API_URL=http://127.0.0.1:8000 \
    python3 docs-tests/verify_docs.py

The harness checks real rendered pages in Chromium as well as the authored
files. It creates a throwaway trial account/workspace/agent/API key so the
developer examples on the pages can be executed exactly as rendered, then
deletes the workspace. No credential is printed or written to disk.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree

import requests
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "BaseBot_UI"
DOCS_ROOT = UI_ROOT / "src" / "content" / "docs" / "en"
DOCS_CSS = UI_ROOT / "src" / "app" / "docs" / "docs.css"
SEARCH_COMPONENT = UI_ROOT / "src" / "components" / "docs" / "docs-search.tsx"
LANDING_NAV = UI_ROOT / "src" / "components" / "landing" / "landing-nav.ts"
SIDEBAR_NAV = UI_ROOT / "src" / "components" / "layout" / "sidebar-nav.tsx"

DEFAULT_DOCS_BASE = os.environ.get("DOCS_BASE_URL", "http://localhost:3000")
DEFAULT_API_BASE = os.environ.get("BOTBASE_API_URL", "http://127.0.0.1:8000")

REQUIRED_GROUPS = [
    "Get started",
    "Knowledge",
    "Agents & Models",
    "Deploy",
    "Account & Workspace",
    "Developer",
    "Help",
]
PLANNED_FEATURES = [
    "WhatsApp",
    "lead forms",
    "email integration",
    "lead qualification",
    "custom actions",
    "automations",
    "custom branding",
    "advanced analytics",
    "team member invitations",
    "self-serve paid upgrades",
]
MODEL_LABELS = [
    "Llama 3.1 8B Instruct",
    "Auto",
    "Llama 3.3 70B Instruct",
    "Qwen3 235B A22B",
    "Gemma 3 27B IT",
    "Free",
]
RAW_MODEL_RE = re.compile(
    r"\b(?:meta-llama|openrouter|qwen|google|inclusionai)/[A-Za-z0-9._:/+-]+"
)
SECRET_RE = re.compile(r"(?:sk-botbase-[A-Za-z0-9_-]{12,}|sk-or-v1-[A-Za-z0-9_-]{12,})")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class Check:
    section: str
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class Page:
    path: Path
    slug: tuple[str, ...]
    href: str
    title: str
    description: str
    group: str
    order: int
    body: str


@dataclass
class ApiFixture:
    email: str
    password: str
    api_base: str
    token: str
    workspace_id: str
    agent_id: str
    api_key: str

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class Runner:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.section = "general"

    def heading(self, name: str) -> None:
        self.section = name
        print(f"\n{name}")

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        result = Check(self.section, name, bool(ok), detail.strip())
        self.checks.append(result)
        marker = "PASS" if result.ok else "FAIL"
        suffix = f" — {detail.strip()}" if detail.strip() else ""
        print(f"  [{marker}] {name}{suffix}")
        return result.ok

    def summary(self) -> int:
        failed = [check for check in self.checks if not check.ok]
        passed = len(self.checks) - len(failed)
        print("\n" + "=" * 78)
        print(f"RESULT: {passed} passed, {len(failed)} failed, {len(self.checks)} total")
        if failed:
            print("\nFailures:")
            for check in failed:
                print(f"  - [{check.section}] {check.name}")
                if check.detail:
                    for line in check.detail.splitlines()[:8]:
                        print(f"      {line}")
            print("=" * 78)
            return 1
        print("All documentation checks passed.")
        print("=" * 78)
        return 0


def wait_for_http(url: str, timeout: float = 180.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def read_pages() -> list[Page]:
    pages: list[Page] = []
    for path in sorted(DOCS_ROOT.rglob("*.md*")):
        if path.suffix not in {".md", ".mdx"}:
            continue
        raw = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
        if not match:
            raise ValueError(f"missing frontmatter: {path}")
        data = yaml.safe_load(match.group(1)) or {}
        rel = path.relative_to(DOCS_ROOT).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "index":
            parts.pop()
        slug = tuple(parts)
        pages.append(
            Page(
                path=path,
                slug=slug,
                href="/docs" + ("/" + "/".join(slug) if slug else ""),
                title=str(data["title"]).strip(),
                description=str(data["description"]).strip(),
                group=str(data["group"]).strip(),
                order=int(data["order"]),
                body=match.group(2).strip(),
            )
        )
    return sorted(pages, key=lambda page: (page.order, page.href))


def normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def source_text(page: Page) -> str:
    text = page.body
    text = re.sub(r"<CodeTabs[\s\S]*?/>", " ", text)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def plain_lower(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def parse_css_vars(block: str) -> dict[str, str]:
    return {
        name: value
        for name, value in re.findall(
            r"(--docs-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})", block
        )
    }


def relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        [relative_luminance(foreground), relative_luminance(background)],
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def hue_for(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    red, green, blue = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    return colorsys.rgb_to_hls(red, green, blue)[0] * 360


def clean_output(value: str, limit: int = 500) -> str:
    value = SECRET_RE.sub("[redacted]", value)
    value = re.sub(r"sk-botbase-[A-Za-z0-9_.-]+", "sk-botbase-[redacted]", value)
    return value.replace("\n", " ")[:limit]


def make_driver(headed: bool = False) -> webdriver.Chrome:
    options = Options()
    chromium = os.environ.get("CHROMIUM_BIN") or shutil.which("chromium") or shutil.which(
        "chromium-browser"
    ) or shutil.which("google-chrome")
    if not chromium:
        raise RuntimeError("Chromium was not found; set CHROMIUM_BIN.")
    options.binary_location = chromium
    if not headed:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1000")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver_path = os.environ.get("CHROMEDRIVER") or shutil.which("chromedriver")
    service = Service(driver_path) if driver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(180)
    return driver


def wait_docs_page(driver: webdriver.Chrome, url: str | None = None, timeout: float = 180) -> None:
    if url:
        driver.get(url)
    WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(
            "return Boolean(document.querySelector('.docs-article h1'))"
        )
    )
    WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(
            "return (document.querySelector('.docs-prose')?.innerText || '').trim().length > 80"
        )
    )


def browser_console_errors(driver: webdriver.Chrome) -> list[str]:
    errors: list[str] = []
    for entry in driver.get_log("browser"):
        if entry.get("level") == "SEVERE":
            message = clean_output(entry.get("message", ""), 240)
            if message:
                errors.append(message)
    return errors


def test_source_content(runner: Runner, pages: list[Page], docs_base: str) -> None:
    runner.heading("Content structure and product truth")
    runner.check(
        "Content is stored under a locale directory",
        DOCS_ROOT.is_dir() and DOCS_ROOT.name == "en",
        str(DOCS_ROOT.relative_to(ROOT)),
    )

    missing = []
    for page in pages:
        for field in ("title", "description", "group"):
            if not getattr(page, field):
                missing.append(f"{page.path.name}:{field}")
    runner.check("Every page has title, description, group and numeric order", not missing, ", ".join(missing))
    runner.check(
        "Page URLs and frontmatter titles are unique",
        len({page.href for page in pages}) == len(pages)
        and len({page.title for page in pages}) == len(pages)
        and len({page.description for page in pages}) == len(pages),
    )
    runner.check("Documentation has the 34 planned pages", len(pages) == 34, f"{len(pages)} pages")

    groups = {page.group for page in pages}
    runner.check(
        "Required information architecture is present",
        set(REQUIRED_GROUPS) <= groups,
        f"groups={sorted(groups)}",
    )
    runner.check(
        "Required entry and reference pages exist",
        {
            "/docs",
            "/docs/get-started",
            "/docs/knowledge",
            "/docs/agents",
            "/docs/deploy",
            "/docs/account",
            "/docs/developer",
            "/docs/help/faq",
            "/docs/deploy/coming-soon",
        }
        <= {page.href for page in pages},
    )

    source_blob = "\n".join(page.body for page in pages)
    rendered_blob = "\n".join(source_text(page) for page in pages)
    runner.check(
        "Customer-facing content never uses the obsolete XvecBot name",
        "XvecBot" not in source_blob and "Xvec" not in source_blob,
    )
    raw_models = sorted(set(RAW_MODEL_RE.findall(source_blob)))
    runner.check("Raw provider model IDs are absent", not raw_models, ", ".join(raw_models))
    secrets = sorted(set(SECRET_RE.findall(source_blob)))
    runner.check("No API-key-shaped secrets are embedded in content", not secrets, ", ".join(secrets))

    models_page = next(page for page in pages if page.href == "/docs/agents/models")
    model_text = source_text(models_page)
    runner.check(
        "All six customer-facing model labels are documented",
        all(label in model_text for label in MODEL_LABELS),
        ", ".join(label for label in MODEL_LABELS if label not in model_text),
    )
    runner.check(
        "Named free models are disclosed as currently unavailable",
        "currently marked unavailable" in model_text.lower(),
    )

    plans = plain_lower(next(page for page in pages if page.href == "/docs/account/plans").body)
    account = plain_lower(next(page for page in pages if page.href == "/docs/account").body)
    coming_soon = plain_lower(
        next(page for page in pages if page.href == "/docs/deploy/coming-soon").body
    )
    truth_checks = {
        "21-day Pro trial is stated": "21-day" in plans or "21 days" in plans,
        "TZS prices are stated": "tzs 7,800" in plans and "tzs 15,800" in plans,
        "Paid self-service upgrades are disclosed as unavailable": (
            "payments are not connected yet" in plans
            and "paid upgrades are not live" in plans
        ),
        "All planned-only capabilities are listed": all(
            feature.lower() in coming_soon for feature in PLANNED_FEATURES
        ),
        "The docs explain that member invitations are unavailable": (
            "team member invitations" in coming_soon
            and "not implemented" in coming_soon
        ),
        "The 21-day trial has no card": "no card" in plans,
        "The account page documents self-service password reset": (
            "self-service reset" in account
            and "/forgot-password" in account
        ),
        "API rate limits are stated": bool(
            re.search(r"60 requests per minute per (?:API )?key", rendered_blob, re.I)
        ),
        "Developer endpoint names are documented": (
            "/api/v1/agents" in source_blob and "/api/v1/chat" in source_blob
        ),
        "Widget and hosted deployment are documented": (
            "/docs/deploy/widget" in source_blob
            and "/docs/deploy/hosted-chat" in source_blob
            and "/docs/deploy/qr" in source_blob
        ),
        "Streaming is documented as unavailable": bool(
            re.search(r"streaming is (?:not supported|not available)", rendered_blob, re.I)
        ),
    }
    for name, condition in truth_checks.items():
        runner.check(name, condition)

    search_source = SEARCH_COMPONENT.read_text(encoding="utf-8")
    runner.check(
        "Search is local and same-origin",
        'fetch("/docs/search-index.json")' in search_source
        and not re.search(r"algolia|typesense|meilisearch|api\.openai", search_source, re.I),
    )
    landing = LANDING_NAV.read_text(encoding="utf-8")
    sidebar = SIDEBAR_NAV.read_text(encoding="utf-8")
    runner.check(
        "Public and dashboard navigation both include Docs",
        'href: "/docs"' in landing and 'href: "/docs"' in sidebar,
    )
    runner.check(
        "Dashboard Docs entry is explicitly external/new-tab",
        'label: "Docs"' in sidebar
        and 'external: true' in sidebar
        and 'target={item.external ? "_blank" : undefined}' in sidebar
        and 'rel={item.external ? "noopener" : undefined}' in sidebar,
    )
    for label, rel_path in [
        ("Model selector", "src/components/agents/model-select.tsx"),
        ("Embed panel", "src/components/embed/embed-panel.tsx"),
        ("Developer panel", "src/components/developer/developer-panel.tsx"),
    ]:
        component = (UI_ROOT / rel_path).read_text(encoding="utf-8")
        runner.check(
            f"{label} has a contextual Learn more docs link",
            "Learn more" in component and 'href="/docs/' in component,
        )

    runner.check(
        "Content paths are visible in the rendered docs nav",
        "Documentation" in requests.get(docs_base + "/docs", timeout=60).text,
    )


def test_static_routes(runner: Runner, pages: list[Page], docs_base: str, api_base: str) -> None:
    runner.heading("Public routes, SEO and API regression")
    docs_home = requests.get(docs_base + "/docs", timeout=90)
    runner.check(
        "Public /docs is available without authentication",
        docs_home.status_code == 200
        and docs_home.url.rstrip("/").endswith("/docs")
        and "Sign in" not in docs_home.text,
        f"status={docs_home.status_code}",
    )

    index_response = requests.get(docs_base + "/docs/search-index.json", timeout=90)
    try:
        index = index_response.json()
    except ValueError:
        index = []
    runner.check(
        "Search index is a static JSON route for every page",
        index_response.status_code == 200
        and "application/json" in index_response.headers.get("content-type", "")
        and {item.get("href") for item in index} == {page.href for page in pages},
        f"status={index_response.status_code}, items={len(index)}",
    )
    index_blob = json.dumps(index, ensure_ascii=False)
    runner.check(
        "Search index does not contain raw model IDs or secrets",
        not RAW_MODEL_RE.findall(index_blob) and not SECRET_RE.findall(index_blob),
    )

    sitemap_response = requests.get(docs_base + "/docs/sitemap.xml", timeout=90)
    sitemap_locs: set[str] = set()
    try:
        root = ElementTree.fromstring(sitemap_response.text)
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_locs = {
            normalize_path(urlparse(node.text or "").path)
            for node in root.findall("s:url/s:loc", namespace)
        }
    except ElementTree.ParseError:
        pass
    runner.check(
        "Docs sitemap lists all pages and nothing else",
        sitemap_response.status_code == 200
        and "xml" in sitemap_response.headers.get("content-type", "")
        and sitemap_locs == {page.href for page in pages},
        f"status={sitemap_response.status_code}, urls={len(sitemap_locs)}",
    )

    llms_response = requests.get(docs_base + "/docs/llms.txt", timeout=90)
    llms = llms_response.text
    runner.check(
        "llms.txt is available and links every page",
        llms_response.status_code == 200
        and "text/plain" in llms_response.headers.get("content-type", "")
        and all(page.href in llms for page in pages),
        f"status={llms_response.status_code}",
    )
    runner.check(
        "llms.txt uses customer-facing model names only",
        "Standard, Auto" not in llms
        and all(label in llms for label in MODEL_LABELS)
        and not RAW_MODEL_RE.findall(llms),
    )
    runner.check(
        "llms.txt states that planned features are not available",
        "Not yet available" in llms
        and "WhatsApp integration" in llms
        and "team member invitations" in llms,
    )

    not_found = requests.get(docs_base + "/docs/this-page-does-not-exist", timeout=60)
    runner.check("Unknown docs URLs return 404", not_found.status_code == 404, f"status={not_found.status_code}")

    landing = requests.get(docs_base + "/", timeout=90)
    landing_docs = BeautifulSoup(landing.text, "html.parser").select('a[href="/docs"]')
    runner.check(
        "Public landing navigation links to Docs",
        landing.status_code == 200 and len(landing_docs) >= 1,
        f"links={len(landing_docs)}",
    )

    backend_docs = requests.get(api_base + "/docs", timeout=90)
    runner.check(
        "Backend FastAPI Swagger remains at /docs",
        backend_docs.status_code == 200 and "swagger" in backend_docs.text.lower(),
        f"status={backend_docs.status_code}",
    )
    health = requests.get(api_base + "/api/v1/health", timeout=30)
    runner.check(
        "Developer API health endpoint still responds",
        health.status_code == 200 and health.json().get("status") == "ok",
        f"status={health.status_code}",
    )
    unauthenticated = requests.get(api_base + "/api/v1/agents", timeout=30)
    try:
        unauthenticated_body = unauthenticated.json()
    except ValueError:
        unauthenticated_body = {}
    runner.check(
        "Developer API authentication errors keep the flat error contract",
        unauthenticated.status_code == 401
        and isinstance(unauthenticated_body.get("error"), str)
        and "detail" not in unauthenticated_body,
        f"status={unauthenticated.status_code}",
    )


def test_brand_and_contrast(runner: Runner, docs_base: str) -> None:
    runner.heading("Brand palette, favicon and WCAG contrast")
    css = DOCS_CSS.read_text(encoding="utf-8")
    try:
        light_block = css.split(".docs-root {", 1)[1].split("}", 1)[0]
        dark_start = css.index('html[data-docs-theme="dark"] .docs-root')
        dark_block = css[dark_start:].split("{", 1)[1].split("}", 1)[0]
    except (IndexError, ValueError):
        light_block = dark_block = ""
    light = parse_css_vars(light_block)
    dark = parse_css_vars(dark_block)

    brand_steps = [50, *range(100, 1000, 100)]
    brand = {f"brand-{step}": light.get(f"--docs-brand-{step}") for step in brand_steps}
    runner.check(
        "The 50–900 brand ramp is complete and sampled from the seed",
        all(brand.values())
        and brand["brand-500"].lower() == "#7c84f4"
        and len([value for value in brand.values() if value]) == 10,
        ", ".join(f"{key}={value}" for key, value in brand.items()),
    )
    hues = [hue_for(value) for value in brand.values() if value]
    runner.check(
        "The ramp stays in the faded-purple hue family",
        len(hues) == 10 and min(hues) >= 230 and max(hues) <= 250,
        f"hue range {min(hues):.1f}–{max(hues):.1f}",
    )

    pairs = [
        ("body text", "text", "bg"),
        ("secondary text", "text-secondary", "bg"),
        ("tertiary text", "text-tertiary", "bg"),
        ("link", "link", "bg"),
        ("button", "button-text", "button-bg"),
        ("note callout", "note-text", "note-bg"),
        ("tip callout", "tip-text", "tip-bg"),
        ("warning callout", "warning-text", "warning-bg"),
        ("danger callout", "danger-text", "danger-bg"),
        ("code text", "code-text", "code-bg"),
        ("code muted text", "code-muted", "code-bg"),
    ]
    ratios: dict[str, float] = {}
    for theme_name, variables in (("light", light), ("dark", dark)):
        for label, foreground, background in pairs:
            fg = variables.get(f"--docs-{foreground}", "")
            bg = variables.get(f"--docs-{background}", "")
            if HEX_RE.match(fg) and HEX_RE.match(bg):
                ratios[f"{theme_name} {label}"] = contrast_ratio(fg, bg)
    runner.check(
        "Every checked text pair meets WCAG AA (4.5:1)",
        len(ratios) == len(pairs) * 2 and min(ratios.values()) >= 4.5,
        f"min={min(ratios.values()):.2f}; " + ", ".join(
            f"{name}={value:.2f}" for name, value in list(ratios.items())[:4]
        ),
    )

    favicon_response = requests.get(docs_base + "/favicon.svg", timeout=30)
    page = requests.get(docs_base + "/docs", timeout=90).text
    soup = BeautifulSoup(page, "html.parser")
    icon_link = soup.select_one('link[rel="icon"]')
    runner.check(
        "The real BotBase favicon is linked and served",
        favicon_response.status_code == 200
        and "<svg" in favicon_response.text
        and icon_link is not None
        and "favicon.svg" in (icon_link.get("href") or ""),
        f"status={favicon_response.status_code}",
    )
    runner.check(
        "The docs header uses the real BotBase vector mark",
        len(soup.select(".docs-brand svg")) >= 1,
    )


def crawl_rendered_pages(
    runner: Runner,
    driver: webdriver.Chrome,
    pages: list[Page],
    docs_base: str,
) -> None:
    runner.heading("Rendered docs pages, navigation, metadata and links")
    expected = {page.href for page in pages}
    failures: list[str] = []
    titles: list[str] = []
    descriptions: list[str] = []
    canonical_paths: list[str] = []
    ids_by_path: dict[str, set[str]] = {}
    links_by_path: dict[str, set[str]] = {}
    console_errors: dict[str, list[str]] = {}
    body_lengths: dict[str, int] = {}
    component_counts: dict[str, dict[str, int]] = {}

    for page in pages:
        url = docs_base + page.href
        try:
            driver.get_log("browser")
            wait_docs_page(driver, url)
            h1 = driver.find_element(By.CSS_SELECTOR, ".docs-article h1").text.strip()
            body_text = driver.find_element(By.CSS_SELECTOR, ".docs-prose").text.strip()
            title = driver.title.strip()
            description = (
                driver.find_element(By.CSS_SELECTOR, 'meta[name="description"]').get_attribute(
                    "content"
                )
                or ""
            ).strip()
            canonical = (
                driver.find_element(By.CSS_SELECTOR, 'link[rel="canonical"]').get_attribute(
                    "href"
                )
                or ""
            )
            ids = set(
                driver.execute_script(
                    "return Array.from(document.querySelectorAll('.docs-root [id]')).map(el => el.id).filter(Boolean)"
                )
                or []
            )
            links = set(
                driver.execute_script(
                    "return Array.from(document.querySelectorAll('.docs-root a[href]')).map(a => a.getAttribute('href')).filter(Boolean)"
                )
                or []
            )
            toc_targets = driver.execute_script(
                "return Array.from(document.querySelectorAll('.docs-toc a[href^=\"#\"]')).map(a => decodeURIComponent(a.getAttribute('href').slice(1)))"
            ) or []
            breadcrumb = driver.execute_script(
                "return {nav: Boolean(document.querySelector('.docs-breadcrumbs')), links: document.querySelectorAll('.docs-breadcrumbs a').length, text: (document.querySelector('.docs-breadcrumbs')?.innerText || '').trim()}"
            )
            pagination_links = driver.execute_script(
                "return document.querySelectorAll('.docs-pagination a[href]').length"
            )
            counts = driver.execute_script(
                "return {callouts: document.querySelectorAll('.docs-callout').length, cards: document.querySelectorAll('.docs-card').length, steps: document.querySelectorAll('.docs-step').length, tables: document.querySelectorAll('.docs-table-wrap table').length}"
            )
            if page.href == "/docs":
                if h1 != "BotBase documentation":
                    failures.append(f"{page.href}: unexpected home h1 {h1!r}")
            elif h1 != page.title:
                failures.append(f"{page.href}: h1 {h1!r} != {page.title!r}")
            if len(body_text) < 80:
                failures.append(f"{page.href}: rendered prose is empty")
            if not title:
                failures.append(f"{page.href}: missing <title>")
            if not description:
                failures.append(f"{page.href}: missing meta description")
            canonical_path = normalize_path(urlparse(canonical).path) if canonical else ""
            if canonical_path != normalize_path(page.href):
                failures.append(f"{page.href}: canonical {canonical_path!r}")
            missing_toc = [target for target in toc_targets if target not in ids]
            if missing_toc:
                failures.append(f"{page.href}: TOC targets missing {missing_toc[:3]}")
            if not breadcrumb.get("nav"):
                failures.append(f"{page.href}: breadcrumb nav missing")
            elif page.href != "/docs":
                crumbs = breadcrumb.get("text", "")
                if breadcrumb.get("links", 0) < 1:
                    failures.append(f"{page.href}: breadcrumb home link missing")
                if page.group != "Home" and page.group not in crumbs:
                    failures.append(f"{page.href}: breadcrumb group missing")
                if page.title not in crumbs:
                    failures.append(f"{page.href}: breadcrumb current page missing")
            if pagination_links < 1:
                failures.append(f"{page.href}: previous/next pagination missing")
            errors = browser_console_errors(driver)
            if errors:
                console_errors[page.href] = errors
            body_lengths[page.href] = len(body_text)
            component_counts[page.href] = counts
            titles.append(title)
            descriptions.append(description)
            canonical_paths.append(canonical_path)
            ids_by_path[page.href] = ids
            links_by_path[page.href] = links
        except Exception as exc:  # noqa: BLE001 - report one page without aborting the rest
            failures.append(f"{page.href}: {type(exc).__name__}: {clean_output(str(exc), 180)}")

    if len(titles) != len(set(titles)):
        failures.append("page titles are not unique")
    if len(descriptions) != len(set(descriptions)):
        failures.append("meta descriptions are not unique")
    if set(canonical_paths) != expected:
        failures.append("canonical URL set does not match page set")
    if console_errors:
        page_name, messages = next(iter(console_errors.items()))
        failures.append(f"browser console errors on {page_name}: {messages[0]}")
    if len(body_lengths) != len(pages):
        failures.append(f"only {len(body_lengths)}/{len(pages)} pages had a rendered body")

    short_pages = [path for path, length in body_lengths.items() if length < 80]
    missing_pages = len(pages) - len(body_lengths)
    runner.check(
        "All docs pages render prose (not an empty Suspense boundary)",
        missing_pages == 0 and not short_pages,
        f"short={short_pages[:5]}, missing={missing_pages}"
        if missing_pages or short_pages
        else "",
    )
    runner.check(
        "Every page has unique title, description and canonical URL",
        not any("canonical" in item or "title" in item or "description" in item for item in failures)
        and len(canonical_paths) == len(pages),
        "; ".join(
            item
            for item in failures
            if "canonical" in item or "title" in item or "description" in item
        )[:500],
    )
    heading_failures = [
        item
        for item in failures
        if " h1 " in item or "TOC targets" in item
    ]
    runner.check(
        "Every page renders its authored H1 and working in-page TOC anchors",
        not heading_failures,
        "; ".join(heading_failures[:5]),
    )
    navigation_failures = [
        item
        for item in failures
        if "breadcrumb" in item or "pagination" in item
    ]
    runner.check(
        "Every page has breadcrumbs and previous/next navigation",
        not navigation_failures,
        "; ".join(navigation_failures[:5]),
    )
    totals = {
        key: sum(page_counts.get(key, 0) for page_counts in component_counts.values())
        for key in ("callouts", "cards", "steps", "tables")
    }
    runner.check(
        "Cards, steps, callouts and tables are rendered in the docs",
        totals["callouts"] >= 10
        and totals["cards"] >= 4
        and totals["steps"] >= 4
        and totals["tables"] >= 10,
        ", ".join(f"{key}={value}" for key, value in totals.items()),
    )
    runner.check(
        "Rendered pages have no severe browser console errors",
        not console_errors,
        next(iter(console_errors.items()))[0] if console_errors else "",
    )

    broken_links: list[str] = []
    checked_links = 0
    for source, links in links_by_path.items():
        for raw_href in links:
            resolved = urljoin(docs_base + source, raw_href)
            parsed = urlparse(resolved)
            if parsed.netloc and parsed.netloc not in urlparse(docs_base).netloc:
                continue
            path = normalize_path(parsed.path)
            if not path.startswith("/docs"):
                continue
            checked_links += 1
            if path in {"/docs/search-index.json", "/docs/sitemap.xml", "/docs/llms.txt"}:
                continue
            if path not in expected:
                broken_links.append(f"{source} -> {raw_href} (unknown page)")
                continue
            fragment = unquote(parsed.fragment)
            if fragment and fragment not in ids_by_path.get(path, set()):
                broken_links.append(f"{source} -> {raw_href} (missing anchor #{fragment})")
    runner.check(
        "Every internal docs link and anchor resolves",
        not broken_links,
        f"checked={checked_links}; " + "; ".join(broken_links[:5]),
    )

    desktop = driver.execute_script(
        "return {sidebar: getComputedStyle(document.querySelector('.docs-sidebar')).display, toc: getComputedStyle(document.querySelector('.docs-toc')).display, width: innerWidth}"
    )
    runner.check(
        "Desktop layout exposes sidebar navigation and right-rail TOC",
        desktop["sidebar"] != "none"
        and desktop["toc"] != "none"
        and desktop["width"] >= 1024,
        str(desktop),
    )


def test_search_and_interactions(runner: Runner, driver: webdriver.Chrome, docs_base: str) -> None:
    runner.heading("Search, theme, code copy and mobile drawer")
    driver.set_window_size(1440, 1000)
    wait_docs_page(driver, docs_base + "/docs")
    body = driver.find_element(By.TAG_NAME, "body")
    body.send_keys(Keys.CONTROL, "k")
    try:
        WebDriverWait(driver, 10).until(
            lambda current: len(current.find_elements(By.CSS_SELECTOR, ".docs-search-dialog")) == 1
        )
        opened = True
    except WebDriverException:
        opened = False
    runner.check("Ctrl/Cmd + K opens the search dialog", opened)
    if not opened:
        return

    expected_rankings = {
        "widget": "/docs/deploy/widget",
        "trial": "/docs/account/plans",
        "API key": "/docs/account/credentials",
        "QR": "/docs/deploy/qr",
        "model": "/docs/agents/models",
    }
    ranking_failures: list[str] = []
    for query, expected_path in expected_rankings.items():
        search_input = driver.find_element(By.CSS_SELECTOR, ".docs-search-input")
        search_input.send_keys(Keys.CONTROL, "a")
        search_input.send_keys(query)
        time.sleep(0.25)
        try:
            WebDriverWait(driver, 10).until(
                lambda current: len(current.find_elements(By.CSS_SELECTOR, ".docs-search-result")) > 0
            )
            first = driver.find_element(By.CSS_SELECTOR, ".docs-search-result")
            first_path = normalize_path(urlparse(first.get_attribute("href")).path)
        except WebDriverException:
            first_path = ""
        if first_path != expected_path:
            ranking_failures.append(f"{query!r}: {first_path or 'no result'} (expected {expected_path})")
    runner.check(
        "Search ranks the canonical guide first for key terms",
        not ranking_failures,
        "; ".join(ranking_failures),
    )

    body = driver.find_element(By.TAG_NAME, "body")
    body.send_keys(Keys.ESCAPE)
    WebDriverWait(driver, 10).until(
        lambda current: len(current.find_elements(By.CSS_SELECTOR, ".docs-search-dialog")) == 0
    )
    runner.check("Escape closes the search dialog", True)

    # System preference should drive a first visit, and the docs toggle must
    # persist only under its own key.
    try:
        driver.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": "dark"}]},
        )
    except WebDriverException:
        pass
    driver.get(docs_base + "/docs")
    driver.execute_script(
        "localStorage.removeItem('botbase-docs-theme'); localStorage.removeItem('botbase-theme');"
    )
    driver.refresh()
    wait_docs_page(driver)
    time.sleep(0.3)
    dark_bg = driver.execute_script(
        "return getComputedStyle(document.querySelector('.docs-root')).backgroundColor"
    )
    theme_button = driver.find_element(By.CSS_SELECTOR, "[data-docs-theme-toggle]")
    dark_pressed = theme_button.get_attribute("aria-pressed")
    theme_button.click()
    WebDriverWait(driver, 10).until(
        lambda current: current.execute_script(
            "return document.documentElement.dataset.docsTheme === 'light'"
        )
    )
    light_bg = driver.execute_script(
        "return getComputedStyle(document.querySelector('.docs-root')).backgroundColor"
    )
    stored_theme = driver.execute_script(
        "return localStorage.getItem('botbase-docs-theme')"
    )
    dashboard_theme = driver.execute_script(
        "return localStorage.getItem('botbase-theme')"
    )
    driver.refresh()
    wait_docs_page(driver)
    persisted = driver.execute_script(
        "return {theme: document.documentElement.dataset.docsTheme, stored: localStorage.getItem('botbase-docs-theme')}"
    )
    runner.check(
        "Docs default to the OS colour scheme and toggle independently",
        dark_bg == "rgb(18, 16, 23)"
        and dark_pressed == "true"
        and light_bg == "rgb(251, 250, 252)"
        and stored_theme == "light"
        and dashboard_theme is None
        and persisted["theme"] == "light"
        and persisted["stored"] == "light",
        f"dark={dark_bg}, light={light_bg}, stored={stored_theme}, dashboard={dashboard_theme}",
    )

    wait_docs_page(driver, docs_base + "/docs/developer/list-agents")
    code_copy = driver.find_element(By.CSS_SELECTOR, ".docs-code-copy")
    driver.execute_script("arguments[0].click()", code_copy)
    try:
        WebDriverWait(driver, 5).until(
            lambda current: "Copied" in current.find_element(By.CSS_SELECTOR, ".docs-code-copy").text
        )
        copied = True
    except WebDriverException:
        copied = False
    runner.check("Code blocks expose a working copy button", copied)

    python_tab = None
    for tab in driver.find_elements(By.CSS_SELECTOR, ".docs-tab"):
        if tab.text.strip() == "Python":
            python_tab = tab
            break
    switched = False
    if python_tab:
        driver.execute_script("arguments[0].click()", python_tab)
        WebDriverWait(driver, 5).until(
            lambda current: current.find_element(By.CSS_SELECTOR, '.docs-tab[aria-selected="true"]').text.strip()
            == "Python"
        )
        panel_code = driver.find_element(
            By.CSS_SELECTOR, ".docs-tabs [role='tabpanel'] code"
        ).text
        switched = "urllib.request" in panel_code
    runner.check("cURL/Python/JavaScript tabs switch their code panel", switched)

    driver.set_window_size(390, 844)
    wait_docs_page(driver, docs_base + "/docs")
    time.sleep(0.3)
    sidebar = driver.find_element(By.CSS_SELECTOR, ".docs-sidebar")
    menu = driver.find_element(
        By.CSS_SELECTOR, "button[aria-label='Open documentation navigation']"
    )
    menu_visible = menu.is_displayed()
    driver.execute_script("arguments[0].click()", menu)
    WebDriverWait(driver, 10).until(
        lambda current: len(current.find_elements(By.CSS_SELECTOR, ".docs-sidebar-drawer")) == 1
    )
    drawer = driver.find_element(By.CSS_SELECTOR, ".docs-sidebar-drawer")
    drawer_has_link = any(
        link.is_displayed() and link.text.strip() for link in drawer.find_elements(By.CSS_SELECTOR, ".docs-nav-link")
    )
    overflow = driver.execute_script(
        "return document.documentElement.scrollWidth - window.innerWidth"
    )
    close = drawer.find_element(
        By.CSS_SELECTOR, "button[aria-label='Close documentation navigation']"
    )
    close.click()
    runner.check(
        "390px layout hides the sidebar, opens the nav drawer and avoids overflow",
        not sidebar.is_displayed()
        and menu_visible
        and drawer_has_link
        and overflow <= 1,
        f"overflow={overflow}px",
    )
    driver.set_window_size(1440, 1000)


def extract_code_tabs(driver: webdriver.Chrome, docs_base: str, path: str) -> dict[str, str]:
    wait_docs_page(driver, docs_base + path)
    tabs: dict[str, str] = {}
    buttons = driver.find_elements(By.CSS_SELECTOR, ".docs-tabs .docs-tab")
    for button in buttons:
        label = button.text.strip()
        driver.execute_script("arguments[0].click()", button)
        WebDriverWait(driver, 5).until(
            lambda current: current.find_element(
                By.CSS_SELECTOR, ".docs-tabs [role='tabpanel'] code"
            ).text.strip()
        )
        tabs[label] = driver.find_element(
            By.CSS_SELECTOR, ".docs-tabs [role='tabpanel'] code"
        ).text
    return tabs


def run_code_example(label: str, code: str, fixture: ApiFixture) -> tuple[bool, str]:
    env = os.environ.copy()
    env.update(
        {
            "BOTBASE_API_URL": fixture.api_base,
            "BOTBASE_API_KEY": fixture.api_key,
            "BOTBASE_AGENT_ID": fixture.agent_id,
        }
    )
    timeout = 240
    if label == "cURL":
        command = ["bash", "-c", code]
    elif label == "Python":
        command = [sys.executable, "-c", code]
    elif label == "JavaScript":
        command = ["node", "--input-type=module", "-e", code]
    else:
        return False, f"unsupported tab label {label!r}"

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except FileNotFoundError as exc:
        return False, clean_output(str(exc), 160)

    output = completed.stdout.strip()
    if completed.returncode != 0:
        return False, clean_output(completed.stderr or output, 300)
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        return False, clean_output(output, 300)
    try:
        payload = json.loads(output[start : end + 1])
    except json.JSONDecodeError as exc:
        return False, clean_output(str(exc), 200)
    return True, payload  # type: ignore[return-value]


def create_api_fixture(api_base: str) -> ApiFixture:
    email = f"docs-verification-{uuid.uuid4().hex[:10]}@example.com"
    password = "DocsVerifyPass123!"
    session = requests.Session()
    registration = session.post(
        api_base + "/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    registration.raise_for_status()
    token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace_response = session.post(
        api_base + "/workspaces",
        json={"name": "Docs verification workspace"},
        headers=headers,
        timeout=30,
    )
    workspace_response.raise_for_status()
    workspace_id = workspace_response.json()["id"]
    try:
        agent_response = session.post(
            api_base + f"/workspaces/{workspace_id}/agents",
            json={
                "name": "Docs verification agent",
                "system_prompt": (
                    "You are a concise support assistant used only to verify the "
                    "BotBase documentation. When asked what you can help with, "
                    "answer in one short sentence about product questions."
                ),
            },
            headers=headers,
            timeout=30,
        )
        agent_response.raise_for_status()
        agent_id = agent_response.json()["id"]
        key_response = session.post(
            api_base + f"/workspaces/{workspace_id}/api-keys",
            json={"name": "Docs verification key"},
            headers=headers,
            timeout=30,
        )
        key_response.raise_for_status()
        api_key = key_response.json()["key"]
    except Exception:
        session.delete(api_base + f"/workspaces/{workspace_id}", headers=headers, timeout=30)
        raise
    return ApiFixture(
        email=email,
        password=password,
        api_base=api_base,
        token=token,
        workspace_id=workspace_id,
        agent_id=agent_id,
        api_key=api_key,
    )


def delete_api_fixture(fixture: ApiFixture) -> None:
    try:
        requests.delete(
            fixture.api_base + f"/workspaces/{fixture.workspace_id}",
            headers=fixture.headers(),
            timeout=30,
        )
    except requests.RequestException:
        pass


def example_failure_detail(result: Any) -> str:
    if isinstance(result, str):
        return clean_output(result, 300)
    # Never echo a live chat payload: it can contain provider diagnostics.
    return "response did not match the documented JSON shape and IDs"


def click_href(driver: webdriver.Chrome, href: str, timeout: float = 90) -> None:
    selector = f'a[href="{href}"]'
    WebDriverWait(driver, timeout).until(
        lambda current: any(
            element.is_displayed()
            for element in current.find_elements(By.CSS_SELECTOR, selector)
        )
    )
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        if element.is_displayed():
            driver.execute_script("arguments[0].click()", element)
            return
    raise RuntimeError(f"visible link not found: {href}")


def test_api_examples(
    runner: Runner,
    driver: webdriver.Chrome,
    fixture: ApiFixture,
    docs_base: str,
) -> None:
    runner.heading("Executable Developer API examples")
    list_tabs = extract_code_tabs(driver, docs_base, "/docs/developer/list-agents")
    runner.check(
        "List-agents page exposes cURL, Python and JavaScript examples",
        set(list_tabs) == {"cURL", "Python", "JavaScript"},
        f"tabs={sorted(list_tabs)}",
    )
    for label in ("cURL", "Python", "JavaScript"):
        code = list_tabs.get(label, "")
        ok, result = run_code_example(label, code, fixture)
        valid = (
            ok
            and isinstance(result, dict)
            and result.get("workspace_id") == fixture.workspace_id
            and any(agent.get("agent_id") == fixture.agent_id for agent in result.get("agents", []))
        )
        runner.check(
            f"GET /api/v1/agents runs from the {label} tab",
            valid,
            "" if valid else example_failure_detail(result),
        )

    chat_tabs = extract_code_tabs(driver, docs_base, "/docs/developer/chat")
    runner.check(
        "Chat page exposes cURL, Python and JavaScript examples",
        set(chat_tabs) == {"cURL", "Python", "JavaScript"},
        f"tabs={sorted(chat_tabs)}",
    )
    for label in ("cURL", "Python", "JavaScript"):
        code = chat_tabs.get(label, "")
        ok, result = run_code_example(label, code, fixture)
        valid = (
            ok
            and isinstance(result, dict)
            and isinstance(result.get("answer"), str)
            and bool(result.get("answer").strip())
            and result.get("agent_id") == fixture.agent_id
            and bool(result.get("conversation_id"))
        )
        runner.check(
            f"POST /api/v1/chat runs from the {label} tab",
            valid,
            "" if valid else example_failure_detail(result),
        )


def test_dashboard(
    runner: Runner,
    driver: webdriver.Chrome,
    fixture: ApiFixture,
    docs_base: str,
) -> None:
    runner.heading("Dashboard Docs entry and contextual links")
    driver.set_window_size(1440, 1000)
    driver.get(docs_base + "/login")
    WebDriverWait(driver, 60).until(
        lambda current: current.find_element(By.CSS_SELECTOR, "input[type='email']")
    )
    driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(fixture.email)
    driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(fixture.password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    try:
        WebDriverWait(driver, 90).until(
            lambda current: "/login" not in urlparse(current.current_url).path
        )
        logged_in = True
    except WebDriverException:
        logged_in = False
    runner.check("A test account can sign in to the dashboard", logged_in)
    if not logged_in:
        return

    WebDriverWait(driver, 60).until(
        lambda current: len(current.find_elements(By.CSS_SELECTOR, "aside[aria-label='Primary']")) == 1
    )
    docs_links = [
        link
        for link in driver.find_elements(By.CSS_SELECTOR, "aside[aria-label='Primary'] a[href='/docs']")
    ]
    docs_link = docs_links[0] if docs_links else None
    runner.check(
        "Dashboard sidebar exposes Docs in a new noopener tab",
        docs_link is not None
        and docs_link.get_attribute("target") == "_blank"
        and "noopener" in (docs_link.get_attribute("rel") or ""),
        "" if docs_link else "link not found",
    )

    theme_state = driver.execute_script(
        "return {docs: localStorage.getItem('botbase-docs-theme'), dashboard: localStorage.getItem('botbase-theme'), attr: document.documentElement.dataset.docsTheme || null}"
    )
    runner.check(
        "Docs theme storage does not leak into the dashboard theme",
        theme_state["docs"] == "light"
        and theme_state["dashboard"] is None
        and theme_state["attr"] is None,
        str(theme_state),
    )

    failures: list[str] = []
    ws = fixture.workspace_id
    agent = fixture.agent_id
    try:
        # All navigation stays client-side: the dashboard deliberately keeps
        # its access token in memory, so a hard reload would sign the test out.
        click_href(driver, "/workspaces")
        click_href(driver, f"/workspaces/{ws}?tab=documents")
        click_href(driver, f"/workspaces/{ws}?tab=agents")
        click_href(driver, f"/workspaces/{ws}/agents/{agent}?tab=overview")
        WebDriverWait(driver, 90).until(
            lambda current: any(
                element.is_displayed()
                for element in current.find_elements(
                    By.XPATH, "//button[normalize-space()='Edit']"
                )
            )
        )
        for edit_button in driver.find_elements(
            By.XPATH, "//button[normalize-space()='Edit']"
        ):
            if edit_button.is_displayed():
                driver.execute_script("arguments[0].click()", edit_button)
                break
        WebDriverWait(driver, 90).until(
            lambda current: any(
                element.is_displayed()
                for element in current.find_elements(
                    By.CSS_SELECTOR, 'a[href="/docs/agents/models"]'
                )
            )
        )
    except (WebDriverException, RuntimeError) as exc:
        failures.append(f"Model selector: {clean_output(str(exc), 160)}")

    try:
        click_href(driver, f"/workspaces/{ws}/agents/{agent}?tab=embed")
        WebDriverWait(driver, 90).until(
            lambda current: any(
                element.is_displayed()
                for element in current.find_elements(
                    By.CSS_SELECTOR, 'a[href="/docs/deploy/widget"]'
                )
            )
        )
    except (WebDriverException, RuntimeError) as exc:
        failures.append(f"Embed panel: {clean_output(str(exc), 160)}")

    try:
        click_href(driver, f"/workspaces/{ws}?tab=developer")
        WebDriverWait(driver, 90).until(
            lambda current: any(
                element.is_displayed()
                for element in current.find_elements(
                    By.CSS_SELECTOR, 'a[href="/docs/developer"]'
                )
            )
        )
    except (WebDriverException, RuntimeError) as exc:
        failures.append(f"Developer panel: {clean_output(str(exc), 160)}")

    runner.check(
        "Model, embed and developer screens each link contextually to docs",
        not failures,
        "; ".join(failures),
    )

    # The dashboard link should actually open the public docs in a new window.
    dashboard_handle = driver.current_window_handle
    opened_new_tab = False
    try:
        wait_until = WebDriverWait(driver, 60)
        wait_until.until(
            lambda current: len(
                current.find_elements(
                    By.CSS_SELECTOR, "aside[aria-label='Primary'] a[href='/docs']"
                )
            )
            > 0
        )
        link = driver.find_element(
            By.CSS_SELECTOR, "aside[aria-label='Primary'] a[href='/docs']"
        )
        link.click()
        WebDriverWait(driver, 30).until(lambda current: len(current.window_handles) > 1)
        docs_handle = next(
            handle for handle in driver.window_handles if handle != dashboard_handle
        )
        driver.switch_to.window(docs_handle)
        wait_docs_page(driver)
        opened_new_tab = urlparse(driver.current_url).path == "/docs"
    except (WebDriverException, RuntimeError):
        opened_new_tab = False
    finally:
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(dashboard_handle)
    runner.check(
        "Dashboard Docs link opens /docs in a new tab without a login wall",
        opened_new_tab,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-base", default=DEFAULT_DOCS_BASE)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--headed", action="store_true", help="show the Chromium window")
    parser.add_argument(
        "--skip-api-examples",
        action="store_true",
        help="skip the live developer API example execution",
    )
    args = parser.parse_args()

    docs_base = args.docs_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    runner = Runner()

    print("BotBase documentation verification")
    print(f"Docs: {docs_base}")
    print(f"API:  {api_base}")

    if not wait_for_http(docs_base + "/docs"):
        print(f"ERROR: docs server is not reachable at {docs_base}/docs", file=sys.stderr)
        return 2
    if not wait_for_http(api_base + "/api/v1/health"):
        print(f"ERROR: API server is not reachable at {api_base}/api/v1/health", file=sys.stderr)
        return 2

    pages = read_pages()
    test_source_content(runner, pages, docs_base)
    test_static_routes(runner, pages, docs_base, api_base)
    test_brand_and_contrast(runner, docs_base)

    driver: webdriver.Chrome | None = None
    fixture: ApiFixture | None = None
    try:
        driver = make_driver(headed=args.headed)
        crawl_rendered_pages(runner, driver, pages, docs_base)
        test_search_and_interactions(runner, driver, docs_base)
        fixture = create_api_fixture(api_base)
        if not args.skip_api_examples:
            test_api_examples(runner, driver, fixture, docs_base)
        else:
            runner.heading("Executable Developer API examples")
            runner.check("Live API examples skipped by request", True)
        test_dashboard(runner, driver, fixture, docs_base)
    except Exception as exc:  # noqa: BLE001 - keep a readable report
        runner.heading("Harness")
        runner.check(
            "Harness completed without an unexpected exception",
            False,
            f"{type(exc).__name__}: {clean_output(str(exc), 400)}",
        )
    finally:
        if fixture is not None:
            delete_api_fixture(fixture)
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
