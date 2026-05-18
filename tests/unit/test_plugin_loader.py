"""Unit tests for the dynamic plugin/skill discovery system."""
from __future__ import annotations

import types
import inspect

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: build a fake skill module
# ---------------------------------------------------------------------------

def _make_skill_module(func_name: str, is_async: bool = True):
    mod = types.ModuleType(func_name)
    mod.__doc__ = f"Skill: {func_name}."
    if is_async:
        g: dict = {}
        exec(f"async def {func_name}(site_url: str, depth: str = 'fast'): 'Run {func_name}.'", g)
        setattr(mod, func_name, g[func_name])
    else:
        def sync_fn(): pass
        sync_fn.__name__ = func_name
        setattr(mod, func_name, sync_fn)
    return mod


# ---------------------------------------------------------------------------
# SkillParam tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_skill_param_required_to_dict():
    from src.skills.plugin_loader import SkillParam

    d = SkillParam("url", "str", True).to_dict()
    assert d["required"] is True
    assert d["name"] == "url"
    assert d["annotation"] == "str"
    assert d["default"] is None


@pytest.mark.unit
def test_skill_param_optional_to_dict():
    from src.skills.plugin_loader import SkillParam

    d = SkillParam("depth", "str", False, "fast").to_dict()
    assert d["required"] is False
    assert d["default"] == "fast"


# ---------------------------------------------------------------------------
# SkillInfo tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_skill_info_to_dict():
    from src.skills.plugin_loader import SkillInfo, SkillParam

    info = SkillInfo(
        "explore",
        "desc",
        "src.skills.explore",
        "explore",
        [SkillParam("site_url", "str", True)],
    )
    d = info.to_dict()
    assert d["name"] == "explore"
    assert d["description"] == "desc"
    assert d["module_path"] == "src.skills.explore"
    assert d["entry_point"] == "explore"
    assert len(d["params"]) == 1
    assert d["params"][0]["name"] == "site_url"
    assert d["params"][0]["required"] is True


# ---------------------------------------------------------------------------
# discover() tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_discover_finds_async_skill():
    from src.skills.plugin_loader import PluginLoader
    from types import SimpleNamespace

    loader = PluginLoader()
    mod = _make_skill_module("explore")

    with patch("src.skills.plugin_loader.pkgutil.iter_modules") as mock_iter, \
         patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_iter.return_value = [SimpleNamespace(name="explore")]
        pkg_mock = MagicMock()
        pkg_mock.__path__ = ["fake"]
        mock_imp.side_effect = lambda n: pkg_mock if n == "src.skills" else mod
        skills = loader.discover("src.skills")

    assert len(skills) == 1
    assert skills[0].name == "explore"


@pytest.mark.unit
def test_discover_skips_sync_function():
    from src.skills.plugin_loader import PluginLoader
    from types import SimpleNamespace

    loader = PluginLoader()
    mod = _make_skill_module("sync_skill", is_async=False)

    with patch("src.skills.plugin_loader.pkgutil.iter_modules") as mock_iter, \
         patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_iter.return_value = [SimpleNamespace(name="sync_skill")]
        pkg_mock = MagicMock()
        pkg_mock.__path__ = ["fake"]
        mock_imp.side_effect = lambda n: pkg_mock if n == "src.skills" else mod
        skills = loader.discover("src.skills")

    assert len(skills) == 0


@pytest.mark.unit
def test_discover_skips_private_modules():
    from src.skills.plugin_loader import PluginLoader
    from types import SimpleNamespace

    loader = PluginLoader()

    with patch("src.skills.plugin_loader.pkgutil.iter_modules") as mock_iter, \
         patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_iter.return_value = [SimpleNamespace(name="_internal")]
        pkg_mock = MagicMock()
        pkg_mock.__path__ = ["fake"]
        mock_imp.return_value = pkg_mock
        skills = loader.discover("src.skills")

    assert len(skills) == 0


@pytest.mark.unit
def test_discover_handles_import_error():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()

    with patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_imp.side_effect = ImportError("no module")
        result = loader.discover("src.skills")

    assert result == []
    assert loader.is_discovered is True


