"""Unit tests for Phase 5 — Full-Site BFS Cloning."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Pure helpers ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_slugify_basic():
    from src.skills.site_clone import _slugify
    assert _slugify("https://example.com/blog/post") == "example.com_blog_post"


@pytest.mark.unit
def test_url_to_dirname_root():
    from src.skills.site_clone import _url_to_dirname
    assert _url_to_dirname("https://example.com") == "home"
    assert _url_to_dirname("https://example.com/") == "home"


@pytest.mark.unit
def test_url_to_dirname_path():
    from src.skills.site_clone import _url_to_dirname
    assert _url_to_dirname("https://example.com/about") == "about"
    assert _url_to_dirname("https://example.com/blog/post-1") == "blog_post-1"


@pytest.mark.unit
def test_url_to_dirname_query_adds_hash():
    from src.skills.site_clone import _url_to_dirname
    d1 = _url_to_dirname("https://example.com/search?q=foo")
    d2 = _url_to_dirname("https://example.com/search?q=bar")
    assert d1 != d2  # different queries → different directory names


@pytest.mark.unit
def test_normalize_url_strips_fragment():
    from src.skills.site_clone import _normalize_url
    assert _normalize_url("https://example.com/page#section") == "https://example.com/page"
    assert _normalize_url("https://example.com/#top") == "https://example.com/"


@pytest.mark.unit
def test_normalize_url_no_fragment_unchanged():
    from src.skills.site_clone import _normalize_url
    url = "https://example.com/about?ref=nav"
    assert _normalize_url(url) == url


@pytest.mark.unit
def test_same_domain_exact_match():
    from src.skills.site_clone import _same_domain
    assert _same_domain("https://example.com/page", "example.com") is True


@pytest.mark.unit
def test_same_domain_www_agnostic():
    from src.skills.site_clone import _same_domain
    assert _same_domain("https://www.example.com/page", "example.com") is True
    assert _same_domain("https://example.com/page", "www.example.com") is True


@pytest.mark.unit
def test_same_domain_rejects_external():
    from src.skills.site_clone import _same_domain
    assert _same_domain("https://other.com/page", "example.com") is False


# ── _get_links ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_links_returns_same_domain_hrefs():
    from src.skills.site_clone import _get_links
    html = """
    <html><body>
      <a href="/about">About</a>
      <a href="/blog/post-1">Post 1</a>
      <a href="https://example.com/contact">Contact</a>
      <a href="https://external.com/foo">External</a>
    </body></html>
    """
    links = _get_links(html, "https://example.com", "example.com")
    assert "https://example.com/about" in links
    assert "https://example.com/blog/post-1" in links
    assert "https://example.com/contact" in links
    assert "https://external.com/foo" not in links


@pytest.mark.unit
def test_get_links_filters_fragments_and_mailto():
    from src.skills.site_clone import _get_links
    html = """
    <html><body>
      <a href="#section">Jump</a>
      <a href="mailto:info@example.com">Email</a>
      <a href="tel:+123456">Phone</a>
      <a href="javascript:void(0)">JS</a>
      <a href="/valid">Valid</a>
    </body></html>
    """
    links = _get_links(html, "https://example.com", "example.com")
    assert links == ["https://example.com/valid"]


@pytest.mark.unit
def test_get_links_deduplicates():
    from src.skills.site_clone import _get_links
    html = """
    <html><body>
      <a href="/about">A</a>
      <a href="/about">B</a>
      <a href="/about#section">C</a>
    </body></html>
    """
    links = _get_links(html, "https://example.com", "example.com")
    assert links.count("https://example.com/about") == 1


@pytest.mark.unit
def test_get_links_empty_html():
    from src.skills.site_clone import _get_links
    assert _get_links("", "https://example.com", "example.com") == []


# ── _parse_sitemap_xml ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parse_sitemap_xml_basic():
    from src.skills.site_clone import _parse_sitemap_xml
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/</loc></url>
      <url><loc>https://example.com/about</loc></url>
      <url><loc>https://example.com/blog</loc></url>
    </urlset>"""
    urls = _parse_sitemap_xml(xml)
    assert urls == [
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/blog",
    ]


