"""Tassonomia chiusa dei difetti e rubrica di severità (docs/printloop/02_DATA_STRATEGY.md §2 e §4).

Le descrizioni in inglese finiscono nel prompt del modello; le etichette italiane sono per la UI.
"""
from __future__ import annotations

DEFECTS: dict[str, dict[str, str]] = {
    "under_extrusion": {
        "label": "Sotto-estrusione",
        "description": "Gaps between lines, thin or missing walls, porous or weak top surfaces, visible infill through skin.",
    },
    "over_extrusion": {
        "label": "Sovra-estrusione",
        "description": "Blobby, bulging or rough walls, ridges on top surfaces, dimensions larger than intended, elephant-like bulges on walls.",
    },
    "stringing": {
        "label": "Stringing",
        "description": "Thin hair-like strands or webs of filament between separate parts or across travel gaps.",
    },
    "bridge_sagging": {
        "label": "Bridge che cedono",
        "description": "Lines spanning unsupported gaps droop, sag, break or curl downwards under a bridge.",
    },
    "overhang_curling": {
        "label": "Overhang arricciati",
        "description": "Edges of angled overhangs curl upwards, look rough or drooped on the underside.",
    },
    "warping": {
        "label": "Warping / distacco",
        "description": "Corners or edges lifted from the bed, bottom not flat, part detached during the print.",
    },
    "first_layer": {
        "label": "Primo layer",
        "description": "First layer problems: lines not fused, gaps, rough or squished bottom, poor adhesion, uneven bottom surface.",
    },
    "layer_shift": {
        "label": "Layer shift",
        "description": "Layers abruptly offset horizontally relative to the ones below, a step in the part.",
    },
    "spaghetti": {
        "label": "Spaghetti / stampa persa",
        "description": "A tangle of loose extruded filament instead of the part; the print failed and continued in mid-air.",
    },
    "none": {
        "label": "Nessun difetto",
        "description": "The part looks correct; no defect of the classes above is visible.",
    },
    "other": {
        "label": "Fuori tassonomia",
        "description": "A defect is visible but it does not fit any class above.",
    },
}

DEFECT_CLASSES: tuple[str, ...] = tuple(DEFECTS)

SEVERITY: dict[int, str] = {
    0: "assente",
    1: "lieve, solo estetico: pezzo accettabile",
    2: "evidente: il pezzo funziona ma va rifatto per un cliente",
    3: "grave: pezzo da scartare",
}

SEVERITY_PROMPT = (
    "0 = absent; 1 = minor, cosmetic only, part acceptable; "
    "2 = clearly visible, part works but would be reprinted for a customer; 3 = severe, part must be discarded."
)


def label(defect: str) -> str:
    return DEFECTS.get(defect, {}).get("label", defect)
