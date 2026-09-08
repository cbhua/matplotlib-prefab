#!/usr/bin/env python3
"""Read a compiled page's real layout out of the PDF: every line, at its baseline.

The HTML paper page is not allowed to guess what LaTeX did. It is generated from
what LaTeX actually produced, and this module is what reads that: it walks the
page's content stream, tracks the text state the way a viewer does, and reports
one record per text run — the characters, the font resource and its base font,
the size in PDF points, the origin on the page, and the advance width computed
from the font's own ``/Widths``.

Why not ``extract_text``: a reading-order string is the wrong output here. The
calibration needs the *position* of every run to a fraction of a millimetre, the
font each run is actually set in (regular, bold, italic, typewriter, maths), and
the line breaks TeX chose — none of which survive being flattened to text.

Coordinates are PDF points with the origin bottom-left, as they are in the file.
Callers convert; nothing here silently flips an axis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

PDF_PT_PER_INCH = 72.0
MM_PER_INCH = 25.4


def pdf_pt_to_mm(value: float) -> float:
    return value / PDF_PT_PER_INCH * MM_PER_INCH


# --------------------------------------------------------------------------
# Matrices
# --------------------------------------------------------------------------

Matrix = List[float]

IDENTITY: Matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def mat_mul(m: Sequence[float], n: Sequence[float]) -> Matrix:
    """Concatenate [a b c d e f] matrices, ``m`` applied first."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return [
        a * A + b * C, a * B + b * D,
        c * A + d * C, c * B + d * D,
        e * A + f * C + E, e * B + f * D + F,
    ]


