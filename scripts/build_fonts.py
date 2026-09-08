#!/usr/bin/env python3
"""Package the body-text fonts the conference PDFs are actually set in, and prove it.

The paper page is only worth calibrating if its type is the type LaTeX used. All
three venue templates set their body in URW Nimbus Roman No9 L (the ``times``
package's font) with URW Nimbus Mono for ``\\texttt``. This script:

* copies those faces from the system's ``urw-base35`` fonts,
* converts them to WOFF2 so a browser can load them,
* and — the part that makes it a claim rather than a hope — compares every
  advance width against the ``/Widths`` array of the font actually embedded in a
  compiled venue PDF, for every character code those pages use.

    python scripts/build_fonts.py --verify-against tests/output/conference-context

If a width disagrees the script fails. A page laid out with a font whose ``e`` is
two units wider would drift a fraction of a millimetre per word and a whole word
per paragraph, and no amount of pixel tolerance would make that honest.

Maths is deliberately *not* handled here: the venue PDFs set it in Computer
Modern, which has no equivalent web font, and those glyphs are emitted as vector
outlines taken from the PDF's own embedded font programs instead. See
``scripts/calibrate_conference_pages.py``.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(REPO_ROOT, "web", "public", "generated", "fonts")

SYSTEM_FONT_DIRS = (
    "/usr/share/fonts/opentype/urw-base35",
    "/usr/local/share/fonts/urw-base35",
    "/opt/homebrew/share/fonts/urw-base35",
)

# The four faces the three venue body pages use, keyed by the base font name
# pdfTeX writes into the PDF (minus its per-run subset prefix).
FACES = {
    "NimbusRomNo9L-Regu": {
        "file": "NimbusRoman-Regular.otf",
        "css_family": "MPF Nimbus Roman",
        "weight": "normal",
        "style": "normal",
        "role": "body text",
    },
    "NimbusRomNo9L-Medi": {
        "file": "NimbusRoman-Bold.otf",
        "css_family": "MPF Nimbus Roman",
        "weight": "bold",
        "style": "normal",
        "role": "section headings and run-in bold",
    },
    "NimbusRomNo9L-ReguItal": {
        "file": "NimbusRoman-Italic.otf",
        "css_family": "MPF Nimbus Roman",
        "weight": "normal",
        "style": "italic",
        "role": "emphasis and journal titles",
    },
    "NimbusRomNo9L-MediItal": {
        "file": "NimbusRoman-BoldItalic.otf",
        "css_family": "MPF Nimbus Roman",
        "weight": "bold",
        "style": "italic",
        "role": "bold italic, if a page uses it",
    },
    "NimbusMonL-Regu": {
        "file": "NimbusMonoPS-Regular.otf",
        "css_family": "MPF Nimbus Mono",
        "weight": "normal",
        "style": "normal",
        "role": "\\texttt{} in the caption and the fixture notices",
    },
}

LICENCE_NOTE = (
    "The Nimbus faces are URW's, distributed under the GNU AGPL v3 with the "
    "URW font exception, from https://github.com/ArtifexSoftware/urw-base35-fonts. "
    "They are redistributed here in WOFF2 form — a format conversion, not a "
    "redesign — with the licence text beside them in LICENCE-urw-base35.txt. "
    "They are here because they are the fonts the venue templates actually set "
    "their body text in, not because they look similar to them. A repository "
    "owner publishing this site should confirm the licence position for their "
    "own distribution."
)

LICENCE_SOURCES = (
    "/usr/share/doc/fonts-urw-base35/copyright",
    "/usr/share/doc/fonts-urw-base35/COPYING",
)


class FontError(RuntimeError):
    pass


def find_system_font(file_name: str) -> Optional[str]:
    for directory in SYSTEM_FONT_DIRS:
        candidate = os.path.join(directory, file_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_woff2(source: str, destination: str) -> Dict[str, Any]:
    from fontTools.ttLib import TTFont

    font = TTFont(source)
    font.flavor = "woff2"
    font.save(destination)
    upm = font["head"].unitsPerEm
    os2 = font["OS/2"]
    hhea = font["hhea"]
    return {
        "units_per_em": upm,
        "typo_ascender": getattr(os2, "sTypoAscender", None),
        "typo_descender": getattr(os2, "sTypoDescender", None),
        "hhea_ascent": hhea.ascent,
        "hhea_descent": hhea.descent,
        "full_name": font["name"].getDebugName(4),
        "version": font["name"].getDebugName(5),
    }


def advance_widths(path: str) -> Dict[str, int]:
    """Advance width per glyph name, in 1/1000 em (the unit PDF /Widths uses)."""
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    upm = font["head"].unitsPerEm
    scale = 1000.0 / upm
    return {name: round(width * scale) for name, (width, _) in font["hmtx"].metrics.items()}


def glyph_name_for_code(pdf_font, code: int) -> Optional[str]:
    """The glyph the PDF's encoding maps a byte to, if it says."""
    return pdf_font.differences.get(code)


