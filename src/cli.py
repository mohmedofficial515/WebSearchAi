"""CLI entry point — `python -m src.cli ...` or `python run.py`."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

import typer
from rich import print as rprint
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .config import settings
from .core.agent import Agent
from .reports import render_arabic_report
from .skills.clone import clone as skill_clone
from .skills.design_tokens import extract_design_tokens
from .skills.explore import explore as skill_explore
from .skills.find_components import find_components as skill_find_components
from .skills.login import login as skill_login
from .skills.signup import signup as skill_signup
from .skills.temp_signup import (
    forget_account as accounts_forget,
    list_accounts as accounts_list,
    temp_signup_persist,
)

app = typer.Typer(help="WebSearchAi — AI-driven browser automation")

# ── Memory sub-app ────────────────────────────────────────────────────────────

memory_app = typer.Typer(help="Manage agent long-term memory")
app.add_typer(memory_app, name="memory")


@memory_app.command("list")
def memory_list():
    """List all sites stored in long-term memory."""
    from .memory import get_memory

    async def _go():
        store = await get_memory()
        return await store.list_sites()

    sites = asyncio.run(_go())
    if not sites:
        rprint("[yellow]No sites in memory.[/yellow]")
        return
    table = Table(title="Remembered Sites", show_lines=True)
    table.add_column("URL", style="cyan", no_wrap=True)
    table.add_column("Visits", justify="right", style="green")
    table.add_column("Last Visited", style="dim")
    for s in sites:
        last = (
            datetime.fromtimestamp(s["last_visited_at"]).strftime("%Y-%m-%d %H:%M")
            if s.get("last_visited_at")
            else "-"
        )
        table.add_row(s["url"], str(s["visit_count"]), last)
    Console().print(table)


@memory_app.command("forget")
def memory_forget(url: str = typer.Argument(..., help="Site URL to remove from memory")):
    """Remove a site and all its data (flows, vectors, logins) from memory."""
    from .memory import get_memory

    async def _go():
        store = await get_memory()
        await store.forget_site(url)

    asyncio.run(_go())
    rprint(f"[green]Forgotten:[/green] {url}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Natural-language search query"),
    k: int = typer.Option(5, "--top", "-k", help="Number of results to return"),
):
    """Semantic search over everything the agent has remembered."""
    from .memory import MemoryRecall, get_memory

    if not settings.mistral_api_key:
        rprint("[red]MISTRAL_API_KEY is required for semantic memory search.[/red]")
        raise typer.Exit(1)

    async def _go():
        store = await get_memory()
        recall = MemoryRecall(store, settings.mistral_api_key)
        return await recall.search(query, k=k)

    results = asyncio.run(_go())
    if not results:
        rprint("[yellow]No results found.[/yellow]")
        return
    rprint(
        Panel.fit(
            json.dumps(results, ensure_ascii=False, indent=2),
            title=f"Memory Search: {query!r}",
            border_style="blue",
        )
    )


# ── Tasks sub-app ─────────────────────────────────────────────────────────────

tasks_app = typer.Typer(help="Browse persisted task history")
app.add_typer(tasks_app, name="tasks")


@tasks_app.command("list")
def tasks_list(
    limit: int = typer.Option(20, help="Max rows to show"),
    kind: str = typer.Option("", help="Filter by kind (run, explore, clone, …)"),
):
    """List tasks persisted to the local database."""
    from .storage import get_task_store

    async def _go():
        store = await get_task_store()
        return await store.list_tasks(limit=limit, kind=kind or None)

    rows = asyncio.run(_go())
    if not rows:
        rprint("[yellow]No tasks found.[/yellow]")
        return
    table = Table(title="Task History", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Kind", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Created", style="dim")
    for t in rows:
        created = (
            datetime.fromtimestamp(t["created_at"]).strftime("%Y-%m-%d %H:%M")
            if t.get("created_at")
            else "-"
        )
        table.add_row(t["task_id"], t["kind"], t["status"], created)
    Console().print(table)


@tasks_app.command("get")
def tasks_get(task_id: str = typer.Argument(..., help="Task ID")):
    """Show full details for a task."""
    from .storage import get_task_store

    async def _go():
        store = await get_task_store()
        return await store.load_task(task_id)

    rec = asyncio.run(_go())
    if not rec:
        rprint(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)
    rprint(
        Panel.fit(
            json.dumps(rec, ensure_ascii=False, indent=2),
            title=f"Task {task_id}",
            border_style="cyan",
        )
    )


# ── Library commands ─────────────────────────────────────────────────────────


@app.command("google")
def cmd_google(
    query: str = typer.Argument(..., help="Search query"),
    top: int = typer.Option(10, "--top", "-k", help="Max results"),
):
    """Search Google — zero LLM calls, instant results."""
    from .skills.library import google_search

    result = asyncio.run(google_search(query, max_results=top))
    if not result.results:
        rprint("[yellow]No results found.[/yellow]")
        return
    table = Table(title=f"Google: {query!r}", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="cyan")
    table.add_column("URL", style="blue")
    for i, r in enumerate(result.results, 1):
        table.add_row(str(i), r.get("title", ""), r.get("url", ""))
    Console().print(table)


@app.command("youtube")
def cmd_youtube(
    query: str = typer.Argument(..., help="Search query"),
    top: int = typer.Option(10, "--top", "-k", help="Max results"),
):
    """Search YouTube — zero LLM calls, instant results."""
    from .skills.library import youtube_search

    result = asyncio.run(youtube_search(query, max_results=top))
    if not result.videos:
        rprint("[yellow]No videos found.[/yellow]")
        return
    table = Table(title=f"YouTube: {query!r}", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="cyan")
    table.add_column("Channel", style="green")
    table.add_column("Duration", style="dim")
    for i, v in enumerate(result.videos, 1):
        table.add_row(str(i), v.get("title", ""), v.get("channel", ""), v.get("duration", ""))
    Console().print(table)


@app.command("linkedin")
def cmd_linkedin(
    url: str = typer.Argument(..., help="LinkedIn profile URL"),
):
    """Extract a LinkedIn profile — zero LLM calls."""
    from .skills.library import linkedin_extract_profile

    profile = asyncio.run(linkedin_extract_profile(url))
    if profile.error:
        rprint(f"[red]Error:[/red] {profile.error}")
        raise typer.Exit(1)
    rprint(
        Panel.fit(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
            title=f"LinkedIn: {profile.name or url}",
            border_style="blue",
        )
    )


# ── Visual test sub-app ───────────────────────────────────────────────────────

vtest_app = typer.Typer(help="Visual regression testing — capture baselines and diff pages")
app.add_typer(vtest_app, name="vtest")


@vtest_app.command("baseline")
def vtest_baseline(
    url: str = typer.Argument(..., help="URL to capture"),
    name: str = typer.Argument(..., help="Baseline name (used as filename stem)"),
    headless: bool = typer.Option(True, help="Run browser headless"),
):
    """Capture and store a visual baseline screenshot."""
    from .skills.visual_test import capture_baseline

    path = asyncio.run(capture_baseline(url, name, headless=headless))
    rprint(f"[green]Baseline saved:[/green] {path}")


@vtest_app.command("compare")
def vtest_compare(
    url: str = typer.Argument(..., help="URL to test"),
    name: str = typer.Argument(..., help="Baseline name to compare against"),
    threshold: float = typer.Option(0.01, help="Max allowed diff fraction (0.01 = 1 %)"),
    headless: bool = typer.Option(True, help="Run browser headless"),
):
    """Compare the current page screenshot against a stored baseline."""
    from .skills.visual_test import compare

    result = asyncio.run(compare(url, name, threshold=threshold, headless=headless))
    status = "PASS" if result.passed else "FAIL"
    color = "green" if result.passed else "red"
    rprint(
        Panel.fit(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            title=f"[{color}]{status}[/{color}] — {name}  diff={result.diff_percent*100:.2f}%",
            border_style=color,
        )
    )
    if not result.passed:
        raise typer.Exit(1)


@vtest_app.command("list")
def vtest_list():
    """List all stored visual baselines."""
    from .skills.visual_test import list_baselines

    baselines = list_baselines()
    if not baselines:
        rprint("[yellow]No baselines found.[/yellow]")
        return
    table = Table(title="Visual Baselines", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right", style="dim")
    table.add_column("Modified", style="dim")
    for b in baselines:
        mod = datetime.fromtimestamp(b["modified_at"]).strftime("%Y-%m-%d %H:%M")
        size_kb = b["size_bytes"] // 1024
        table.add_row(b["name"], f"{size_kb} KB", mod)
    Console().print(table)


@vtest_app.command("delete")
def vtest_delete(
    name: str = typer.Argument(..., help="Baseline name to delete"),
):
    """Delete a stored baseline."""
    from .skills.visual_test import delete_baseline

    ok = delete_baseline(name)
    if ok:
        rprint(f"[green]Deleted baseline:[/green] {name}")
    else:
        rprint(f"[red]Baseline not found:[/red] {name}")
        raise typer.Exit(1)


# ── Plugins sub-app ──────────────────────────────────────────────────────────

plugins_app = typer.Typer(help="Discover and inspect available skills/plugins")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list():
    """List all discoverable skills."""
    from .skills.plugin_loader import plugin_loader

    skills = plugin_loader.discover()
    if not skills:
        rprint("[yellow]No skills discovered.[/yellow]")
        return
    table = Table(title="Available Skills", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Params", justify="right", style="dim")
    for s in sorted(skills, key=lambda x: x.name):
        table.add_row(s.name, s.description[:60], str(len(s.params)))
    Console().print(table)


@plugins_app.command("info")
def plugins_info(name: str = typer.Argument(..., help="Skill name")):
    """Show full parameter details for a skill."""
    from .skills.plugin_loader import plugin_loader

    skill = plugin_loader.get(name)
    if not skill:
        rprint(f"[red]Skill not found:[/red] {name}")
        raise typer.Exit(1)
    rprint(
        Panel.fit(
            json.dumps(skill.to_dict(), ensure_ascii=False, indent=2),
            title=f"Skill: {name}",
            border_style="cyan",
        )
    )


# ── Core commands ─────────────────────────────────────────────────────────────


@app.command()
def run(
    goal: str = typer.Argument(..., help="Natural-language goal"),
    headless: bool = typer.Option(False, help="Run browser headless"),
    no_vision: bool = typer.Option(False, help="Disable vision LLM"),
):
    """Run a free-form goal."""

    async def _go():
        async with Agent(headless=headless, use_vision=not no_vision) as agent:
            return await agent.run(goal)

    result = asyncio.run(_go())
    result_dict = result.to_dict()
    # If the run went through the research orchestrator we have a
    # rich Markdown report on disk — show that instead of the JSON.
    if isinstance(result_dict.get("plan"), dict) and result_dict["plan"].get("research"):
        rprint(Markdown(render_arabic_report(result_dict)))
    else:
        rprint(
            Panel.fit(
                json.dumps(result_dict, ensure_ascii=False, indent=2),
                title="Result",
                border_style="cyan",
            )
        )


@app.command()
def research(
    goal: str = typer.Argument(..., help="Search keywords / question (any language)"),
    headless: bool = typer.Option(False, help="Run browser headless"),
    no_vision: bool = typer.Option(True, help="Disable vision LLM (research rarely needs it)"),
    max_candidates: int = typer.Option(0, help="Override RESEARCH_MAX_CANDIDATES (0 = use config)"),
    min_useful: int = typer.Option(0, help="Override RESEARCH_MIN_USEFUL_SOURCES (0 = use config)"),
):
    """Search-first agentic research.

    Pipeline: generate queries → search → rank → critique → visit top-K →
    judge content → (re-search if empty) → synthesize cited answer.
    Use this for KEYWORD/QUESTION goals where you don't have a URL.
    """
    # Apply CLI overrides at the settings level so the new flow picks them up.
    if max_candidates > 0:
        settings.research_max_candidates = max_candidates
    if min_useful > 0:
        settings.research_min_useful_sources = min_useful
    # Force-enable research mode and fresh runs (per spec: no cache).
    settings.research_enabled = True
    settings.research_fresh_runs = True

    async def _go():
        async with Agent(headless=headless, use_vision=not no_vision) as agent:
            return await agent.run(goal)

    result = asyncio.run(_go())
    result_dict = result.to_dict()

    # Render the Arabic Markdown report — far more readable than raw JSON.
    md = render_arabic_report(result_dict)
    rprint(Markdown(md))

    artifacts = result_dict.get("artifacts_dir") or ""
    if artifacts:
        rprint(
            Panel.fit(
                f"📄 [bold]Markdown:[/bold] {artifacts}/report.ar.md\n"
                f"📦 [bold]JSON:[/bold]     {artifacts}/result.json",
                title="Files",
                border_style="cyan",
            )
        )


@app.command()
def signup(
    site_url: str,
    name: str = typer.Option("", help="Full name"),
    extra: str = typer.Option("", help="Extra instructions"),
):
    """Create an account on a site using a temp inbox."""
    result = asyncio.run(skill_signup(site_url, full_name=name or None, extra_instructions=extra))
    rprint(
        Panel.fit(
            f"email:    {result.email}\n"
            f"password: {result.password}\n"
            f"link:     {result.verification_link}\n",
            title="Signup",
            border_style="green",
        )
    )


@app.command("temp-signup")
def temp_signup_cmd(
    site_url: str = typer.Argument(..., help="Site to register on"),
    name: str = typer.Option("", help="Full name to fill in"),
    profile: str = typer.Option("", help="Profile slug for persistent session (default: host)"),
    extra: str = typer.Option("", help="Extra instructions to give the agent"),
    headless: bool = typer.Option(False, help="Run browser headless"),
):
    """Sign up with a temp-mail address and PERSIST the browser session.

    The session (cookies, localStorage) is saved under
    `outputs/profiles/<slug>/` so subsequent `login` calls reuse it
    automatically. Credentials are written to `outputs/accounts/<slug>.json`
    for audit.
    """
    result = asyncio.run(temp_signup_persist(
        site_url,
        profile_name=profile or None,
        full_name=name or None,
        extra_instructions=extra,
        headless=headless,
    ))
    rprint(
        Panel.fit(
            f"site:        {result.site_url}\n"
            f"email:       {result.email}\n"
            f"password:    {result.password}\n"
            f"profile:     {result.profile_name}\n"
            f"session_dir: {result.session_dir}\n"
            f"verified:    {result.verified}\n"
            f"card:        {result.account_card}\n",
            title="✓ Persistent Signup",
            border_style="green",
        )
    )


@app.command("accounts")
def accounts_cmd(
    forget: str = typer.Option("", help="Profile slug to delete (omit to list)"),
):
    """List or delete persistent temp-mail accounts."""
    if forget:
        ok = accounts_forget(forget)
        rprint(f"{'🗑️  removed' if ok else '⚠️  not found'}: {forget}")
        return
    items = accounts_list()
    if not items:
        rprint("[muted]no accounts yet — run `temp-signup` first[/muted]")
        return
    t = Table(title="Saved accounts")
    t.add_column("profile"); t.add_column("site"); t.add_column("email")
    t.add_column("verified"); t.add_column("created")
    for it in items:
        ts = it.get("created_at") or 0
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"
        t.add_row(
            it.get("profile_name") or "",
            it.get("site_url") or "",
            it.get("email") or "",
            "✓" if it.get("verified") else "—",
            when,
        )
    Console().print(t)


@app.command("find-components")
def find_components_cmd(
    query: str = typer.Argument(..., help="Component search (any language)"),
    max_results: int = typer.Option(6, help="Number of components to capture"),
    headless: bool = typer.Option(True, help="Run browser headless"),
):
    """Designer/dev skill: find UI components, capture screenshots, build a gallery.

    Examples:
      python run.py find-components "tailwind navbar"
      python run.py find-components "بطاقات منتجات bootstrap"
    """
    result = asyncio.run(skill_find_components(
        query, max_pages=max_results, headless=headless
    ))
    rprint(
        Panel.fit(
            f"query:       {result.query}\n"
            f"variants:    {len(result.variants)} component(s)\n"
            f"viewer:      {result.viewer_html}\n"
            f"report.ar:   {result.report_md}\n"
            f"output dir:  {result.out_dir}\n\n"
            f"افتح viewer.html في المتصفح لاستعراض كل المكوّنات بكودها JSX.",
            title="🎨 Components",
            border_style="magenta",
        )
    )


@app.command("design-tokens")
def design_tokens_cmd(
    url: str = typer.Argument(..., help="URL whose design tokens to extract"),
    headless: bool = typer.Option(True, help="Run browser headless"),
    wait: float = typer.Option(2.0, help="Seconds to wait after navigation"),
):
    """Designer skill: extract palette/typography/spacing from a URL."""
    tokens = asyncio.run(extract_design_tokens(url, headless=headless, wait_seconds=wait))
    rprint(Markdown(open(tokens.report_md, encoding="utf-8").read()))
    rprint(
        Panel.fit(
            f"tokens:    {tokens.tokens_json}\n"
            f"palette:   {tokens.palette_image}\n"
            f"shot:      {tokens.screenshot}\n"
            f"report.ar: {tokens.report_md}\n",
            title="🎨 Design Tokens",
            border_style="cyan",
        )
    )


@app.command()
def login(site_url: str, email: str, password: str, persist: bool = True):
    """Log in to a site."""
    result = asyncio.run(skill_login(site_url, email, password, persist_session=persist))
    rprint(
        Panel.fit(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            title="Login",
            border_style="green",
        )
    )


@app.command()
def explore(site_url: str, depth: str = "thorough"):
    """Explore a site like a human and produce a feature report."""
    result = asyncio.run(skill_explore(site_url, depth_hint=depth))
    rprint(
        Panel.fit(
            json.dumps(result.report, ensure_ascii=False, indent=2),
            title=f"Report → {result.report_path}",
            border_style="magenta",
        )
    )


@app.command("site-clone")
def site_clone_cmd(
    url: str = typer.Argument(..., help="Root URL to crawl"),
    max_pages: int = typer.Option(50, help="Maximum pages to crawl"),
    max_depth: int = typer.Option(3, help="BFS depth limit (0 = root only)"),
    screenshots: bool = typer.Option(False, "--screenshots", help="Also capture screenshots"),
    headless: bool = typer.Option(True, help="Run browser headless (only with --screenshots)"),
):
    """Crawl an entire site with BFS and save HTML for every page."""
    from .skills.site_clone import site_clone as skill_site_clone

    result = asyncio.run(
        skill_site_clone(
            url,
            max_pages=max_pages,
            max_depth=max_depth,
            take_screenshots=screenshots,
            headless=headless,
        )
    )
    ok = sum(1 for p in result.pages if p.status == "ok")
    fail = result.total_pages - ok
    rprint(
        Panel.fit(
            f"pages crawled:   {result.total_pages}\n"
            f"successful:      {ok}\n"
            f"failed:          {fail}\n"
            f"sitemap URLs:    {len(result.sitemap_urls)}\n"
            f"output:          {result.out_dir}\n",
            title=f"Site Clone — {url}",
            border_style="cyan",
        )
    )
    if fail:
        raise typer.Exit(1)


@app.command()
def clone(url: str, max_assets: int = 60):
    """Clone a single page (capture + AI rebuild)."""
    result = asyncio.run(skill_clone(url, max_assets=max_assets))
    rprint(
        Panel.fit(
            f"index:    {result.index_html_path}\n"
            f"raw:      {result.raw_dir}\n"
            f"media:    {result.media_count}\n"
            f"css:      {result.css_count}\n"
            f"js:       {result.js_count}\n"
            f"swaps:    {len(result.library_swaps)}\n"
            f"dropped:  {len(result.dropped_assets)}\n",
            title="Clone",
            border_style="yellow",
        )
    )


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Start the FastAPI server + Web UI."""
    import uvicorn

    uvicorn.run("src.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
