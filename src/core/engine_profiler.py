"""
Engine profiling and detection for RPG Maker projects.
Provides confidence-based engine detection even when package.json is missing or corrupted.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class RpgMakerEngine(Enum):
    """Supported RPG Maker engine variants."""
    MV = "mv"
    MZ = "mz"
    VX_ACE = "vx_ace"
    VX = "vx"
    XP = "xp"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Risk level classification for project complexity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class DetectionEvidence:
    """Single piece of evidence for engine detection."""
    source: str
    pattern: str
    weight: int
    description: str


@dataclass
class EngineProfile:
    """Complete engine detection profile for a project."""
    engine: RpgMakerEngine
    confidence: float
    confidence_level: str
    evidence: List[DetectionEvidence]
    risk_signals: List[str]
    risk_labels: List[str]
    metadata: Dict[str, Any]

    def is_mz_heavy(self) -> bool:
        """Check if project is heavily using MZ plugins."""
        mz_heavy_signals = [
            sig for sig in self.risk_signals
            if "visumz" in sig.lower() or "mz_plugin_heavy" in sig.lower()
        ]
        return len(mz_heavy_signals) >= 2

    def is_generic_mz_plugin_heavy(self) -> bool:
        """Check if project uses many generic MZ plugins."""
        generic_mz_count = sum(
            1 for sig in self.risk_signals
            if "generic_mz_plugin" in sig.lower()
        )
        return generic_mz_count >= 3


@dataclass
class RubyVariantSignature:
    """Ruby file variant signature for engine detection."""
    extension: str
    magic_bytes: bytes
    expected_marshal_version: int
    engine_hints: Set[str]


RUBY_VARIANT_SIGNATURES: Dict[str, RubyVariantSignature] = {
    ".rxdata": RubyVariantSignature(
        extension=".rxdata",
        magic_bytes=b"\x04\x08",
        expected_marshal_version=8,
        engine_hints={"xp", "vx"},
    ),
    ".rvdata": RubyVariantSignature(
        extension=".rvdata",
        magic_bytes=b"\x04\x07",
        expected_marshal_version=7,
        engine_hints={"vx"},
    ),
    ".rvdata2": RubyVariantSignature(
        extension=".rvdata2",
        magic_bytes=b"\x04\x08",
        expected_marshal_version=8,
        engine_hints={"vx_ace"},
    ),
}


@dataclass
class ProjectProfile:
    """Complete project profile including engine detection and risk assessment."""
    project_path: str
    engine_profile: EngineProfile
    plugin_count: int
    active_plugin_count: int
    visu_stella_plugins: List[str]
    heavy_plugin_families: Dict[str, int]
    is_ui_heavy: bool
    has_shop_signals: bool
    has_quest_signals: bool
    suggested_worker_count: int
    suggested_batch_strategy: str
    has_wordwrap_plugins: bool = False


class EngineProfiler:
    """Confidence-based engine profiling system."""

    # Weight values for evidence
    HIGH_WEIGHT = 10
    MEDIUM_WEIGHT = 5
    LOW_WEIGHT = 2

    # Package.json detection patterns
    MV_PACKAGE_PATTERNS = [
        r'"rmmvCoreScripts"',
        r'"dependencies"\s*:\s*\{[^}]*"rmmv-core-scripts"',
        r'" RPG Maker MV"',
    ]

    MZ_PACKAGE_PATTERNS = [
        r'"rmmzCoreScripts"',
        r'"dependencies"\s*:\s*\{[^}]*"rmmz-core-scripts"',
        r'" RPG Maker MZ"',
    ]

    # JavaScript file signatures
    MV_JS_SIGNATURES = [
        r"rpg_core\.js",
        r"rpg_managers\.js",
        r"rpg_objects\.js",
        r"rpg_scenes\.js",
        r"rpg_sprites\.js",
        r"rpg_windows\.js",
    ]

    MZ_JS_SIGNATURES = [
        r"rmmz_core\.js",
        r"rmmz_managers\.js",
        r"rmmz_objects\.js",
        r"rmmz_scenes\.js",
        r"rmmz_sprites\.js",
        r"rmmz_windows\.js",
    ]

    # VisuStella plugin patterns
    VISUSTELLA_PATTERNS = [
        re.compile(r"^(VisuMZ_[0-9]|VisuStella_[A-Z])", re.IGNORECASE),
        re.compile(r"^VisuMZ_", re.IGNORECASE),
    ]

    # Shop/Quest UI patterns
    SHOP_SIGNALS = [
        re.compile(r"shop", re.IGNORECASE),
        re.compile(r"store", re.IGNORECASE),
        re.compile(r"buy", re.IGNORECASE),
        re.compile(r"sell", re.IGNORECASE),
        re.compile(r"merchant", re.IGNORECASE),
        re.compile(r"trade", re.IGNORECASE),
    ]

    QUEST_SIGNALS = [
        re.compile(r"quest", re.IGNORECASE),
        re.compile(r"mission", re.IGNORECASE),
        re.compile(r"task", re.IGNORECASE),
        re.compile(r"objective", re.IGNORECASE),
        re.compile(r"journal", re.IGNORECASE),
        re.compile(r"log", re.IGNORECASE),
    ]
    
    # Word wrap plugin patterns
    WORDWRAP_SIGNALS = [
        re.compile(r"MessageCore", re.IGNORECASE),
        re.compile(r"MessageWindow", re.IGNORECASE),
        re.compile(r"WordWrap", re.IGNORECASE),
        re.compile(r"MessageStyle", re.IGNORECASE),
    ]

    def __init__(self, project_path: str) -> None:
        self.project_path = project_path
        self._evidence: List[DetectionEvidence] = []
        self._risk_signals: List[str] = []

    def profile(self) -> ProjectProfile:
        """Create complete project profile."""
        engine_profile = self.detect_engine()
        plugin_data = self._analyze_plugins()
        risk_signals = self._detect_risk_signals(plugin_data)

        is_ui_heavy = self._detect_ui_heavy(plugin_data)
        has_shop = self._detect_shop_signals(plugin_data)
        has_quest = self._detect_quest_signals(plugin_data)

        worker_count = self._calculate_worker_count(plugin_data, engine_profile)
        batch_strategy = self._determine_batch_strategy(engine_profile, plugin_data)

        return ProjectProfile(
            project_path=self.project_path,
            engine_profile=engine_profile,
            plugin_count=plugin_data["total"],
            active_plugin_count=plugin_data["active"],
            visu_stella_plugins=plugin_data["visustella"],
            heavy_plugin_families=plugin_data["families"],
            is_ui_heavy=is_ui_heavy,
            has_shop_signals=has_shop,
            has_quest_signals=has_quest,
            suggested_worker_count=worker_count,
            suggested_batch_strategy=batch_strategy,
            has_wordwrap_plugins=self._detect_wordwrap_signals(plugin_data)
        )

    def detect_engine(self) -> EngineProfile:
        """Detect engine type with confidence scoring."""
        self._evidence.clear()
        self._risk_signals.clear()

        package_json_path = self._find_package_json()
        js_dir = self._find_js_dir()

        engine = RpgMakerEngine.UNKNOWN
        total_weight = 0
        matched_weight = 0

        if package_json_path:
            engine, evidence_data = self._detect_from_package_json(package_json_path)
            matched_weight = evidence_data["weight"]
            total_weight = evidence_data["total"]
            self._evidence.extend(evidence_data["items"])

        if js_dir and engine == RpgMakerEngine.UNKNOWN:
            engine, evidence_data = self._detect_from_js_dir(js_dir)
            matched_weight += evidence_data["weight"]
            total_weight += evidence_data["total"]
            self._evidence.extend(evidence_data["items"])

        if engine == RpgMakerEngine.UNKNOWN:
            # Fallback to Ruby detection if engine is still unknown (XP/VX/VXA)
            engine, evidence_data = self._detect_from_ruby_files()
            matched_weight += evidence_data["weight"]
            total_weight += evidence_data["total"]
            self._evidence.extend(evidence_data["items"])

        if total_weight == 0:
            confidence = 0.0
        else:
            confidence = min(1.0, matched_weight / total_weight)

        confidence_level = self._confidence_level(confidence)

        risk_labels = self._sort_risk_labels()

        return EngineProfile(
            engine=engine,
            confidence=confidence,
            confidence_level=confidence_level,
            evidence=list(self._evidence),
            risk_signals=list(self._risk_signals),
            risk_labels=risk_labels,
            metadata={
                "package_json_found": package_json_path is not None,
                "js_dir_found": js_dir is not None,
            },
        )

    def _find_package_json(self) -> Optional[str]:
        """Find package.json in project."""
        candidates = [
            os.path.join(self.project_path, "package.json"),
            os.path.join(self.project_path, "www", "package.json"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def _find_js_dir(self) -> Optional[str]:
        """Find JavaScript directory in project."""
        candidates = [
            os.path.join(self.project_path, "js"),
            os.path.join(self.project_path, "www", "js"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    def _find_data_dir(self) -> Optional[str]:
        """Find data directory in project."""
        candidates = [
            os.path.join(self.project_path, "data"),
            os.path.join(self.project_path, "Data"),
            os.path.join(self.project_path, "www", "data"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    def _read_package_json(self, path: str) -> Dict[str, Any]:
        """Read package.json with error handling."""
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _detect_from_package_json(self, path: str) -> tuple[RpgMakerEngine, Dict[str, Any]]:
        """Detect engine from package.json."""
        data = self._read_package_json(path)
        content = json.dumps(data)

        evidence_items: List[DetectionEvidence] = []
        total_weight = 100
        matched_weight = 0

        for pattern in self.MV_PACKAGE_PATTERNS:
            if re.search(pattern, content):
                matched_weight += self.HIGH_WEIGHT
                evidence_items.append(DetectionEvidence(
                    source="package.json",
                    pattern=pattern,
                    weight=self.HIGH_WEIGHT,
                    description="MV package signature found",
                ))

        for pattern in self.MZ_PACKAGE_PATTERNS:
            if re.search(pattern, content):
                matched_weight += self.HIGH_WEIGHT
                evidence_items.append(DetectionEvidence(
                    source="package.json",
                    pattern=pattern,
                    weight=self.HIGH_WEIGHT,
                    description="MZ package signature found",
                ))

        if "rmmv" in content.lower() and "rmmz" not in content.lower():
            engine = RpgMakerEngine.MV
        elif "rmmz" in content.lower():
            engine = RpgMakerEngine.MZ
        else:
            engine = RpgMakerEngine.UNKNOWN

        return engine, {
            "weight": matched_weight,
            "total": total_weight,
            "items": evidence_items,
        }

    def _detect_from_js_dir(self, js_dir: str) -> tuple[RpgMakerEngine, Dict[str, Any]]:
        """Detect engine from JavaScript directory contents."""
        evidence_items: List[DetectionEvidence] = []
        mv_signatures = 0
        mz_signatures = 0
        total_weight = 0

        try:
            for filename in os.listdir(js_dir):
                lower_name = filename.lower()
                for pattern in self.MV_JS_SIGNATURES:
                    if re.search(pattern, lower_name):
                        mv_signatures += 1
                        evidence_items.append(DetectionEvidence(
                            source=f"js/{filename}",
                            pattern=pattern,
                            weight=self.MEDIUM_WEIGHT,
                            description="MV JS core file found",
                        ))
                        total_weight += self.MEDIUM_WEIGHT

                for pattern in self.MZ_JS_SIGNATURES:
                    if re.search(pattern, lower_name):
                        mz_signatures += 1
                        evidence_items.append(DetectionEvidence(
                            source=f"js/{filename}",
                            pattern=pattern,
                            weight=self.MEDIUM_WEIGHT,
                            description="MZ JS core file found",
                        ))
                        total_weight += self.MEDIUM_WEIGHT
        except OSError:
            pass

        matched_weight = mv_signatures + mz_signatures
        total_weight = max(total_weight, 1)

        if mz_signatures > mv_signatures:
            engine = RpgMakerEngine.MZ
        elif mv_signatures > mz_signatures:
            engine = RpgMakerEngine.MV
        else:
            engine = RpgMakerEngine.UNKNOWN

        return engine, {
            "weight": matched_weight * self.MEDIUM_WEIGHT,
            "total": total_weight,
            "items": evidence_items,
        }

    def _detect_from_ruby_files(self) -> tuple[RpgMakerEngine, Dict[str, Any]]:
        """Detect engine from Ruby data files (XP/VX/VXA)."""
        evidence_items: List[DetectionEvidence] = []
        detected_signatures: Dict[str, int] = {}
        total_weight = 0

        data_dir = self._find_data_dir()
        if not data_dir:
            return RpgMakerEngine.UNKNOWN, {"weight": 0, "total": 1, "items": []}

        ruby_extensions = {".rxdata", ".rvdata", ".rvdata2"}
        sample_count = 0
        max_samples = 10

        try:
            with os.scandir(data_dir) as entries:
                for entry in entries:
                    if not entry.is_file() or sample_count >= max_samples:
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in ruby_extensions:
                        sample_count += 1
                        variant = self._detect_ruby_variant(entry.path)
                        if variant:
                            detected_signatures[variant] = detected_signatures.get(variant, 0) + 1
                            evidence_items.append(DetectionEvidence(
                                source=entry.name,
                                pattern=f"magic_bytes:{variant}",
                                weight=self.HIGH_WEIGHT,
                                description=f"Ruby variant detected: {variant}",
                            ))
                            total_weight += self.HIGH_WEIGHT
        except OSError:
            pass

        if not detected_signatures:
            return RpgMakerEngine.UNKNOWN, {"weight": 0, "total": 1, "items": []}

        dominant_variant = max(detected_signatures, key=detected_signatures.get)
        engine = self._ruby_variant_to_engine(dominant_variant)

        return engine, {
            "weight": total_weight,
            "total": max(total_weight, 1),
            "items": evidence_items,
        }

    def _detect_ruby_variant(self, file_path: str) -> Optional[str]:
        """Detect Ruby file variant from magic bytes with extension preference."""
        ext = os.path.splitext(file_path)[1].lower()
        try:
            with open(file_path, "rb") as f:
                header = f.read(2)
                if len(header) < 2:
                    return None

                # First, check if the actual extension matches its expected magic bytes
                if ext in RUBY_VARIANT_SIGNATURES:
                    sig = RUBY_VARIANT_SIGNATURES[ext]
                    if header == sig.magic_bytes:
                        return ext

                # Fallback: scan all signatures if extension is non-standard
                for variant_name, sig in RUBY_VARIANT_SIGNATURES.items():
                    if header == sig.magic_bytes:
                        return variant_name
        except OSError:
            pass
        return None

    def _ruby_variant_to_engine(self, variant: str) -> RpgMakerEngine:
        """Map Ruby variant to engine."""
        mapping = {
            ".rxdata": RpgMakerEngine.XP,
            ".rvdata": RpgMakerEngine.VX,
            ".rvdata2": RpgMakerEngine.VX_ACE,
        }
        return mapping.get(variant, RpgMakerEngine.UNKNOWN)

    def _detect_ruby_variant_direct(self, file_path: str) -> RpgMakerEngine:
        """Detect Ruby variant directly from file path."""
        ext = os.path.splitext(file_path)[1].lower()
        return self._ruby_variant_to_engine(ext)

    def _analyze_plugins(self) -> Dict[str, Any]:
        """Analyze plugins.js for plugin statistics."""
        result = {
            "total": 0,
            "active": 0,
            "visustella": [],
            "families": {},
        }

        plugins_js = self._find_plugins_js()
        if not plugins_js:
            return result

        try:
            with open(plugins_js, "r", encoding="utf-8-sig") as f:
                content = f.read()

            start = content.find("[")
            end = content.rfind("]")
            if start < 0 or end < 0:
                return result

            plugins = json.loads(content[start:end + 1])
            if not isinstance(plugins, list):
                return result

            result["total"] = len(plugins)

            for plugin in plugins:
                if not isinstance(plugin, dict):
                    continue

                name = plugin.get("name", "")
                if not name:
                    continue

                if plugin.get("status") is True:
                    result["active"] += 1

                if self._is_visustella(name):
                    result["visustella"].append(name)

                family = self._detect_plugin_family(name)
                if family:
                    result["families"][family] = result["families"].get(family, 0) + 1

        except (json.JSONDecodeError, OSError):
            pass

        return result

    def _find_plugins_js(self) -> Optional[str]:
        """Find plugins.js file."""
        js_dir = self._find_js_dir()
        if not js_dir:
            return None

        plugins_js = os.path.join(js_dir, "plugins.js")
        if os.path.exists(plugins_js):
            return plugins_js
        return None

    def _is_visustella(self, name: str) -> bool:
        """Check if plugin is VisuStella family."""
        return any(pattern.search(name) for pattern in self.VISUSTELLA_PATTERNS)

    def _detect_plugin_family(self, name: str) -> Optional[str]:
        """Detect plugin family from name."""
        name_lower = name.lower()
        families = {
            "visustella": [r"^(visumz|visustella|yep)_"],
            "mog": [r"^mog_"],
            "srd": [r"^srd_"],
            "galv": [r"^galv_"],
            "srpg": [r"^srpg_"],
            "ts": [r"^ts_"],
        }

        for family, patterns in families.items():
            for pattern in patterns:
                if re.search(pattern, name_lower):
                    return family
        return "other"

    def _detect_risk_signals(self, plugin_data: Dict[str, Any]) -> List[str]:
        """Detect risk signals from plugin data."""
        signals: List[str] = []

        visu_count = len(plugin_data["visustella"])
        if visu_count >= 10:
            signals.append("visumz_heavy")
            self._risk_signals.append("visumz_heavy")
        elif visu_count >= 5:
            signals.append("visumz_moderate")
            self._risk_signals.append("visumz_moderate")

        if plugin_data["active"] >= 50:
            signals.append("plugin_overload")
            self._risk_signals.append("plugin_overload")
        elif plugin_data["active"] >= 30:
            signals.append("plugin_heavy")
            self._risk_signals.append("plugin_heavy")

        families = plugin_data["families"]
        other_count = families.get("other", 0)
        if other_count >= 15:
            signals.append("generic_mz_plugin_heavy")
            self._risk_signals.append("generic_mz_plugin_heavy")

        for family, count in families.items():
            if family != "visustella" and count >= 8:
                signals.append(f"{family}_plugin_cluster")
                self._risk_signals.append(f"{family}_plugin_cluster")

        return signals

    def _detect_ui_heavy(self, plugin_data: Dict[str, Any]) -> bool:
        """Detect if project is UI-heavy based on plugin patterns."""
        families = plugin_data["families"]
        ui_families = {"mog", "srd", "galv", "other"}
        ui_count = sum(families.get(f, 0) for f in ui_families)
        return ui_count >= 10 or (ui_count >= 5 and plugin_data["active"] >= 20)

    def _detect_shop_signals(self, plugin_data: Dict[str, Any]) -> bool:
        """Detect shop-related plugin signals."""
        plugins_js = self._find_plugins_js()
        if not plugins_js:
            return False

        try:
            with open(plugins_js, "r", encoding="utf-8-sig") as f:
                content = f.read().lower()

            matches = sum(1 for pattern in self.SHOP_SIGNALS if pattern.search(content))
            return matches >= 2
        except OSError:
            return False

    def _detect_quest_signals(self, plugin_data: Dict[str, Any]) -> bool:
        """Detect quest-related plugin signals."""
        plugins_js = self._find_plugins_js()
        if not plugins_js:
            return False

        try:
            with open(plugins_js, "r", encoding="utf-8-sig") as f:
                content = f.read().lower()

            matches = sum(1 for pattern in self.QUEST_SIGNALS if pattern.search(content))
            return matches >= 2
        except OSError:
            return False

    def _detect_wordwrap_signals(self, plugin_data: Dict[str, Any]) -> bool:
        """Detect if project likely supports engine-level word wrapping via plugins."""
        # 1. Check active VisuStella/Yanfly plugins (they usually have wrap)
        for name in plugin_data["visustella"]:
            if "MessageCore" in name:
                return True
        
        # 2. Check all active plugins for wordwrap keywords
        plugins_js = self._find_plugins_js()
        if not plugins_js:
            # For Ruby projects (XP/VX/Ace), we might check script names later
            return False

        try:
            with open(plugins_js, "r", encoding="utf-8-sig") as f:
                content = f.read().lower()
            
            return any(pattern.search(content) for pattern in self.WORDWRAP_SIGNALS)
        except OSError:
            return False

    def _confidence_level(self, confidence: float) -> str:
        """Get confidence level description."""
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.7:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        elif confidence >= 0.3:
            return "low"
        else:
            return "very_low"

    def _sort_risk_labels(self) -> List[str]:
        """Sort risk labels by severity."""
        priority_map = {
            "visumz_heavy": 1,
            "plugin_overload": 2,
            "generic_mz_plugin_heavy": 3,
            "visumz_moderate": 4,
            "plugin_heavy": 5,
        }

        sorted_labels = sorted(
            self._risk_signals,
            key=lambda x: priority_map.get(x, 99)
        )
        return sorted_labels

    def _calculate_worker_count(self, plugin_data: Dict[str, Any], engine_profile: EngineProfile) -> int:
        """Calculate optimal worker count based on project size."""
        active_plugins = plugin_data["active"]
        total_entries = plugin_data.get("estimated_entries", 0)

        if active_plugins < 10 and total_entries < 1000:
            return 2
        elif active_plugins < 30:
            return 4
        elif active_plugins < 50:
            return 6
        else:
            return min(os.cpu_count() or 4, 8)

    def _determine_batch_strategy(self, engine_profile: EngineProfile, plugin_data: Dict[str, Any]) -> str:
        """Determine optimal batch processing strategy."""
        if engine_profile.engine == RpgMakerEngine.MZ and engine_profile.is_mz_heavy():
            return "conservative"
        elif engine_profile.engine == RpgMakerEngine.MV and plugin_data["active"] < 20:
            return "standard"
        elif plugin_data["active"] >= 50:
            return "capped"
        else:
            return "standard"


def profile_project(project_path: str) -> ProjectProfile:
    """Convenience function to profile a project."""
    profiler = EngineProfiler(project_path)
    return profiler.profile()