@pytest.mark.unit
def test_parse_sitemap_xml_no_namespace():
    from src.skills.site_clone import _parse_sitemap_xml
    xml = "<urlset><url><loc>https://a.com/</loc></url></urlset>"
    assert _parse_sitemap_xml(xml) == ["https://a.com/"]


@pytest.mark.unit
def test_parse_sitemap_xml_invalid_falls_back_to_regex():
    from src.skills.site_clone import _parse_sitemap_xml
    # Malformed XML that ET can't parse
    raw = "<urlset><url><loc>https://x.com/page</loc></url><url><loc>https://x.com/about"
    urls = _parse_sitemap_xml(raw)
    assert "https://x.com/page" in urls


@pytest.mark.unit
def test_parse_sitemap_xml_empty():
    from src.skills.site_clone import _parse_sitemap_xml
    assert _parse_sitemap_xml("<urlset></urlset>") == []


# ── SiteCloneResult.to_dict ───────────────────────────────────────────────────


@pytest.mark.unit
def test_site_clone_result_to_dict():
    from src.skills.site_clone import PageResult, SiteCloneResult

    pages = [
        PageResult(url="https://a.com", title="Home", html_path="/p/home.html",
                   screenshot_path="", links_found=3, status="ok"),
        PageResult(url="https://a.com/about", title="About", html_path="/p/about.html",
                   screenshot_path="", links_found=1, status="ok"),
    ]
    result = SiteCloneResult(
        root_url="https://a.com",
        out_dir="/out/a_com",
        pages=pages,
        total_pages=2,
        sitemap_urls=["https://a.com/", "https://a.com/about"],
        crawled_at=1000.0,
    )
    d = result.to_dict()
    assert d["total_pages"] == 2
    assert d["sitemap_urls_found"] == 2
    assert len(d["pages"]) == 2
    assert d["pages"][0]["url"] == "https://a.com"


# ── API body models ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_site_clone_body_defaults():
    from src.api.main import SiteCloneBody
    body = SiteCloneBody(url="https://example.com")
    assert body.max_pages == 50
    assert body.max_depth == 3
    assert body.take_screenshots is False
    assert body.headless is True


@pytest.mark.unit
def test_site_clone_body_custom():
    from src.api.main import SiteCloneBody
    body = SiteCloneBody(url="https://x.com", max_pages=10, max_depth=2)
    assert body.max_pages == 10
    assert body.max_depth == 2


# ── site_clone integration (mocked network) ───────────────────────────────────


def _make_fake_response(status: int, text: str = "", content_type: str = "text/html"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.content = text.encode()
    resp.headers = {"content-type": content_type}

    def raise_for_status():
        if status >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"HTTP {status}", request=MagicMock(), response=resp
            )
    resp.raise_for_status = raise_for_status
    return resp


@pytest.mark.unit
async def test_site_clone_crawls_root_page(tmp_path):
    from src.skills.site_clone import site_clone

    root_html = (
        "<html><head><title>Home</title></head>"
        "<body><a href='/about'>About</a></body></html>"
    )
    about_html = (
        "<html><head><title>About Us</title></head>"
        "<body><p>About</p></body></html>"
    )

    async def fake_get(url, **_):
        if "robots" in url or "sitemap" in url:
            return _make_fake_response(404)
        if url.endswith("/about"):
            return _make_fake_response(200, about_html)
        return _make_fake_response(200, root_html)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("src.skills.site_clone.settings") as ms, \
         patch("src.skills.site_clone.httpx.AsyncClient") as MockClient:
        ms.output_path = tmp_path
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await site_clone(
            "https://example.com",
            max_pages=5,
            max_depth=1,
            take_screenshots=False,
            delay_between_pages=0,
        )

    assert result.root_url == "https://example.com"
    urls = {p.url for p in result.pages}
    assert "https://example.com" in urls
    assert all(p.status == "ok" for p in result.pages)