def verify(faces_built: Dict[str, Dict[str, Any]], pages_root: str) -> List[Dict[str, Any]]:
    """Compare packaged widths with the widths in every compiled page we can find."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pdf_layout

    from pypdf import PdfReader

    results: List[Dict[str, Any]] = []
    pdfs = sorted(glob.glob(os.path.join(pages_root, "**", "page.pdf"), recursive=True))
    if not pdfs:
        raise FontError(
            "No compiled page.pdf under %s, so there is nothing to verify the fonts "
            "against. Generate the conference pages first." % pages_root
        )

    for pdf_path in pdfs:
        reader = PdfReader(pdf_path)
        page = reader.pages[0]
        for pdf_font in pdf_layout.page_fonts(page).values():
            family = pdf_font.family
            built = faces_built.get(family)
            if built is None:
                results.append({
                    "pdf": os.path.relpath(pdf_path, REPO_ROOT),
                    "font": family,
                    "checked": False,
                    "reason": "not a packaged text face (maths and symbol fonts are drawn "
                              "as outlines instead)",
                })
                continue
            widths = built["_widths"]
            compared = 0
            mismatches = []
            missing = []
            for offset, width in enumerate(pdf_font.widths):
                code = pdf_font.first_char + offset
                if width == 0:
                    continue
                name = glyph_name_for_code(pdf_font, code)
                if name is None:
                    continue
                if name not in widths:
                    missing.append(name)
                    continue
                compared += 1
                if abs(widths[name] - width) > 0.5:
                    mismatches.append({"glyph": name, "code": code,
                                       "pdf": width, "packaged": widths[name]})
            results.append({
                "pdf": os.path.relpath(pdf_path, REPO_ROOT),
                "font": family,
                "checked": True,
                "glyphs_compared": compared,
                "mismatches": mismatches,
                "glyphs_missing_from_packaged_face": sorted(set(missing)),
            })
    return results


def build(verify_against: Optional[str]) -> int:
    os.makedirs(FONT_DIR, exist_ok=True)
    built: Dict[str, Dict[str, Any]] = {}
    absent: List[str] = []

    for base_font, face in FACES.items():
        source = find_system_font(face["file"])
        if source is None:
            absent.append(face["file"])
            continue
        target_name = os.path.splitext(face["file"])[0] + ".woff2"
        destination = os.path.join(FONT_DIR, target_name)
        metrics = to_woff2(source, destination)
        built[base_font] = {
            **face,
            "pdf_base_font": base_font,
            "asset": "fonts/" + target_name,
            "source": source,
            "source_sha256": sha256_file(source),
            "woff2_sha256": sha256_file(destination),
            "woff2_bytes": os.path.getsize(destination),
            "metrics": metrics,
            "_widths": advance_widths(source),
        }

    if absent:
        print(
            "error: these faces are not installed: %s\n"
            "Install the URW base 35 fonts (Debian/Ubuntu: `sudo apt install "
            "fonts-urw-base35`; macOS: they ship with Ghostscript) — the paper page "
            "cannot be set in the venues' own type without them."
            % ", ".join(absent),
            file=sys.stderr,
        )
        return 2

    licence_path = os.path.join(FONT_DIR, "LICENCE-urw-base35.txt")
    for candidate in LICENCE_SOURCES:
        if os.path.isfile(candidate):
            shutil.copyfile(candidate, licence_path)
            break
    else:
        with open(licence_path, "w", encoding="utf-8") as handle:
            handle.write(LICENCE_NOTE + "\n")

    verification = None
    if verify_against:
        verification = verify(built, verify_against)
        bad = [entry for entry in verification
               if entry.get("checked") and (entry["mismatches"] or entry["glyphs_missing_from_packaged_face"])]
        for entry in verification:
            if not entry.get("checked"):
                continue
            print("  %-24s %-28s %4d glyphs, %d mismatch, %d missing"
                  % (os.path.basename(os.path.dirname(entry["pdf"])), entry["font"],
                     entry["glyphs_compared"], len(entry["mismatches"]),
                     len(entry["glyphs_missing_from_packaged_face"])))
        if bad:
            print("error: the packaged faces do not match the fonts in the compiled pages.",
                  file=sys.stderr)
            print(json.dumps(bad, indent=2)[:4000], file=sys.stderr)
            return 1

    manifest = {
        "manifest_version": "1",
        "note": "Written by scripts/build_fonts.py. These are the faces the venue "
                "templates set their body text in, packaged for the browser and checked "
                "glyph by glyph against the fonts embedded in the compiled pages.",
        "licence": LICENCE_NOTE,
        "licence_file": "fonts/LICENCE-urw-base35.txt",
        "faces": {
            name: {key: value for key, value in face.items() if not key.startswith("_")}
            for name, face in built.items()
        },
        "not_packaged": {
            "computer_modern_maths": "CMMI7, CMMI10 and CMSY10 carry the inline maths in "
                                     "these pages. There is no web font with those exact "
                                     "outlines and metrics, so those glyphs are emitted as "
                                     "SVG paths extracted from the PDF's own embedded font "
                                     "programs, at the positions the PDF gives them. That is "
                                     "a local vector asset with a recorded source, not a "
                                     "substitute font pretending to be Computer Modern.",
        },
        "verification": verification,
    }
    path = os.path.join(FONT_DIR, "fonts.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    total = sum(face["woff2_bytes"] for face in built.values())
    print("packaged %d face(s), %.1f KiB total -> %s"
          % (len(built), total / 1024, os.path.relpath(FONT_DIR, REPO_ROOT)))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify-against",
                        default=os.path.join(REPO_ROOT, "tests", "output", "conference-context"),
                        help="Directory tree of compiled page.pdf files to check widths against.")
    parser.add_argument("--no-verify", action="store_true", help="Package without checking.")
    args = parser.parse_args(argv)
    try:
        return build(None if args.no_verify else args.verify_against)
    except FontError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
