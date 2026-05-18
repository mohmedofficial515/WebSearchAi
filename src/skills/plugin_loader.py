"""Dynamic plugin/skill discovery and registry."""
from __future__ import annotations
import importlib, inspect, pkgutil
from dataclasses import dataclass, field
from typing import Any
from ..utils.logger import log


@dataclass
class SkillParam:
    name: str
    annotation: str
    required: bool
    default: Any = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "required": self.required,
            "default": None if self.default is inspect.Parameter.empty else self.default,
        }


@dataclass
class SkillInfo:
    name: str
    description: str
    module_path: str
    entry_point: str
    params: list[SkillParam] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "module_path": self.module_path,
            "entry_point": self.entry_point,
            "params": [p.to_dict() for p in self.params],
        }


class PluginLoader:
    """Discovers and registers async skill functions from a package."""

    def __init__(self) -> None:
        self._registry: dict[str, SkillInfo] = {}
        self._discovered = False

    @property
    def is_discovered(self) -> bool:
        return self._discovered

    def discover(self, package: str = "src.skills") -> list[SkillInfo]:
        """Scan *package* for async skill functions and populate the registry."""
        self._registry.clear()

        try:
            pkg = importlib.import_module(package)
        except ImportError as exc:
            log.warning(f"plugin_loader: cannot import package '{package}': {exc}")
            self._discovered = True
            return []

        for module_info in pkgutil.iter_modules(pkg.__path__):
            if module_info.name.startswith("_"):
                continue

            module_path = f"{package}.{module_info.name}"
            name = module_info.name

            try:
                mod = importlib.import_module(module_path)
                skill = self._extract(name, mod, module_path)
            except Exception as exc:  # noqa: BLE001
                log.warning(f"plugin_loader: skipping '{module_path}': {exc}")
                continue

            if skill is not None:
                self._registry[name] = skill

        self._discovered = True
        return list(self._registry.values())

    def _extract(self, name: str, mod: Any, module_path: str) -> SkillInfo | None:
        """Return a SkillInfo for *name* in *mod*, or None if not a coroutine function."""
        func = getattr(mod, name, None)
        if func is None or not inspect.iscoroutinefunction(func):
            return None

        raw_doc = func.__doc__ or getattr(mod, "__doc__", "") or ""
        description = ""
        for line in raw_doc.splitlines():
            stripped = line.strip()
            if stripped:
                description = stripped
                break

        params: list[SkillParam] = []
        for param_name, param in inspect.signature(func).parameters.items():
            # Resolve annotation string
            if param.annotation is inspect.Parameter.empty:
                ann_str = "Any"
            elif hasattr(param.annotation, "__name__"):
                ann_str = param.annotation.__name__
            else:
                ann_str = str(param.annotation)
                if ann_str == "<class 'inspect._empty'>":
                    ann_str = "Any"

            required = param.default is inspect.Parameter.empty
            default = None if required else param.default

            params.append(SkillParam(
                name=param_name,
                annotation=ann_str,
                required=required,
                default=default,
            ))

        return SkillInfo(
            name=name,
            description=description,
            module_path=module_path,
            entry_point=name,
            params=params,
        )

    def get(self, name: str) -> SkillInfo | None:
        """Return a registered skill by name, triggering discovery if needed."""
        if not self._discovered:
            self.discover()
        return self._registry.get(name)

    def list(self) -> list[SkillInfo]:
        """Return all registered skills, triggering discovery if needed."""
        if not self._discovered:
            self.discover()
        return list(self._registry.values())

    def reset(self) -> None:
        """Clear all discovered skills and reset discovery state."""
        self._registry.clear()
        self._discovered = False


# Module-level singleton
plugin_loader = PluginLoader()