def apply(matrix: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

STANDARD_ENCODING_OVERRIDES = {
    # TeX's text fonts use their own encoding vectors, which the PDF records as
    # /Differences. Everything not overridden falls back to WinAnsi/Standard,
    # where the code is the Latin-1 code point for the ASCII range — which is
    # all these documents use outside the difference list.
}


class Font:
    """One /Font resource, reduced to what layout needs: widths and characters."""

    def __init__(self, name: str, obj: Dict[str, Any]) -> None:
        from fontTools import agl

        self.resource_name = name
        self.base_font = str(obj.get("/BaseFont", "")).lstrip("/")
        # pdfTeX subsets as ABCDEF+RealName; the prefix is per-run noise.
        self.family = self.base_font.split("+", 1)[-1]
        self.subtype = str(obj.get("/Subtype", "")).lstrip("/")

        self.first_char = int(obj.get("/FirstChar", 0))
        widths = obj.get("/Widths")
        self.widths = [float(w) for w in widths] if widths is not None else []

        descriptor = obj.get("/FontDescriptor")
        descriptor = descriptor.get_object() if descriptor is not None else {}
        self.flags = int(descriptor.get("/Flags", 0) or 0)
        self.italic_angle = float(descriptor.get("/ItalicAngle", 0) or 0)
        self.stem_v = float(descriptor.get("/StemV", 0) or 0)
        self.missing_width = float(descriptor.get("/MissingWidth", 0) or 0)

        self.differences: Dict[int, str] = {}
        encoding = obj.get("/Encoding")
        if encoding is not None:
            encoding = encoding.get_object()
            if isinstance(encoding, dict):
                self.base_encoding = str(encoding.get("/BaseEncoding", "") or "").lstrip("/")
                diffs = encoding.get("/Differences")
                if diffs is not None:
                    code = 0
                    for item in diffs.get_object():
                        if isinstance(item, (int, float)):
                            code = int(item)
                        else:
                            self.differences[code] = str(item).lstrip("/")
                            code += 1
            else:
                self.base_encoding = str(encoding).lstrip("/")
        else:
            self.base_encoding = ""

        self._to_unicode = agl.toUnicode

    def width(self, code: int) -> float:
        """Advance for one byte code, in 1/1000 em."""
        index = code - self.first_char
        if 0 <= index < len(self.widths):
            return self.widths[index]
        return self.missing_width

    def text(self, code: int) -> str:
        """The characters this code stands for, ligatures expanded."""
        glyph = self.differences.get(code)
        if glyph is None:
            # Outside the difference list these fonts follow the standard Latin
            # codes, which for the ASCII range is the code point itself.
            return chr(code) if 32 <= code < 127 else ""
        decoded = self._to_unicode(glyph)
        return decoded if decoded else ""

    def style(self) -> Dict[str, Any]:
        """Weight and slant as the calibration reports them.

        Read from the font's own name and descriptor, not guessed from context:
        ``NimbusRomNo9L-Medi`` *is* the bold face, and saying so is the point —
        the HTML page has to use that face rather than synthesising a bold.
        """
        lowered = self.family.lower()
        bold = ("medi" in lowered or "bold" in lowered or "-bd" in lowered
                or bool(self.flags & (1 << 18)))
        italic = ("ital" in lowered or "obli" in lowered or self.italic_angle != 0
                  or bool(self.flags & (1 << 6)))
        mono = "mono" in lowered or "cmtt" in lowered or bool(self.flags & 1)
        maths = lowered.startswith("cm") and not mono
        return {
            "weight": "bold" if bold else "normal",
            "style": "italic" if italic else "normal",
            "monospace": mono,
            "maths": maths,
            "serif": bool(self.flags & (1 << 1)),
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "resource": self.resource_name,
            "base_font": self.base_font,
            "family": self.family,
            "subtype": self.subtype,
            "flags": self.flags,
            "italic_angle": self.italic_angle,
            **self.style(),
        }


def page_fonts(page) -> Dict[str, Font]:
    resources = page.get("/Resources")
    if resources is None:
        return {}
    resources = resources.get_object()
    fonts = resources.get("/Font")
    if fonts is None:
        return {}
    return {
        str(name): Font(str(name), entry.get_object())
        for name, entry in fonts.get_object().items()
    }


# --------------------------------------------------------------------------
# The text walker
# --------------------------------------------------------------------------

class TextState:
    def __init__(self) -> None:
        self.font: Optional[Font] = None
        self.size = 0.0
        self.char_spacing = 0.0
        self.word_spacing = 0.0
        self.horizontal_scale = 1.0
        self.leading = 0.0
        self.rise = 0.0
        self.render_mode = 0


def _decode_string(operand) -> bytes:
    if isinstance(operand, bytes):
        return operand
    original = getattr(operand, "original_bytes", None)
    if original is not None:
        return bytes(original)
    return str(operand).encode("latin-1", "replace")


def text_runs(page, reader) -> List[Dict[str, Any]]:
    """Every show-text operation on the page, with where it starts and ends.

    One record per ``Tj``/``TJ``: the run's characters, its font, its size in
    page points after the full transform, its baseline origin, and its width.
    Runs are *not* merged into lines here — grouping is a separate decision and
    a caller that wants raw runs should get raw runs.
    """
    from pypdf.generic import ContentStream

    fonts = page_fonts(page)
    contents = page.get_contents()
    if contents is None:
        return []
    stream = ContentStream(contents, reader)

    ctm: Matrix = list(IDENTITY)
    stack: List[Matrix] = []
    tm: Matrix = list(IDENTITY)
    tlm: Matrix = list(IDENTITY)
    state = TextState()
    state_stack: List[TextState] = []
    runs: List[Dict[str, Any]] = []

    def show(payload: bytes) -> None:
        nonlocal tm
        if state.font is None or not payload:
            return
        font = state.font
        start = list(tm)
        characters: List[str] = []
        codes: List[int] = []
        advance = 0.0
        for byte in payload:
            width = font.width(byte) / 1000.0 * state.size
            width += state.char_spacing
            if byte == 32:
                width += state.word_spacing
            advance += width * state.horizontal_scale
            characters.append(font.text(byte))
            codes.append(byte)
        tm = mat_mul([1, 0, 0, 1, advance, 0], tm)

        full = mat_mul(start, ctm)
        origin = apply(full, 0.0, state.rise)
        end = apply(mat_mul([1, 0, 0, 1, advance, 0], full), 0.0, state.rise)
        # The effective size is the nominal size through both matrices; for these
        # documents the vertical scale is 1, but reading it rather than assuming
        # it is what makes the number a measurement.
        vertical_scale = (full[1] ** 2 + full[3] ** 2) ** 0.5
        runs.append({
            "text": "".join(characters),
            "codes": codes,
            "font": font.resource_name,
            "font_family": font.family,
            "nominal_size_pt": state.size,
            "size_pt": state.size * vertical_scale,
            "x_pt": origin[0],
            "y_pt": origin[1],
            "end_x_pt": end[0],
            "width_pt": end[0] - origin[0],
            "render_mode": state.render_mode,
            **font.style(),
        })

    def adjust(amount: float) -> None:
        nonlocal tm
        shift = -amount / 1000.0 * state.size * state.horizontal_scale
        tm = mat_mul([1, 0, 0, 1, shift, 0], tm)

    def next_line(tx: float, ty: float) -> None:
        nonlocal tm, tlm
        tlm = mat_mul([1, 0, 0, 1, tx, ty], tlm)
        tm = list(tlm)

    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(list(ctm))
            state_stack.append(state)
        elif operator == b"Q":
            ctm = stack.pop() if stack else list(IDENTITY)
            state = state_stack.pop() if state_stack else TextState()
        elif operator == b"cm" and len(operands) == 6:
            ctm = mat_mul([float(v) for v in operands], ctm)
        elif operator == b"BT":
            tm = list(IDENTITY)
            tlm = list(IDENTITY)
        elif operator == b"ET":
            pass
        elif operator == b"Tf" and len(operands) == 2:
            state.font = fonts.get(str(operands[0]))
            state.size = float(operands[1])
        elif operator == b"Td" and len(operands) == 2:
            next_line(float(operands[0]), float(operands[1]))
        elif operator == b"TD" and len(operands) == 2:
            state.leading = -float(operands[1])
            next_line(float(operands[0]), float(operands[1]))
        elif operator == b"Tm" and len(operands) == 6:
            tlm = [float(v) for v in operands]
            tm = list(tlm)
        elif operator == b"T*":
            next_line(0.0, -state.leading)
        elif operator == b"TL" and operands:
            state.leading = float(operands[0])
        elif operator == b"Tc" and operands:
            state.char_spacing = float(operands[0])
        elif operator == b"Tw" and operands:
            state.word_spacing = float(operands[0])
        elif operator == b"Tz" and operands:
            state.horizontal_scale = float(operands[0]) / 100.0
        elif operator == b"Ts" and operands:
            state.rise = float(operands[0])
        elif operator == b"Tr" and operands:
            state.render_mode = int(operands[0])
        elif operator == b"Tj" and operands:
            show(_decode_string(operands[0]))
        elif operator == b"'" and operands:
            next_line(0.0, -state.leading)
            show(_decode_string(operands[0]))
        elif operator == b'"' and len(operands) == 3:
            state.word_spacing = float(operands[0])
            state.char_spacing = float(operands[1])
            next_line(0.0, -state.leading)
            show(_decode_string(operands[2]))
        elif operator == b"TJ" and operands:
            for item in operands[0]:
                if isinstance(item, (int, float)):
                    adjust(float(item))
                else:
                    show(_decode_string(item))
    return runs


def group_lines(runs: List[Dict[str, Any]], tolerance_pt: float = 0.6) -> List[Dict[str, Any]]:
    """Group runs sharing a baseline into lines, left to right.

    ``tolerance_pt`` absorbs the small vertical shifts of inline maths and
    superscripts sitting on the same line; anything further off is a different
    line and is kept as one. Subscripts that fall outside the tolerance appear as
    their own line, which is correct for measurement and is why the HTML places
    runs, not lines, when a line has more than one baseline.
    """
    ordered = sorted(runs, key=lambda run: (-run["y_pt"], run["x_pt"]))
    lines: List[Dict[str, Any]] = []
    for run in ordered:
        if lines and abs(lines[-1]["baseline_pt"] - run["y_pt"]) <= tolerance_pt:
            lines[-1]["runs"].append(run)
        else:
            lines.append({"baseline_pt": run["y_pt"], "runs": [run]})
    for line in lines:
        line["runs"].sort(key=lambda run: run["x_pt"])
        line["text"] = "".join(run["text"] for run in line["runs"])
        line["x_pt"] = min(run["x_pt"] for run in line["runs"])
        line["end_x_pt"] = max(run["end_x_pt"] for run in line["runs"])
        line["width_pt"] = line["end_x_pt"] - line["x_pt"]
        line["max_size_pt"] = max(run["size_pt"] for run in line["runs"])
        line["baseline_pt"] = sum(run["y_pt"] for run in line["runs"]) / len(line["runs"])
    return lines


# --------------------------------------------------------------------------
# Vector graphics: rules, and the box the figure occupies
# --------------------------------------------------------------------------

def filled_rectangles(page, reader) -> List[Dict[str, Any]]:
    """Axis-aligned filled rectangles — TeX's rules: the header line, the slot.

    Only ``re``-then-fill is recognised, which is what TeX emits for a rule.
    General paths are out of scope: a page whose header line is a bezier would
    need a different reader, and pretending otherwise would report a wrong box.
    """
    from pypdf.generic import ContentStream

    contents = page.get_contents()
    if contents is None:
        return []
    stream = ContentStream(contents, reader)

    ctm: Matrix = list(IDENTITY)
    stack: List[Matrix] = []
    pending: List[Tuple[List[float], Matrix]] = []
    found: List[Dict[str, Any]] = []

    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(list(ctm))
        elif operator == b"Q":
            ctm = stack.pop() if stack else list(IDENTITY)
        elif operator == b"cm" and len(operands) == 6:
            ctm = mat_mul([float(v) for v in operands], ctm)
        elif operator == b"re" and len(operands) == 4:
            pending.append(([float(v) for v in operands], list(ctm)))
        elif operator in (b"f", b"F", b"f*", b"b", b"b*", b"B", b"B*"):
            for (x, y, w, h), matrix in pending:
                corners = [
                    apply(matrix, x, y), apply(matrix, x + w, y),
                    apply(matrix, x + w, y + h), apply(matrix, x, y + h),
                ]
                xs = [point[0] for point in corners]
                ys = [point[1] for point in corners]
                found.append({
                    "x_pt": min(xs), "y_pt": min(ys),
                    "width_pt": max(xs) - min(xs), "height_pt": max(ys) - min(ys),
                })
            pending = []
        elif operator in (b"n", b"S", b"s", b"W", b"W*"):
            pending = []
    return found


def form_boxes(page, reader) -> List[Dict[str, Any]]:
    """Every Form XObject drawn on the page, with the box it really occupies."""
    from pypdf.generic import ContentStream

    resources = page.get("/Resources")
    if resources is None:
        return []
    xobjects = resources.get_object().get("/XObject")
    xobjects = xobjects.get_object() if xobjects is not None else {}
    contents = page.get_contents()
    if contents is None:
        return []
    stream = ContentStream(contents, reader)

    ctm: Matrix = list(IDENTITY)
    stack: List[Matrix] = []
    found: List[Dict[str, Any]] = []
    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(list(ctm))
        elif operator == b"Q":
            ctm = stack.pop() if stack else list(IDENTITY)
        elif operator == b"cm" and len(operands) == 6:
            ctm = mat_mul([float(v) for v in operands], ctm)
        elif operator == b"Do" and operands:
            entry = xobjects.get(operands[0])
            if entry is None:
                continue
            obj = entry.get_object()
            if obj.get("/Subtype") != "/Form":
                continue
            bbox = [float(v) for v in obj.get("/BBox", [0, 0, 0, 0])]
            matrix = mat_mul([float(v) for v in obj.get("/Matrix", IDENTITY)], ctm)
            corners = [
                apply(matrix, bbox[0], bbox[1]), apply(matrix, bbox[2], bbox[1]),
                apply(matrix, bbox[2], bbox[3]), apply(matrix, bbox[0], bbox[3]),
            ]
            xs = [point[0] for point in corners]
            ys = [point[1] for point in corners]
            found.append({
                "name": str(operands[0]),
                "x_pt": min(xs), "y_pt": min(ys),
                "width_pt": max(xs) - min(xs), "height_pt": max(ys) - min(ys),
                "bbox_pt": bbox,
            })
    return found


def describe_page(pdf_path: str, index: int = 0) -> Dict[str, Any]:
    """Everything the HTML generator and the calibration need from one page."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    page = reader.pages[index]
    box = page.mediabox
    runs = text_runs(page, reader)
    lines = group_lines(runs)
    fonts = page_fonts(page)
    return {
        "source": os.path.abspath(pdf_path),
        "page_index": index,
        "mediabox_pt": [float(box.left), float(box.bottom), float(box.right), float(box.top)],
        "width_pt": float(box.width),
        "height_pt": float(box.height),
        "width_mm": round(pdf_pt_to_mm(float(box.width)), 4),
        "height_mm": round(pdf_pt_to_mm(float(box.height)), 4),
        "fonts": [font.describe() for font in sorted(fonts.values(), key=lambda f: f.resource_name)],
        "runs": runs,
        "lines": lines,
        "rules": filled_rectangles(page, reader),
        "forms": form_boxes(page, reader),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf")
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--lines", action="store_true", help="Print the lines instead of JSON.")
    args = parser.parse_args(argv)

    described = describe_page(args.pdf, args.page)
    if args.lines:
        print("%.2f x %.2f pt (%.2f x %.2f mm), %d runs in %d lines"
              % (described["width_pt"], described["height_pt"],
                 described["width_mm"], described["height_mm"],
                 len(described["runs"]), len(described["lines"])))
        for line in described["lines"]:
            print("  y=%8.3f x=%7.3f w=%7.3f  %s"
                  % (line["baseline_pt"], line["x_pt"], line["width_pt"], line["text"][:88]))
        for rule in described["rules"]:
            print("  rule x=%.2f y=%.2f %.2f x %.2f"
                  % (rule["x_pt"], rule["y_pt"], rule["width_pt"], rule["height_pt"]))
        for form in described["forms"]:
            print("  form %s x=%.2f y=%.2f %.2f x %.2f pt (%.2f x %.2f mm)"
                  % (form["name"], form["x_pt"], form["y_pt"], form["width_pt"], form["height_pt"],
                     pdf_pt_to_mm(form["width_pt"]), pdf_pt_to_mm(form["height_pt"])))
        return 0
    json.dump(described, sys.stdout, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