@pytest.mark.unit
async def test_site_clone_respects_max_pages(tmp_path):
    """Crawler must not exceed max_pages even with many links."""
    from src.skills.site_clone import site_clone

    def _many_links_html(page_id: int) -> str:
        links = "".join(
            f'<a href="/page-{i}">Page {i}</a>' for i in range(20)
        )
        return f"<html><head><title>P{page_id}</title></head><body>{links}</body></html>"

    async def fake_get(url, **_):
        if "robots" in url or "sitemap" in url:
            return _make_fake_response(404)
        m = __import__("re").search(r"/page-(\d+)", url)
        pid = int(m.group(1)) if m else 0
        return _make_fake_response(200, _many_links_html(pid))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("src.skills.site_clone.settings") as ms, \
         patch("src.skills.site_clone.httpx.AsyncClient") as MockClient:
        ms.output_path = tmp_path
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await site_clone(
            "https://example.com",
            max_pages=5,
            max_depth=3,
            take_screenshots=False,
            delay_between_pages=0,
        )

    assert result.total_pages <= 5


@pytest.mark.unit
async def test_site_clone_skips_external_links(tmp_path):
    """Links to other domains must not be followed."""
    from src.skills.site_clone import site_clone

    html = (
        "<html><head><title>Home</title></head><body>"
        "<a href='https://external.com/page'>External</a>"
        "<a href='/internal'>Internal</a>"
        "</body></html>"
    )

    async def fake_get(url, **_):
        if "robots" in url or "sitemap" in url:
            return _make_fake_response(404)
        return _make_fake_response(200, html)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("src.skills.site_clone.settings") as ms, \
         patch("src.skills.site_clone.httpx.AsyncClient") as MockClient:
        ms.output_path = tmp_path
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await site_clone(
            "https://example.com",
            max_pages=10,
            max_depth=1,
            take_screenshots=False,
            delay_between_pages=0,
        )

    crawled_urls = {p.url for p in result.pages}
    assert not any("external.com" in u for u in crawled_urls)


@pytest.mark.unit
async def test_site_clone_handles_fetch_error_gracefully(tmp_path):
    """A page that fails to fetch is recorded as status='error', crawl continues."""
    from src.skills.site_clone import site_clone
    import httpx

    async def fake_get(url, **_):
        if "robots" in url or "sitemap" in url:
            return _make_fake_response(404)
        if url.endswith("/broken"):
            raise httpx.ConnectError("timeout")
        # Root page with a link to /broken
        return _make_fake_response(
            200,
            "<html><title>Home</title><body><a href='/broken'>Broken</a></body></html>",
        )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("src.skills.site_clone.settings") as ms, \
         patch("src.skills.site_clone.httpx.AsyncClient") as MockClient:
        ms.output_path = tmp_path
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await site_clone(
            "https://example.com",
            max_pages=5,
            max_depth=1,
            take_screenshots=False,
            delay_between_pages=0,
        )

    statuses = {p.status for p in result.pages}
    assert "ok" in statuses
    assert "error" in statuses


@pytest.mark.unit
async def test_site_clone_uses_sitemap_urls(tmp_path):
    """Sitemap URLs should be included in the crawl queue."""
    from src.skills.site_clone import site_clone

    sitemap_xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/sitemap-page</loc></url>
    </urlset>"""

    async def fake_get(url, **_):
        if "robots.txt" in url:
            return _make_fake_response(404)
        if url.endswith("sitemap.xml") or url.endswith("sitemap_index.xml"):
            return _make_fake_response(200, sitemap_xml, content_type="application/xml")
        return _make_fake_response(
            200, "<html><title>P</title><body></body></html>"
        )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("src.skills.site_clone.settings") as ms, \
         patch("src.skills.site_clone.httpx.AsyncClient") as MockClient:
        ms.output_path = tmp_path
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await site_clone(
            "https://example.com",
            max_pages=10,
            max_depth=0,
            take_screenshots=False,
            delay_between_pages=0,
        )

    assert len(result.sitemap_urls) == 1
    crawled = {p.url for p in result.pages}
    assert "https://example.com/sitemap-page" in crawled