@pytest.mark.unit
def test_discover_skips_module_without_matching_function():
    from src.skills.plugin_loader import PluginLoader
    from types import SimpleNamespace

    loader = PluginLoader()

    # Module named "orphan" but has no attribute "orphan"
    mod = types.ModuleType("orphan")
    mod.__doc__ = "No matching function here."

    with patch("src.skills.plugin_loader.pkgutil.iter_modules") as mock_iter, \
         patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_iter.return_value = [SimpleNamespace(name="orphan")]
        pkg_mock = MagicMock()
        pkg_mock.__path__ = ["fake"]
        mock_imp.side_effect = lambda n: pkg_mock if n == "src.skills" else mod
        skills = loader.discover("src.skills")

    assert len(skills) == 0


# ---------------------------------------------------------------------------
# get() and list() tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_get_returns_skill_after_discover():
    from src.skills.plugin_loader import PluginLoader
    from types import SimpleNamespace

    loader = PluginLoader()
    mod = _make_skill_module("explore")

    with patch("src.skills.plugin_loader.pkgutil.iter_modules") as mock_iter, \
         patch("src.skills.plugin_loader.importlib.import_module") as mock_imp:
        mock_iter.return_value = [SimpleNamespace(name="explore")]
        pkg_mock = MagicMock()
        pkg_mock.__path__ = ["fake"]
        mock_imp.side_effect = lambda n: pkg_mock if n == "src.skills" else mod
        loader.discover("src.skills")

    skill = loader.get("explore")
    assert skill is not None
    assert skill.name == "explore"


@pytest.mark.unit
def test_get_returns_none_for_unknown():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()
    loader._discovered = True  # skip auto-discover

    assert loader.get("ghost") is None


@pytest.mark.unit
def test_list_returns_all():
    from src.skills.plugin_loader import PluginLoader, SkillInfo

    loader = PluginLoader()
    loader._registry["a"] = SkillInfo("a", "desc a", "src.skills.a", "a")
    loader._registry["b"] = SkillInfo("b", "desc b", "src.skills.b", "b")
    loader._discovered = True

    result = loader.list()
    assert len(result) == 2


@pytest.mark.unit
def test_reset_clears_registry():
    from src.skills.plugin_loader import PluginLoader, SkillInfo

    loader = PluginLoader()
    loader._registry["x"] = SkillInfo("x", "desc", "src.skills.x", "x")
    loader._discovered = True

    loader.reset()

    assert loader._registry == {}
    assert loader.is_discovered is False


@pytest.mark.unit
def test_list_triggers_discover_if_needed():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()
    # _discovered stays False so list() should call discover()

    with patch.object(loader, "discover", return_value=[]) as mock_discover:
        loader.list()

    mock_discover.assert_called_once()


@pytest.mark.unit
def test_get_triggers_discover_if_needed():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()

    with patch.object(loader, "discover", return_value=[]) as mock_discover:
        loader.get("anything")

    mock_discover.assert_called_once()


# ---------------------------------------------------------------------------
# _extract() tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_extract_params_required_and_optional():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()
    mod = _make_skill_module("explore")
    skill = loader._extract("explore", mod, "src.skills.explore")

    assert skill is not None
    param_map = {p.name: p for p in skill.params}

    assert "site_url" in param_map
    assert param_map["site_url"].required is True
    assert param_map["site_url"].default is None

    assert "depth" in param_map
    assert param_map["depth"].required is False
    assert param_map["depth"].default == "fast"


@pytest.mark.unit
def test_extract_returns_none_for_missing_func():
    from src.skills.plugin_loader import PluginLoader

    loader = PluginLoader()
    mod = types.ModuleType("myskill")
    # No attribute "myskill" on the module

    result = loader._extract("myskill", mod, "src.skills.myskill")
    assert result is None


# ---------------------------------------------------------------------------
# API route existence tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_api_plugins_route_exists():
    from src.api.main import app

    routes = {r.path for r in app.routes}
    assert "/api/plugins" in routes


@pytest.mark.unit
def test_api_plugin_detail_route_exists():
    from src.api.main import app

    routes = {r.path for r in app.routes}
    assert "/api/plugins/{name}" in routes
