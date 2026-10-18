"""BambuStudio / OrcaSlicer G-code parser for the pre-flight.

Extracts, per feature (`; FEATURE: Bridge`, or `;TYPE:` in Prusa/Orca style) and per layer
(`; CHANGE_LAYER` or `;LAYER_CHANGE`): speed, extrusion per mm, part fan, temperature setpoints,
retraction events (including the one spread over the wipe) and nominal volumetric flow.
Statistics cover only the body of the print: the start G-code (purge, levelling) is excluded.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"([A-Z])([-+]?\d*\.?\d+)")
_FEATURE = re.compile(r"^;\s*(?:FEATURE:|TYPE:)\s*(.+?)\s*$")
_LAYER = re.compile(r"^;\s*(?:CHANGE_LAYER|LAYER_CHANGE)\s*$")
_CONFIG = re.compile(r"^;\s*([a-z0-9_]+)\s*=\s*(.*)$")
_HEADER = re.compile(r"^;\s*(total estimated time|total filament length \[mm\]|total filament weight \[g\]|total layer number)\s*:\s*(.+)$")
_END_MARKERS = ("MACHINE_END_GCODE_START", "EXECUTABLE_BLOCK_END", "filament end gcode")
_NON_PRINT_FEATURES = {"Custom", "Undefined", "Flush", "Prime tower", "Wipe tower"}


def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    """Length-weighted median: robust to short segments."""
    pairs = [(v, w) for v, w in pairs if w > 0]
    if not pairs:
        return None
    pairs.sort()
    total = sum(w for _, w in pairs)
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= total / 2:
            return value
    return pairs[-1][0]


@dataclass
class FeatureStats:
    length_mm: float = 0.0
    e_mm: float = 0.0
    time_s: float = 0.0
    moves: int = 0
    speeds: list[tuple[float, float]] = field(default_factory=list)  # (mm/s, length)
    fans: list[tuple[float, float]] = field(default_factory=list)    # (fan %, length)

    def add(self, length: float, de: float, speed: float, fan_pct: float) -> None:
        self.length_mm += length
        self.e_mm += de
        self.time_s += length / speed if speed > 0 else 0.0
        self.moves += 1
        self.speeds.append((speed, length))
        self.fans.append((fan_pct, length))

    def merge(self, other: "FeatureStats") -> None:
        self.length_mm += other.length_mm
        self.e_mm += other.e_mm
        self.time_s += other.time_s
        self.moves += other.moves
        self.speeds.extend(other.speeds)
        self.fans.extend(other.fans)

    def summary(self) -> dict:
        return {"length_mm": round(self.length_mm, 1), "moves": self.moves,
                "speed_mm_s": _r(self.speed()), "e_per_mm": _r(self.e_per_mm(), 5), "fan_pct": _r(self.fan())}

    def speed(self) -> float | None:
        return _weighted_median(self.speeds)

    def e_per_mm(self) -> float | None:
        return self.e_mm / self.length_mm if self.length_mm > 0 else None

    def fan(self) -> float | None:
        return _weighted_median(self.fans)


def _r(value: float | None, nd: int = 2) -> float | None:
    return None if value is None else round(value, nd)


@dataclass
class GcodeStats:
    features: dict[str, FeatureStats] = field(default_factory=dict)
    first_layer: dict[str, FeatureStats] = field(default_factory=dict)
    hotend: list[tuple[int, float]] = field(default_factory=list)  # (layer, °C), layer -1 = start G-code
    bed: list[tuple[int, float]] = field(default_factory=list)
    retractions: list[float] = field(default_factory=list)
    volumetric: list[tuple[float, float]] = field(default_factory=list)  # (mm³/s, length)
    config: dict[str, str] = field(default_factory=dict)
    header: dict[str, str] = field(default_factory=dict)
    layers: int = 0
    filament_mm: float = 0.0

    def feature(self, names: list[str] | tuple[str, ...], first_layer: bool = False) -> FeatureStats:
        """Aggregated statistics over one or more features."""
        source = self.first_layer if first_layer else self.features
        agg = FeatureStats()
        for name in names:
            if name in source:
                agg.merge(source[name])
        return agg

    def setpoint(self, kind: str, layer: int) -> float | None:
        """Setpoint in effect during `layer` (the last one set up to that layer, ignoring heater-off commands)."""
        series = self.hotend if kind == "hotend" else self.bed
        value = None
        for lay, temp in series:
            if lay > layer:
                break
            if temp > 0:
                value = temp
        return value

    def retraction_median(self) -> float | None:
        values = sorted(self.retractions)
        return values[len(values) // 2] if values else None

    def volumetric_p99(self) -> float | None:
        if not self.volumetric:
            return None
        pairs = sorted(self.volumetric)
        total = sum(w for _, w in pairs)
        acc = 0.0
        for value, weight in pairs:
            acc += weight
            if acc >= 0.99 * total:
                return value
        return pairs[-1][0]

    def summary(self) -> dict:
        return {
            "layers": self.layers,
            "filament_mm": round(self.filament_mm, 1),
            "features": {k: v.summary() for k, v in sorted(self.features.items())},
            "hotend_layer0": self.setpoint("hotend", 0), "hotend_layer1": self.setpoint("hotend", 1),
            "bed_layer0": self.setpoint("bed", 0), "bed_layer1": self.setpoint("bed", 1),
            "retraction_mm": _r(self.retraction_median(), 3),
            "volumetric_p99_mm3_s": _r(self.volumetric_p99()),
            "header": self.header,
        }


def _arc_length(x0: float, y0: float, x1: float, y1: float, i: float, j: float, clockwise: bool) -> float:
    cx, cy = x0 + i, y0 + j
    r = math.hypot(i, j)
    a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
    sweep = a0 - a1 if clockwise else a1 - a0
    if sweep <= 1e-9:
        sweep += 2 * math.pi
    return r * sweep


def parse(path: str | Path) -> GcodeStats:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_lines(fh)


def parse_text(text: str) -> GcodeStats:
    return parse_lines(text.splitlines())


def parse_lines(lines) -> GcodeStats:
    st = GcodeStats()
    x = y = z = 0.0
    e_abs = 0.0
    abs_xyz, abs_e = True, False
    feed = 0.0  # mm/min
    fan = 0.0   # part fan %
    layer = -1
    feature: str | None = None
    retract_acc = 0.0
    ended = False
    area = math.pi * (1.75 / 2) ** 2

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            if any(marker in line for marker in _END_MARKERS) and layer >= 0:
                ended = True
            if _LAYER.match(line):
                layer += 1
                st.layers = layer + 1
                continue
            m = _FEATURE.match(line)
            if m:
                feature = m.group(1)
                continue
            m = _HEADER.match(line)
            if m:
                st.header[m.group(1)] = m.group(2).strip()
                continue
            m = _CONFIG.match(line)
            if m:
                st.config[m.group(1)] = m.group(2).strip()
                if m.group(1) == "filament_diameter":
                    try:
                        area = math.pi * (float(m.group(2).split(",")[0]) / 2) ** 2
                    except ValueError:
                        pass
            continue

        code, _, _comment = line.partition(";")
        parts = code.split(None, 1)
        if not parts:
            continue
        cmd = parts[0].upper()
        words = {k: float(v) for k, v in _WORD.findall(parts[1].upper())} if len(parts) > 1 else {}

        if cmd in ("G0", "G1", "G2", "G3"):
            if "F" in words:
                feed = words["F"]
            nx = (words["X"] if abs_xyz else x + words["X"]) if "X" in words else x
            ny = (words["Y"] if abs_xyz else y + words["Y"]) if "Y" in words else y
            nz = (words["Z"] if abs_xyz else z + words["Z"]) if "Z" in words else z
            de = 0.0
            if "E" in words:
                de = words["E"] - e_abs if abs_e else words["E"]
                e_abs = words["E"] if abs_e else e_abs + words["E"]
            if cmd in ("G2", "G3") and ("I" in words or "J" in words):
                length = _arc_length(x, y, nx, ny, words.get("I", 0.0), words.get("J", 0.0), cmd == "G2")
            else:
                length = math.hypot(nx - x, ny - y)
            x, y, z = nx, ny, nz

            if layer < 0 or ended:
                continue
            if de < 0:
                retract_acc += -de
                continue
            if de > 0:
                if retract_acc > 0:
                    st.retractions.append(retract_acc)
                    retract_acc = 0.0
                if length <= 1e-6:
                    continue  # stationary de-retraction
                st.filament_mm += de
                if feature in _NON_PRINT_FEATURES or feature is None:
                    continue
                speed = feed / 60.0
                st.features.setdefault(feature, FeatureStats()).add(length, de, speed, fan)
                if layer == 0:
                    st.first_layer.setdefault(feature, FeatureStats()).add(length, de, speed, fan)
                if speed > 0:
                    st.volumetric.append((de * area * speed / length, length))
        elif cmd == "G90":
            abs_xyz = True
        elif cmd == "G91":
            abs_xyz = False
        elif cmd == "M82":
            abs_e = True
        elif cmd == "M83":
            abs_e = False
        elif cmd == "G92" and "E" in words:
            e_abs = words["E"]
        elif cmd == "M106":
            if words.get("P", 1) in (0, 1):  # P1 or missing = part fan (P2 auxiliary, P3 chamber)
                fan = max(0.0, min(100.0, words.get("S", 255.0) / 255.0 * 100.0))
        elif cmd == "M107":
            fan = 0.0
        elif cmd in ("M104", "M109") and "S" in words and not ended:
            st.hotend.append((layer, words["S"]))
        elif cmd in ("M140", "M190") and "S" in words and not ended:
            st.bed.append((layer, words["S"]))
    return st
