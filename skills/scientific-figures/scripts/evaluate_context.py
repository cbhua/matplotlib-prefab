"""Put a rendered figure into a real conference body page and measure what happens to it.

A ``figure.pdf`` on its own tells you the canvas is 85 mm wide. It does not tell
you whether the tick labels survive being placed at half the text width of a
two-column template, which is the only size the reader ever sees. This script
compiles the figure into a venue's own LaTeX style, keeps the single body page
the figure landed on, and reports the geometry it measured *from the compiled
PDF* rather than from the ``\\includegraphics`` argument it wrote.

Two passes, because the target width is a property of the template, not of us:

1. **Probe.** Compile the venue wrapper with a placeholder box in the float, and
   read back ``\\textwidth``, ``\\columnwidth``, the ``\\linewidth`` the float
   actually sees, and the body and caption font sizes — measured by TeX, in the
   document, at the insertion point.
2. **Place.** Derive a profile at that target width (canvas width only; every
   font and line width keeps its value), render through the ordinary
   ``render.py``, compile again with the real figure, locate the page, extract
   it, rasterise it, report.

Pass ``--figure-dir`` instead of ``--spec`` to skip the derivation and place an
already-rendered figure at whatever size it happens to be. That is the path that
shows a real reduction: an 85 mm figure in a 69.85 mm slot is reported as a
0.82 scale factor and correspondingly smaller effective type, not as "still 9 pt".

Portability
-----------
Nothing here knows where this repository is. The fixtures — venue styles, the
body-text excerpt, the wrappers — are passed in by path, so a copy of
``skills/scientific-figures/`` elsewhere still works as long as the caller says
where its fixtures live. ``tests/render_conference_context.py`` is the entry
point that supplies this repository's.

Exit codes
----------
``0`` the page was produced and no check failed, ``1`` a check failed, ``2`` the
inputs were rejected, ``3`` a required external tool is missing. Never ``0`` on a
skipped evaluation: an incomplete context check is not a passing one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import figure_core  # noqa: E402

PASS = "pass"
WARN = "warn"
FAIL = "fail"
NOT_CHECKED = "not_checked"

# TeX's point is 1/72.27 in; PDF's is 1/72 in. Mixing them is a ~0.4% error,
# which is the same order as the tolerance this script checks widths against, so
# every length carries its unit in its name.
TEX_PT_PER_INCH = 72.27
PDF_PT_PER_INCH = 72.0
MM_PER_INCH = figure_core.MM_PER_INCH

REQUIRED_TOOLS = {
    "latexmk": "build driver (reruns pdflatex and bibtex until references converge)",
    "pdflatex": "typesetter",
    "bibtex": "bibliography",
    "pdftoppm": "page rasteriser (poppler-utils)",
}

INSTALL_HINT = (
    "Install them, e.g. on Debian/Ubuntu:\n"
    "  sudo apt install texlive-latex-recommended texlive-fonts-recommended \\\n"
    "                   texlive-latex-extra latexmk poppler-utils\n"
    "on macOS with Homebrew:\n"
    "  brew install --cask mactex-no-gui && brew install poppler\n"
    "\n"
    "These are needed only for the conference context evaluation. Rendering a\n"
    "figure with render.py needs no LaTeX at all."
)

FIGURE_LABEL = "fig:mpf-target"
FIGURE_BASENAME = "figure"
JOBNAME = "document"


class ContextError(ValueError):
    """The evaluation could not start: bad paths, unknown venue, malformed fixtures."""


class MissingToolError(RuntimeError):
    """A required external program is not on PATH."""


# --------------------------------------------------------------------------
# Small utilities
# --------------------------------------------------------------------------

def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def tex_pt_to_mm(value_tex_pt: float) -> float:
    return value_tex_pt / TEX_PT_PER_INCH * MM_PER_INCH


def pdf_pt_to_mm(value_pdf_pt: float) -> float:
    return value_pdf_pt / PDF_PT_PER_INCH * MM_PER_INCH


def escape_tex(text: str) -> str:
    """Make arbitrary text safe to drop into a caption.

    Captions carry case names and file paths that come from a caller. None of it
    is allowed to become an executable control sequence, so every TeX-special
    character is neutralised rather than trusted.
    """
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "^": r"\textasciicircum{}",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "%": r"\%",
    }
    return "".join(replacements.get(char, char) for char in text)


def check_entry(check_id: str, status: str, message: str, **detail: Any) -> Dict[str, Any]:
    entry = {"id": check_id, "status": status, "message": message}
    if detail:
        entry["detail"] = detail
    return entry


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

class Fixtures:
    """Where the venue styles, the body-text excerpt and the wrappers live.

    ``root`` is the convenient case: a directory holding ``conferences/``,
    ``article-context/`` and ``wrappers/``. This repository does not use that
    shape (the wrappers sit with the tests, not with the fixtures), so each
    directory can be given separately instead.
    """

    def __init__(
        self,
        conferences: str,
        article: str,
        wrappers: str,
    ) -> None:
        self.conferences = os.path.abspath(conferences)
        self.article = os.path.abspath(article)
        self.wrappers = os.path.abspath(wrappers)

        for label, path in (
            ("conferences", self.conferences),
            ("article-context", self.article),
            ("wrappers", self.wrappers),
        ):
            if not os.path.isdir(path):
                raise ContextError("The %s fixture directory does not exist: %s" % (label, path))

        self.manifest_path = os.path.join(self.conferences, "manifest.json")
        if not os.path.isfile(self.manifest_path):
            raise ContextError("No manifest.json in %s." % self.conferences)
        with open(self.manifest_path, encoding="utf-8") as handle:
            self.manifest = json.load(handle)

        self.body_path = os.path.join(self.article, "body.tex")
        self.bib_path = os.path.join(self.article, "references.bib")
        for path in (self.body_path, self.bib_path):
            if not os.path.isfile(path):
                raise ContextError("Missing article-context fixture: %s" % path)

        self.measure_path = os.path.join(self.wrappers, "measure.tex")
        if not os.path.isfile(self.measure_path):
            raise ContextError("Missing measurement harness: %s" % self.measure_path)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Fixtures":
        root = args.fixtures_root
        def pick(explicit: Optional[str], under_root: str, label: str) -> str:
            if explicit:
                return explicit
            if root:
                return os.path.join(root, under_root)
            raise ContextError(
                "Nothing says where the %s fixtures are. Pass --fixtures-root, or "
                "--%s-dir." % (label, label)
            )
        return cls(
            conferences=pick(args.conferences_dir, "conferences", "conferences"),
            article=pick(args.article_dir, "article-context", "article"),
            wrappers=pick(args.wrappers_dir, "wrappers", "wrappers"),
        )

    def venue_ids(self) -> List[str]:
        return [entry["id"] for entry in self.manifest["venues"]]

    def venue(self, venue_id: str) -> Dict[str, Any]:
        for entry in self.manifest["venues"]:
            if entry["id"] == venue_id:
                return entry
        raise ContextError(
            "Unknown venue %r. This fixture set has: %s."
            % (venue_id, ", ".join(sorted(self.venue_ids())))
        )

    def layout(self, venue_id: str, layout_id: Optional[str] = None) -> Dict[str, Any]:
        """One width mode of one venue, defaulting to the venue's own default.

        A fixture set written before width modes existed has no ``layouts`` key;
        it is read as a single mode built from the venue's own width rule, so the
        older shape keeps behaving exactly as it did.
        """
        venue = self.venue(venue_id)
        layouts = venue.get("layouts")
        if not layouts:
            return {
                "id": "narrow",
                "label": venue["target_width_rule"],
                "float_environment": "figure",
                "target_width_rule": venue["target_width_rule"],
                "target_width_factor": float(venue["target_width_factor"]),
                "target_width_basis": venue.get("target_width_basis"),
                "note": "Synthesised from the venue's own width rule: this fixture set "
                        "predates width modes.",
            }
        wanted = layout_id or venue.get("default_layout") or layouts[0]["id"]
        for entry in layouts:
            if entry["id"] == wanted:
                return entry
        raise ContextError(
            "Unknown layout %r for %s. That venue has: %s."
            % (wanted, venue_id, ", ".join(entry["id"] for entry in layouts))
        )

    def layout_ids(self, venue_id: str) -> List[str]:
        venue = self.venue(venue_id)
        return [entry["id"] for entry in venue.get("layouts", [])] or ["narrow"]

    def wrapper_path(self, venue_id: str) -> str:
        path = os.path.join(self.wrappers, "%s.tex" % venue_id)
        if not os.path.isfile(path):
            raise ContextError("No wrapper document for %r at %s." % (venue_id, path))
        return path

    def venue_dir(self, venue_id: str) -> str:
        path = os.path.join(self.conferences, venue_id)
        if not os.path.isdir(path):
            raise ContextError("No template directory for %r at %s." % (venue_id, path))
        return path


# --------------------------------------------------------------------------
# Toolchain
# --------------------------------------------------------------------------

def missing_tools() -> List[str]:
    return [name for name in REQUIRED_TOOLS if shutil.which(name) is None]


def require_tools() -> Dict[str, str]:
    absent = missing_tools()
    if absent:
        raise MissingToolError(
            "The context evaluation needs %s, which %s not on PATH.\n\n%s"
            % (
                ", ".join(
                    "%s (%s)" % (name, REQUIRED_TOOLS[name]) for name in sorted(absent)
                ),
                "is" if len(absent) == 1 else "are",
                INSTALL_HINT,
            )
        )
    return {name: shutil.which(name) for name in sorted(REQUIRED_TOOLS)}


def tool_versions(paths: Dict[str, str]) -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for name in sorted(paths):
        flag = "--version" if name != "bibtex" else "-version"
        try:
            result = subprocess.run(
                [paths[name], flag], capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            versions[name] = "unknown"
            continue
        first = (result.stdout or result.stderr).strip().splitlines()
        versions[name] = first[0].strip() if first else "unknown"
    return versions


# --------------------------------------------------------------------------
# The generated float
# --------------------------------------------------------------------------

def figure_block(
    width_factor: float,
    caption: str,
    placeholder: bool,
    float_environment: str = "figure",
) -> str:
    """The ``context-figure.tex`` that body.tex inputs.

    The width is written the way an author writes it — a fraction of
    ``\\linewidth`` — so the placed size is the template's own arithmetic and not
    a number this script talked itself into. ``\\linewidth`` inside the float is
    ``\\textwidth`` in a one-column document, ``\\columnwidth`` in a two-column
    one, and ``\\textwidth`` again inside a ``figure*``. That is exactly the
    distinction between the two width modes, and it is the template that draws
    it, not this function.
    """
    if float_environment not in ("figure", "figure*"):
        raise ContextError(
            "Unknown float environment %r. This fixture places a figure or a figure*; "
            "anything else would need its own measurement path." % float_environment
        )
    if abs(width_factor - 1.0) < 1e-12:
        width_arg = r"\linewidth"
    else:
        width_arg = "%g\\linewidth" % width_factor
    if placeholder:
        # The probe pass only needs the float to exist so \linewidth can be read
        # from inside it; a rule needs no image on disk.
        content = r"\rule{%s}{40mm}" % width_arg
    else:
        content = r"\includegraphics[width=%s]{%s}" % (width_arg, FIGURE_BASENAME)
    return "\n".join(
        [
            "%% Generated by evaluate_context.py. Do not edit; it is rewritten every run.",
            r"\mpfprobebody",
            r"\begin{%s}[t]" % float_environment,
            r"  \centering",
            r"  \mpfprobefloat",
            "  %s" % content,
            r"  \caption{%s}" % caption,
            r"  \label{%s}" % FIGURE_LABEL,
            r"\end{%s}" % float_environment,
            "",
        ]
    )


def default_caption(
    venue: Dict[str, Any],
    case_id: str,
    source: str,
    layout: Optional[Dict[str, Any]] = None,
) -> str:
    factor = float((layout or venue)["target_width_factor"])
    where = (layout or {}).get("label") or (
        "half the line width" if factor < 1.0 else "the full line width"
    )
    return (
        "Synthetic evaluation fixture, not a result. Rendered by "
        "\\texttt{matplotlib-prefab} from \\texttt{%s} and placed at %s. "
        "This page exists only to show the figure at its final "
        "printed size in the %s body text; the surrounding prose is an excerpt "
        "reproduced as typographic context. Case \\texttt{%s}."
        % (
            escape_tex(source),
            escape_tex(where),
            escape_tex(venue["name"]),
            escape_tex(case_id),
        )
    )


# --------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------

class CompileResult:
    def __init__(self, returncode: int, stdout: str, stderr: str, log: str, timed_out: bool):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.log = log
        self.timed_out = timed_out

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def stage_build_dir(
    build_dir: str,
    fixtures: Fixtures,
    venue: Dict[str, Any],
) -> None:
    """Copy everything the compile needs into an empty directory.

    The build runs there with nothing else on TEXINPUTS, so the venue's own
    bundled fancyhdr/natbib/algorithm are the ones that get used, exactly as
    they would be for an author unpacking the template.
    """
    venue_dir = fixtures.venue_dir(venue["id"])
    for entry in venue["files"]:
        source = os.path.join(venue_dir, entry["path"])
        if not os.path.isfile(source):
            raise ContextError(
                "manifest.json lists %s for %s but it is not in %s."
                % (entry["path"], venue["id"], venue_dir)
            )
        shutil.copyfile(source, os.path.join(build_dir, entry["path"]))

    shutil.copyfile(fixtures.wrapper_path(venue["id"]), os.path.join(build_dir, "%s.tex" % JOBNAME))
    shutil.copyfile(fixtures.measure_path, os.path.join(build_dir, "measure.tex"))
    shutil.copyfile(fixtures.body_path, os.path.join(build_dir, "body.tex"))
    shutil.copyfile(fixtures.bib_path, os.path.join(build_dir, "references.bib"))


def compile_document(build_dir: str, timeout: int) -> CompileResult:
    """Run latexmk to convergence, with shell escape off and a hard timeout."""
    env = dict(os.environ)
    # Belt and braces: no \write18, and no writing outside the build directory.
    env["shell_escape"] = "f"
    env["openout_any"] = "p"
    env["TEXMFOUTPUT"] = build_dir
    env["TEXINPUTS"] = ".:"
    env["BIBINPUTS"] = ".:"
    env["BSTINPUTS"] = ".:"
    env.pop("TEXMFHOME", None)

    command = [
        "latexmk",
        "-pdf",
        "-quiet",
        "-interaction=nonstopmode",
        "-file-line-error",
        "-no-shell-escape",
        "-jobname=%s" % JOBNAME,
        "%s.tex" % JOBNAME,
    ]
    timed_out = False
    try:
        result = subprocess.run(
            command,
            cwd=build_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")

    log_path = os.path.join(build_dir, "%s.log" % JOBNAME)
    log = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            log = handle.read()
    return CompileResult(returncode, stdout, stderr, log, timed_out)


def read_measures(build_dir: str) -> Dict[str, str]:
    path = os.path.join(build_dir, "%s.measures" % JOBNAME)
    if not os.path.isfile(path):
        return {}
    measures: Dict[str, str] = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                measures[key.strip()] = value.strip()
    return measures


_LENGTH_RE = re.compile(r"^(-?[0-9.]+)pt$")


def measured_tex_pt(measures: Dict[str, str], key: str) -> Optional[float]:
    raw = measures.get(key)
    if raw is None:
        return None
    match = _LENGTH_RE.match(raw)
    if not match:
        return None
    return float(match.group(1))


def measured_float(measures: Dict[str, str], key: str) -> Optional[float]:
    raw = measures.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


_UNDEFINED_RE = re.compile(r"^(?:LaTeX|Package natbib) Warning: (Citation|Reference) .*", re.M)
_ERROR_RE = re.compile(r"^(?:.*?:\d+: |! ).*$", re.M)
_OVERFULL_RE = re.compile(r"^(Overfull|Underfull) \\[hv]box.*$", re.M)


def log_diagnostics(log: str) -> Dict[str, List[str]]:
    # finditer, not findall: the patterns have groups, and it is the whole warning
    # line that is worth reporting, not the captured word.
    undefined_lines = sorted({m.group(0).strip() for m in _UNDEFINED_RE.finditer(log)}) if log else []
    errors = [m.group(0).strip() for m in _ERROR_RE.finditer(log)] if log else []
    boxes = [m.group(0).strip() for m in _OVERFULL_RE.finditer(log)] if log else []
    return {
        "undefined_citations_or_references": undefined_lines,
        "errors": errors[:40],
        "bad_boxes": boxes[:40],
    }


# --------------------------------------------------------------------------
# PDF geometry
# --------------------------------------------------------------------------

def _mat_mul(m: Sequence[float], n: Sequence[float]) -> List[float]:
    """Concatenate two PDF matrices [a b c d e f], m applied first."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return [
        a * A + b * C,
        a * B + b * D,
        c * A + d * C,
        c * B + d * D,
        e * A + f * C + E,
        e * B + f * D + F,
    ]


def _apply(matrix: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def read_pdf(path: str, what: str):
    """Open a PDF, turning a parse failure into a message instead of a traceback.

    A truncated or corrupt figure is an ordinary thing to be handed, and the
    caller needs to be told which file is bad — not shown pypdf's stack.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        if not reader.pages:
            raise ContextError("%s (%s) has no pages." % (what, path))
        # Touch the first page so a lazily-parsed corruption surfaces here.
        _ = reader.pages[0].mediabox
    except ContextError:
        raise
    except Exception as exc:
        raise ContextError(
            "%s could not be read as a PDF: %s (%s). Re-render it before placing it "
            "in a page." % (what, path, exc)
        ) from None
    return reader


def placed_forms(page, reader) -> List[Dict[str, Any]]:
    """Every Form XObject drawn on ``page``, with the box it actually occupies.

    This walks the page's content stream and tracks the graphics state, so the
    width reported is the width the viewer will paint — not the width the
    ``\\includegraphics`` argument asked for. Those two agreeing is the whole
    point of the check; taking the second as evidence for the first would prove
    nothing.
    """
    from pypdf.generic import ContentStream

    resources = page.get("/Resources")
    if resources is None:
        return []
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    xobjects = xobjects.get_object() if xobjects is not None else {}

    contents = page.get_contents()
    if contents is None:
        return []
    stream = ContentStream(contents, reader)

    ctm: List[float] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    stack: List[List[float]] = []
    found: List[Dict[str, Any]] = []

    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(list(ctm))
        elif operator == b"Q":
            ctm = stack.pop() if stack else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        elif operator == b"cm" and len(operands) == 6:
            ctm = _mat_mul([float(value) for value in operands], ctm)
        elif operator == b"Do" and operands:
            name = operands[0]
            entry = xobjects.get(name)
            if entry is None:
                continue
            obj = entry.get_object()
            if obj.get("/Subtype") != "/Form":
                continue
            bbox = [float(value) for value in obj.get("/BBox", [0, 0, 0, 0])]
            form_matrix = [float(value) for value in obj.get("/Matrix", [1, 0, 0, 1, 0, 0])]
            full = _mat_mul(form_matrix, ctm)
            corners = [
                _apply(full, bbox[0], bbox[1]),
                _apply(full, bbox[2], bbox[1]),
                _apply(full, bbox[2], bbox[3]),
                _apply(full, bbox[0], bbox[3]),
            ]
            xs = [point[0] for point in corners]
            ys = [point[1] for point in corners]
            found.append(
                {
                    "name": str(name),
                    "bbox_pdf_pt": bbox,
                    "bbox_width_pdf_pt": abs(bbox[2] - bbox[0]),
                    "bbox_height_pdf_pt": abs(bbox[3] - bbox[1]),
                    "ctm": full,
                    "placed_width_pdf_pt": max(xs) - min(xs),
                    "placed_height_pdf_pt": max(ys) - min(ys),
                    "placed_origin_pdf_pt": [min(xs), min(ys)],
                }
            )
    return found


def locate_figure_page(
    pdf_path: str,
    source_width_pdf_pt: float,
    source_height_pdf_pt: float,
) -> Tuple[int, Dict[str, Any], Any]:
    """Find the physical page index carrying the figure, by its drawn geometry.

    Matching is on the form's ``/BBox``, which pdfTeX copies from the included
    file's box, so it identifies our figure among any other forms on the page.
    """
    reader = read_pdf(pdf_path, "The compiled document")
    matches: List[Tuple[int, Dict[str, Any]]] = []
    for index, page in enumerate(reader.pages):
        for form in placed_forms(page, reader):
            if (
                abs(form["bbox_width_pdf_pt"] - source_width_pdf_pt) <= 0.75
                and abs(form["bbox_height_pdf_pt"] - source_height_pdf_pt) <= 0.75
            ):
                matches.append((index, form))
    if not matches:
        raise ContextError(
            "The figure was not found anywhere in the compiled document. Expected a "
            "form XObject with a %.2f x %.2f pt bounding box across %d page(s). The "
            "figure may have failed to embed, or the source PDF may be damaged."
            % (source_width_pdf_pt, source_height_pdf_pt, len(reader.pages))
        )
    if len(matches) > 1:
        raise ContextError(
            "The figure is drawn %d times (pages %s). This fixture places exactly one "
            "figure; something is placing it more than once and the measurement would "
            "be ambiguous."
            % (len(matches), ", ".join(str(index) for index, _ in matches))
        )
    index, form = matches[0]
    return index, form, reader


def extract_single_page(reader, index: int, destination: str) -> Dict[str, Any]:
    """Write page ``index`` out on its own, untouched.

    No scaling, no re-cropping, no re-imposition: the boxes, the running head,
    the folio and the margins are the ones the compiler produced.
    """
    from pypdf import PdfWriter

    source_page = reader.pages[index]
    writer = PdfWriter()
    writer.add_page(source_page)
    with open(destination, "wb") as handle:
        writer.write(handle)

    box = source_page.mediabox
    return {
        "mediabox_pdf_pt": [float(box.left), float(box.bottom), float(box.right), float(box.top)],
        "width_pdf_pt": float(box.width),
        "height_pdf_pt": float(box.height),
        "width_mm": round(pdf_pt_to_mm(float(box.width)), 3),
        "height_mm": round(pdf_pt_to_mm(float(box.height)), 3),
    }


def rasterise(pdf_path: str, png_path: str, dpi: int, timeout: int) -> None:
    prefix = os.path.splitext(png_path)[0]
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-singlefile", pdf_path, prefix],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0 or not os.path.isfile(png_path):
        raise ContextError(
            "pdftoppm failed to rasterise %s (exit %d): %s"
            % (pdf_path, result.returncode, (result.stderr or "").strip())
        )


def page_text(reader, index: int) -> str:
    try:
        return reader.pages[index].extract_text() or ""
    except Exception:  # pragma: no cover - extraction is best-effort evidence
        return ""


# --------------------------------------------------------------------------
# The evaluation
# --------------------------------------------------------------------------

def derive_profile(base_profile: Dict[str, Any], width_mm: float) -> Dict[str, Any]:
    """A copy of the profile at the template's width. Nothing else moves.

    Font sizes and line widths keep their values on purpose: the point of
    rendering at the target width is that the figure arrives on the page at
    scale 1, so a 9 pt label is 9 pt on the page. Shrinking the type here as
    well would defeat the exercise.
    """
    import copy

    derived = copy.deepcopy(base_profile)
    derived["canvas"]["width_mm"] = round(float(width_mm), 3)
    derived["name"] = "%s-context" % base_profile.get("name", "profile")
    derived["note"] = (
        "Derived by evaluate_context.py from %r for one context evaluation: "
        "canvas.width_mm was set to the width measured in the target template and "
        "nothing else was changed. Not a new default; the repository profile is "
        "untouched." % base_profile.get("name", "profile")
    )
    return figure_core.validate_profile(derived)


def source_type_sizes(profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    if not profile:
        return None
    fonts = profile["fonts"]
    lines = profile["lines"]
    return {
        "axis_label_pt": float(fonts["size_axis_label_pt"]),
        "tick_pt": float(fonts["size_tick_pt"]),
        "legend_pt": float(fonts["size_legend_pt"]),
        "title_pt": float(fonts["size_title_pt"]),
        "data_linewidth_pt": float(lines["data_linewidth_pt"]),
    }


def probe_template(
    fixtures: Fixtures,
    venue_id: str,
    layout_id: Optional[str] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Compile the venue wrapper with a placeholder float and report its geometry.

    This is the first half of ``evaluate`` on its own, for the callers that need
    the target width *before* they have a figure to place — the calibration
    generator has to know how big the slot is in order to make a placeholder that
    fills it exactly. Splitting it out keeps one implementation of "what width
    does this template give a figure in this mode"; a second one would be a
    second answer waiting to disagree.
    """
    require_tools()
    venue = fixtures.venue(venue_id)
    layout = fixtures.layout(venue_id, layout_id)
    width_factor = float(layout["target_width_factor"])
    float_environment = layout.get("float_environment", "figure")

    build_dir = tempfile.mkdtemp(prefix="mpf-probe-%s-%s-" % (venue_id, layout["id"]))
    try:
        stage_build_dir(build_dir, fixtures, venue)
        caption = escape_tex("Width probe. No figure is placed in this pass.")
        with open(os.path.join(build_dir, "context-figure.tex"), "w", encoding="utf-8") as handle:
            handle.write(figure_block(width_factor, caption, True, float_environment))
        result = compile_document(build_dir, timeout)
        measures = read_measures(build_dir)
        if not result.ok or "float_linewidth_tex_pt" not in measures:
            raise ContextError(
                "The width probe compile of the %s wrapper in %s mode failed.\n%s"
                % (venue["name"], layout["id"],
                   "\n".join(log_diagnostics(result.log)["errors"][:10]) or result.stderr.strip())
            )
        float_linewidth_tex_pt = measured_tex_pt(measures, "float_linewidth_tex_pt")
        target_width_tex_pt = float_linewidth_tex_pt * width_factor
        return {
            "venue": venue["id"],
            "layout": layout["id"],
            "float_environment": float_environment,
            "width_factor": width_factor,
            "float_linewidth_tex_pt": float_linewidth_tex_pt,
            "float_linewidth_mm": round(tex_pt_to_mm(float_linewidth_tex_pt), 4),
            "target_width_tex_pt": target_width_tex_pt,
            "target_width_mm": round(tex_pt_to_mm(target_width_tex_pt), 4),
            "columns": int(measured_float(measures, "columns") or venue["columns"]),
            "paperwidth_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "paperwidth_tex_pt") or 0.0), 4),
            "paperheight_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "paperheight_tex_pt") or 0.0), 4),
            "textwidth_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "textwidth_tex_pt") or 0.0), 4),
            "textheight_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "textheight_tex_pt") or 0.0), 4),
            "columnwidth_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "columnwidth_tex_pt") or 0.0), 4),
            "columnsep_mm": round(tex_pt_to_mm(measured_tex_pt(measures, "columnsep_tex_pt") or 0.0), 4),
            "body_font_size_pt": measured_float(measures, "body_font_size_pt"),
            "body_baselineskip_tex_pt": measured_tex_pt(measures, "body_baselineskip_tex_pt"),
            "caption_font_size_pt": measured_float(measures, "caption_font_size_pt"),
            "caption_baselineskip_tex_pt": measured_tex_pt(measures, "caption_baselineskip_tex_pt"),
            "margins_tex_pt": {
                key: measured_tex_pt(measures, "%s_tex_pt" % key)
                for key in (
                    "oddsidemargin", "evensidemargin", "topmargin", "headheight",
                    "headsep", "footskip", "parindent", "parskip", "textfloatsep",
                    "intextsep", "dblfloatsep", "dbltextfloatsep",
                    "abovecaptionskip", "belowcaptionskip",
                )
            },
            "text_block_note": "LaTeX puts its origin one inch from the top-left of the "
                               "sheet; the text block's left edge is that inch plus "
                               "oddsidemargin, and its first baseline sits below that inch "
                               "plus topmargin + headheight + headsep. Recorded so a "
                               "reproduction can be checked against the template's own "
                               "arithmetic.",
            "measured_by": "TeX, inside the compiled document at the figure's insertion point",
        }
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def evaluate(
    fixtures: Fixtures,
    venue_id: str,
    case_id: str,
    output_dir: str,
    spec_path: Optional[str] = None,
    figure_dir: Optional[str] = None,
    base_profile_path: Optional[str] = None,
    caption: Optional[str] = None,
    png_dpi: int = 200,
    timeout: int = 300,
    diagnostics_dir: Optional[str] = None,
    layout_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce ``page.pdf``, ``page.png`` and ``context-report.json`` for one case."""
    if bool(spec_path) == bool(figure_dir):
        raise ContextError("Give exactly one of --spec (render at the target width) or --figure-dir (place an existing figure).")

    tools = require_tools()
    venue = fixtures.venue(venue_id)
    layout = fixtures.layout(venue_id, layout_id)
    width_factor = float(layout["target_width_factor"])

    checks: List[Dict[str, Any]] = [
        check_entry(
            "dependencies",
            PASS,
            "latexmk, pdflatex, bibtex and pdftoppm are all available.",
            resolved=tools,
        )
    ]

    build_dir = tempfile.mkdtemp(
        prefix="mpf-context-%s-%s-%s-" % (venue_id, layout["id"], case_id)
    )
    kept_build: Optional[str] = None
    try:
        return _evaluate_in(
            build_dir=build_dir,
            fixtures=fixtures,
            venue=venue,
            case_id=case_id,
            output_dir=output_dir,
            spec_path=spec_path,
            figure_dir=figure_dir,
            base_profile_path=base_profile_path,
            caption=caption,
            png_dpi=png_dpi,
            timeout=timeout,
            width_factor=width_factor,
            layout=layout,
            checks=checks,
            tools=tools,
        )
    except Exception:
        if diagnostics_dir:
            kept_build = os.path.join(
                os.path.abspath(diagnostics_dir), "%s-%s-%s" % (venue_id, layout["id"], case_id)
            )
            if os.path.isdir(kept_build):
                shutil.rmtree(kept_build)
            os.makedirs(os.path.dirname(kept_build), exist_ok=True)
            shutil.copytree(build_dir, kept_build)
            sys.stderr.write("build directory kept for diagnosis: %s\n" % kept_build)
        raise
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _evaluate_in(
    build_dir: str,
    fixtures: Fixtures,
    venue: Dict[str, Any],
    case_id: str,
    output_dir: str,
    spec_path: Optional[str],
    figure_dir: Optional[str],
    base_profile_path: Optional[str],
    caption: Optional[str],
    png_dpi: int,
    timeout: int,
    width_factor: float,
    layout: Dict[str, Any],
    checks: List[Dict[str, Any]],
    tools: Dict[str, str],
) -> Dict[str, Any]:
    import render as render_module

    # Reject a damaged figure before spending a probe compile on it.
    if figure_dir is not None:
        candidate = os.path.join(figure_dir, "figure.pdf")
        if not os.path.isfile(candidate):
            raise ContextError("No figure.pdf in %s." % figure_dir)
        read_pdf(candidate, "The figure in %s" % figure_dir)

    stage_build_dir(build_dir, fixtures, venue)

    # ---------------------------------------------------------------- probe
    probe_caption = escape_tex("Width probe. Replaced before the figure is placed.")
    float_environment = layout.get("float_environment", "figure")
    with open(os.path.join(build_dir, "context-figure.tex"), "w", encoding="utf-8") as handle:
        handle.write(figure_block(width_factor, probe_caption, True, float_environment))

    probe = compile_document(build_dir, timeout)
    probe_measures = read_measures(build_dir)
    if not probe.ok or "float_linewidth_tex_pt" not in probe_measures:
        raise ContextError(
            "The width probe compile of the %s wrapper failed%s. Without it there is "
            "no measured target width, so nothing downstream would be trustworthy.\n"
            "%s"
            % (
                venue["name"],
                " (timed out after %ds)" % timeout if probe.timed_out else "",
                "\n".join(log_diagnostics(probe.log)["errors"][:10]) or probe.stderr.strip(),
            )
        )

    float_linewidth_tex_pt = measured_tex_pt(probe_measures, "float_linewidth_tex_pt")
    target_width_tex_pt = float_linewidth_tex_pt * width_factor
    target_width_mm = tex_pt_to_mm(target_width_tex_pt)

    template = {
        "columns": int(measured_float(probe_measures, "columns") or venue["columns"]),
        "paperwidth_mm": round(tex_pt_to_mm(measured_tex_pt(probe_measures, "paperwidth_tex_pt") or 0.0), 3),
        "paperheight_mm": round(tex_pt_to_mm(measured_tex_pt(probe_measures, "paperheight_tex_pt") or 0.0), 3),
        "textwidth_tex_pt": measured_tex_pt(probe_measures, "textwidth_tex_pt"),
        "textwidth_mm": round(tex_pt_to_mm(measured_tex_pt(probe_measures, "textwidth_tex_pt") or 0.0), 3),
        "columnwidth_tex_pt": measured_tex_pt(probe_measures, "columnwidth_tex_pt"),
        "columnwidth_mm": round(tex_pt_to_mm(measured_tex_pt(probe_measures, "columnwidth_tex_pt") or 0.0), 3),
        "columnsep_tex_pt": measured_tex_pt(probe_measures, "columnsep_tex_pt"),
        "float_linewidth_tex_pt": float_linewidth_tex_pt,
        "float_linewidth_mm": round(tex_pt_to_mm(float_linewidth_tex_pt), 3),
        "body_font_size_pt": measured_float(probe_measures, "body_font_size_pt"),
        "body_baselineskip_tex_pt": measured_tex_pt(probe_measures, "body_baselineskip_tex_pt"),
        "caption_font_size_pt": measured_float(probe_measures, "caption_font_size_pt"),
        "measured_by": "TeX, inside the compiled document at the figure's insertion point",
        "units": "lengths named _tex_pt are TeX points (72.27/in); font sizes are the printed pt of the typeface",
    }

    # ------------------------------------------------------- render or reuse
    if spec_path:
        base_path = base_profile_path or figure_core.default_profile_path(SKILL_ROOT)
        base_profile = figure_core.load_profile(base_path)
        derived_profile = derive_profile(base_profile, target_width_mm)
        derived_profile_path = os.path.join(build_dir, "profile.derived.json")
        figure_core.write_json(derived_profile_path, derived_profile)

        render_out = os.path.join(build_dir, "render")
        figure_report = render_module.render(spec_path, render_out, derived_profile_path)
        figure_pdf = os.path.join(render_out, "figure.pdf")
        figure_source = {
            "mode": "rendered-to-template-width",
            "spec": os.path.abspath(spec_path),
            "spec_sha256": sha256_file(spec_path),
            "base_profile": os.path.abspath(base_path),
            "base_profile_name": base_profile.get("name"),
            "derived_profile": derived_profile,
            "figure_status": figure_report["status"],
            "figure_checks": [
                {"id": entry["id"], "status": entry["status"], "message": entry["message"]}
                for entry in figure_report["checks"]
                if entry["status"] in (WARN, FAIL)
            ],
        }
        figure_profile: Optional[Dict[str, Any]] = derived_profile
        reproduce_render = (
            "python %s --spec %s --profile <derived: canvas.width_mm=%.3f> --output-dir <dir>"
            % (
                os.path.join("skills", "scientific-figures", "scripts", "render.py"),
                spec_path,
                derived_profile["canvas"]["width_mm"],
            )
        )
    else:
        assert figure_dir is not None
        figure_pdf_source = os.path.join(figure_dir, "figure.pdf")
        render_out = os.path.join(build_dir, "render")
        os.makedirs(render_out, exist_ok=True)
        figure_pdf = os.path.join(render_out, "figure.pdf")
        shutil.copyfile(figure_pdf_source, figure_pdf)

        profile_json = os.path.join(figure_dir, "profile.resolved.json")
        figure_profile = None
        if os.path.isfile(profile_json):
            try:
                figure_profile = figure_core.load_profile(profile_json)
            except figure_core.ProfileError:
                figure_profile = None
        spec_json = os.path.join(figure_dir, "spec.json")
        figure_source = {
            "mode": "existing-figure-placed-as-is",
            "figure_dir": os.path.abspath(figure_dir),
            "figure_pdf_sha256": sha256_file(figure_pdf_source),
            "spec": os.path.abspath(spec_json) if os.path.isfile(spec_json) else None,
            "spec_sha256": sha256_file(spec_json) if os.path.isfile(spec_json) else None,
            "profile_found": figure_profile is not None,
            "derived_profile": None,
        }
        reproduce_render = "reused as-is from %s" % figure_dir

    source_reader = read_pdf(figure_pdf, "The figure to be placed")
    source_box = source_reader.pages[0].mediabox
    source_width_pdf_pt = float(source_box.width)
    source_height_pdf_pt = float(source_box.height)

    # ---------------------------------------------------------------- place
    caption_text = caption or default_caption(
        venue,
        case_id,
        os.path.basename(spec_path) if spec_path else os.path.basename(os.path.abspath(figure_dir or "")),
        layout,
    )
    with open(os.path.join(build_dir, "context-figure.tex"), "w", encoding="utf-8") as handle:
        handle.write(figure_block(width_factor, caption_text, False, float_environment))
    shutil.copyfile(figure_pdf, os.path.join(build_dir, "%s.pdf" % FIGURE_BASENAME))

    final = compile_document(build_dir, timeout)
    measures = read_measures(build_dir)
    diagnostics = log_diagnostics(final.log)
    compiled_pdf = os.path.join(build_dir, "%s.pdf" % JOBNAME)

    if final.timed_out:
        raise ContextError(
            "The %s wrapper did not finish compiling within %d s." % (venue["name"], timeout)
        )
    if not final.ok or not os.path.isfile(compiled_pdf):
        raise ContextError(
            "The %s wrapper failed to compile with the figure in place (latexmk exit %d).\n%s"
            % (venue["name"], final.returncode, "\n".join(diagnostics["errors"][:10]) or final.stderr.strip())
        )

    checks.append(
        check_entry(
            "compile",
            PASS,
            "latexmk built the %s wrapper to convergence." % venue["name"],
            venue=venue["id"],
            mode=venue["mode"],
        )
    )
    if diagnostics["undefined_citations_or_references"]:
        checks.append(
            check_entry(
                "latex_references_resolve",
                FAIL,
                "%d undefined citation/reference warning(s); the page shows '?' where a "
                "number should be." % len(diagnostics["undefined_citations_or_references"]),
                warnings=diagnostics["undefined_citations_or_references"],
            )
        )
    else:
        checks.append(
            check_entry(
                "latex_references_resolve",
                PASS,
                "Every citation and cross-reference resolved; bibtex ran and converged.",
            )
        )
    if diagnostics["bad_boxes"]:
        checks.append(
            check_entry(
                "latex_boxes",
                WARN,
                "%d overfull/underfull box warning(s). Normal in running prose; worth a "
                "look only if one names the figure." % len(diagnostics["bad_boxes"]),
                warnings=diagnostics["bad_boxes"][:10],
            )
        )
    else:
        checks.append(check_entry("latex_boxes", PASS, "No overfull or underfull boxes."))

    # ------------------------------------------------------------- locate it
    page_index, form, reader = locate_figure_page(
        compiled_pdf, source_width_pdf_pt, source_height_pdf_pt
    )
    total_pages = len(reader.pages)
    printed_page = measured_float(measures, "figure_printed_page")
    printed_page = int(printed_page) if printed_page is not None else None

    checks.append(
        check_entry(
            "figure_page_located",
            PASS,
            "The figure is drawn exactly once, on PDF page index %d of %d."
            % (page_index, total_pages),
            pdf_page_index_zero_based=page_index,
            total_pages=total_pages,
        )
    )

    if printed_page is None:
        checks.append(
            check_entry(
                "page_index_consistent",
                NOT_CHECKED,
                "TeX did not report the page the float landed on, so the printed folio "
                "could not be cross-checked against the PDF index.",
            )
        )
    elif printed_page - 1 == page_index:
        checks.append(
            check_entry(
                "page_index_consistent",
                PASS,
                "TeX shipped the float on printed page %d, which is PDF index %d — the "
                "two locators agree." % (printed_page, page_index),
                printed_page=printed_page,
                pdf_page_index_zero_based=page_index,
            )
        )
    else:
        checks.append(
            check_entry(
                "page_index_consistent",
                FAIL,
                "TeX says the float shipped on printed page %d but the figure is drawn on "
                "PDF index %d. The printed folio and the physical page have come apart; "
                "the extracted page may not be the one the report describes."
                % (printed_page, page_index),
                printed_page=printed_page,
                pdf_page_index_zero_based=page_index,
            )
        )

    text = page_text(reader, page_index)
    body_chars = len(re.sub(r"\s+", "", text))
    if page_index == 0:
        checks.append(
            check_entry(
                "page_is_body_page",
                FAIL,
                "The figure landed on the first page, which carries the title block. The "
                "whole point is to judge it in ordinary body text.",
                pdf_page_index_zero_based=page_index,
            )
        )
    elif body_chars < 800:
        checks.append(
            check_entry(
                "page_is_body_page",
                FAIL,
                "Only %d non-space characters of text on the page; that is not a page of "
                "running prose with a figure in it." % body_chars,
                text_characters=body_chars,
            )
        )
    else:
        checks.append(
            check_entry(
                "page_is_body_page",
                PASS,
                "Page index %d carries %d non-space characters of body text alongside the "
                "figure." % (page_index, body_chars),
                pdf_page_index_zero_based=page_index,
                text_characters=body_chars,
            )
        )

    if "Figure" in text:
        checks.append(
            check_entry(
                "caption_present",
                PASS,
                "The caption is on the extracted page, set in the venue's own caption style.",
            )
        )
    else:
        checks.append(
            check_entry(
                "caption_present",
                FAIL,
                "No caption text found on the page. The figure may have been placed "
                "without its caption, or the caption floated elsewhere.",
            )
        )

    # -------------------------------------------------------------- geometry
    placed_width_pdf_pt = form["placed_width_pdf_pt"]
    placed_width_mm = pdf_pt_to_mm(placed_width_pdf_pt)
    target_width_pdf_pt = target_width_tex_pt / TEX_PT_PER_INCH * PDF_PT_PER_INCH
    width_error = abs(placed_width_mm - tex_pt_to_mm(target_width_tex_pt))
    relative_error = width_error / max(tex_pt_to_mm(target_width_tex_pt), 1e-9)

    if relative_error <= 0.005:
        checks.append(
            check_entry(
                "placed_width_matches_target",
                PASS,
                "Drawn at %.2f mm against a %.2f mm target (%.3f%% off), measured from the "
                "page's own drawing transform."
                % (placed_width_mm, tex_pt_to_mm(target_width_tex_pt), relative_error * 100),
                placed_width_mm=round(placed_width_mm, 3),
                target_width_mm=round(tex_pt_to_mm(target_width_tex_pt), 3),
                relative_error=round(relative_error, 6),
            )
        )
    else:
        checks.append(
            check_entry(
                "placed_width_matches_target",
                FAIL,
                "Drawn at %.2f mm but the target is %.2f mm (%.2f%% off). The template is "
                "not placing the figure where the width rule says it should."
                % (placed_width_mm, tex_pt_to_mm(target_width_tex_pt), relative_error * 100),
                placed_width_mm=round(placed_width_mm, 3),
                target_width_mm=round(tex_pt_to_mm(target_width_tex_pt), 3),
                relative_error=round(relative_error, 6),
            )
        )

    # The ordinary render checks ran at the *derived* width, which is the width
    # that matters — a bar chart whose category labels fit at 85 mm can have them
    # collide at 69.85 mm. Burying that behind a one-word status would hide the
    # most useful thing this evaluation found.
    render_checks = figure_source.get("figure_checks")
    if render_checks is None:
        checks.append(
            check_entry(
                "figure_render_checks",
                NOT_CHECKED,
                "The figure was placed as it came, so render.py's own checks were not "
                "re-run at this width.",
            )
        )
    elif any(entry["status"] == FAIL for entry in render_checks):
        checks.append(
            check_entry(
                "figure_render_checks",
                FAIL,
                "render.py failed a check drawing the figure at %.2f mm: %s"
                % (target_width_mm, "; ".join(
                    "%s: %s" % (entry["id"], entry["message"])
                    for entry in render_checks if entry["status"] == FAIL)),
                checks=render_checks,
            )
        )
    elif render_checks:
        checks.append(
            check_entry(
                "figure_render_checks",
                WARN,
                "Drawn at the template's %.2f mm, the figure's own checks warn: %s"
                % (target_width_mm, "; ".join(
                    "%s: %s" % (entry["id"], entry["message"]) for entry in render_checks)),
                checks=render_checks,
            )
        )
    else:
        checks.append(
            check_entry(
                "figure_render_checks",
                PASS,
                "render.py's checks are clean at the template's %.2f mm." % target_width_mm,
            )
        )

    scale = placed_width_pdf_pt / source_width_pdf_pt
    sizes = source_type_sizes(figure_profile)
    if sizes is None:
        checks.append(
            check_entry(
                "effective_type_size",
                NOT_CHECKED,
                "The figure was placed at scale %.4f, but no profile came with it, so the "
                "type sizes it was drawn at are unknown and the effective sizes cannot be "
                "worked out. Not a pass." % scale,
                scale=round(scale, 6),
            )
        )
        effective = None
    else:
        effective = {key: round(value * scale, 3) for key, value in sizes.items()}
        if abs(scale - 1.0) <= 0.005:
            checks.append(
                check_entry(
                    "effective_type_size",
                    PASS,
                    "Placed at scale %.4f, so the figure's %.1f pt axis labels and %.1f pt "
                    "ticks are those sizes on the page."
                    % (scale, sizes["axis_label_pt"], sizes["tick_pt"]),
                    scale=round(scale, 6),
                    source=sizes,
                    effective=effective,
                )
            )
        else:
            checks.append(
                check_entry(
                    "effective_type_size",
                    WARN,
                    "Placed at scale %.4f: %.1f pt axis labels print at %.2f pt, %.1f pt "
                    "ticks at %.2f pt, %.2f pt data lines at %.3f pt. Whether that is "
                    "legible is a judgement, not a rule — this check reports the numbers "
                    "and does not set a threshold."
                    % (
                        scale,
                        sizes["axis_label_pt"],
                        effective["axis_label_pt"],
                        sizes["tick_pt"],
                        effective["tick_pt"],
                        sizes["data_linewidth_pt"],
                        effective["data_linewidth_pt"],
                    ),
                    scale=round(scale, 6),
                    source=sizes,
                    effective=effective,
                )
            )

    # ------------------------------------------------------------- deliver
    os.makedirs(output_dir, exist_ok=True)
    page_pdf = os.path.join(output_dir, "page.pdf")
    page_png = os.path.join(output_dir, "page.png")
    page_geometry = extract_single_page(reader, page_index, page_pdf)

    extracted = read_pdf(page_pdf, "The extracted page")
    if len(extracted.pages) == 1:
        checks.append(
            check_entry(
                "single_page_output",
                PASS,
                "page.pdf is exactly one page, %.1f x %.1f mm — the full body page, "
                "uncropped." % (page_geometry["width_mm"], page_geometry["height_mm"]),
                **page_geometry,
            )
        )
    else:
        checks.append(
            check_entry(
                "single_page_output",
                FAIL,
                "page.pdf came out with %d pages." % len(extracted.pages),
            )
        )

    extracted_box = extracted.pages[0].mediabox
    if (
        abs(float(extracted_box.width) - page_geometry["width_pdf_pt"]) < 0.01
        and abs(float(extracted_box.height) - page_geometry["height_pdf_pt"]) < 0.01
    ):
        checks.append(
            check_entry(
                "page_size_preserved",
                PASS,
                "The extracted page keeps the compiled document's media box exactly.",
            )
        )
    else:
        checks.append(
            check_entry("page_size_preserved", FAIL, "The extracted page was resized.")
        )

    rasterise(page_pdf, page_png, png_dpi, timeout)
    checks.append(
        check_entry(
            "preview_written",
            PASS,
            "page.png rasterised from page.pdf at %d DPI with pdftoppm." % png_dpi,
            dpi=png_dpi,
        )
    )

    checks.append(
        check_entry(
            "visual_review",
            NOT_CHECKED,
            "Open page.png and read the figure against the prose beside it: labels, "
            "legend, line weights, white space. No script closes this one, and a clean "
            "compile is not a visual pass.",
        )
    )

    counts = {status: 0 for status in (PASS, WARN, FAIL, NOT_CHECKED)}
    for entry in checks:
        counts[entry["status"]] += 1
    status = FAIL if counts[FAIL] else (WARN if counts[WARN] else PASS)

    report = {
        "report_version": "1",
        "kind": "conference-context",
        "status": status,
        "counts": counts,
        "case": case_id,
        "venue": {
            "id": venue["id"],
            "name": venue["name"],
            "year": venue["year"],
            "mode": venue["mode"],
            "mode_syntax": venue["mode_syntax"],
            "columns": venue["columns"],
            "target_width_rule": layout["target_width_rule"],
            "target_width_factor": layout["target_width_factor"],
            "bibliography_style": venue.get("bibliography_style"),
        },
        "layout": {
            **layout,
            "measured_float_environment": float_environment,
            "note": "The width mode this page was produced in. The factor is applied to "
                    "the \\linewidth measured inside this float, so a figure* getting "
                    "\\textwidth and an ordinary figure getting \\columnwidth is the "
                    "template's arithmetic, not a constant written here.",
        },
        "fixtures": {
            "manifest": os.path.abspath(fixtures.manifest_path),
            "manifest_sha256": sha256_file(fixtures.manifest_path),
            "wrapper": os.path.abspath(fixtures.wrapper_path(venue["id"])),
            "wrapper_sha256": sha256_file(fixtures.wrapper_path(venue["id"])),
            "measure": os.path.abspath(fixtures.measure_path),
            "measure_sha256": sha256_file(fixtures.measure_path),
            "body": os.path.abspath(fixtures.body_path),
            "body_sha256": sha256_file(fixtures.body_path),
            "references": os.path.abspath(fixtures.bib_path),
            "references_sha256": sha256_file(fixtures.bib_path),
            "venue_files": [
                {
                    "path": entry["path"],
                    "sha256": sha256_file(os.path.join(fixtures.venue_dir(venue["id"]), entry["path"])),
                }
                for entry in venue["files"]
            ],
        },
        "template": template,
        "figure_source": figure_source,
        "geometry": {
            "units": "PDF points are 72/in; TeX points are 72.27/in; mm is the physical size",
            "target_width_tex_pt": round(target_width_tex_pt, 4),
            "target_width_pdf_pt": round(target_width_pdf_pt, 4),
            "target_width_mm": round(tex_pt_to_mm(target_width_tex_pt), 3),
            "source_pdf_width_pdf_pt": round(source_width_pdf_pt, 4),
            "source_pdf_width_mm": round(pdf_pt_to_mm(source_width_pdf_pt), 3),
            "source_pdf_height_mm": round(pdf_pt_to_mm(source_height_pdf_pt), 3),
            "placed_width_pdf_pt": round(placed_width_pdf_pt, 4),
            "placed_width_mm": round(placed_width_mm, 3),
            "placed_height_mm": round(pdf_pt_to_mm(form["placed_height_pdf_pt"]), 3),
            "placed_origin_pdf_pt": [round(value, 4) for value in form["placed_origin_pdf_pt"]],
            "drawing_matrix": [round(value, 6) for value in form["ctm"]],
            "scale": round(scale, 6),
            "scale_definition": "placed_width / source_pdf_width, both in PDF points, read from the page's drawing transform",
            "measured_from": "the compiled page's content stream, not the \\includegraphics argument",
        },
        "type_sizes": {
            "body_font_size_pt": template["body_font_size_pt"],
            "caption_font_size_pt": template["caption_font_size_pt"],
            "figure_source_pt": sizes,
            "figure_effective_pt": effective,
            "effective_definition": "source size x scale; None when the figure arrived without a profile",
            "note": "Reported, not adjudicated. There is no rule here that figure text must match body text.",
        },
        "page": {
            "pdf_page_index_zero_based": page_index,
            "printed_page_number": printed_page,
            "total_pages_in_full_document": total_pages,
            "pages_in_output": len(extracted.pages),
            **page_geometry,
        },
        "outputs": {
            "page_pdf": os.path.abspath(page_pdf),
            "page_png": os.path.abspath(page_png),
            "png_dpi": png_dpi,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "tools": tool_versions(tools),
        },
        "reproduce": {
            "render": reproduce_render,
            "context": "python tests/render_conference_context.py --venue %s --case %s"
            % (venue["id"], case_id),
            "context_layout": "python skills/scientific-figures/scripts/evaluate_context.py "
                              "--venue %s --layout %s --case %s ..." % (venue["id"], layout["id"], case_id),
        },
        "checks": checks,
        "build_artifacts": "The full multi-page PDF, .aux, .log, .bbl and the derived "
                           "profile live only in a temporary build directory, which is "
                           "removed on success. Nothing but page.pdf, page.png and this "
                           "report reaches the output directory.",
        "preview_caveat": "page.png is a %d DPI raster and a browser will scale it to fit. "
                          "That is not the printed size. The physical size is the one in "
                          "geometry/, measured from the PDF." % png_dpi,
    }

    figure_core.write_json(os.path.join(output_dir, "context-report.json"), report)
    return report


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Place a rendered figure in a conference body page and measure the result.",
    )
    # Not marked required, so --check-dependencies can stand alone; main() enforces
    # them for a real run.
    parser.add_argument("--venue", help="Venue id from the fixtures' manifest.json.")
    parser.add_argument("--case", help="Identifier for this case; names the output and appears in the caption.")
    parser.add_argument("--layout", help="Width mode from the venue's layouts (default: the venue's own default).")
    parser.add_argument("--output-dir", help="Directory for page.pdf, page.png and context-report.json.")

    source = parser.add_argument_group("figure source (exactly one)")
    source.add_argument("--spec", help="Render this spec at the template's target width (the default path).")
    source.add_argument("--figure-dir", help="Place the figure.pdf already in this directory, at whatever size it is.")

    fixtures = parser.add_argument_group("fixtures")
    fixtures.add_argument("--fixtures-root", help="Directory holding conferences/, article-context/ and wrappers/.")
    fixtures.add_argument("--conferences-dir", help="Override: directory with manifest.json and the venue style files.")
    fixtures.add_argument("--article-dir", help="Override: directory with body.tex and references.bib.")
    fixtures.add_argument("--wrappers-dir", help="Override: directory with measure.tex and <venue>.tex.")

    parser.add_argument("--base-profile", help="Profile to derive the target width from. Defaults to the skill's own.")
    parser.add_argument("--caption", help="Replace the generated caption. Escaped before it reaches TeX.")
    parser.add_argument("--png-dpi", type=int, default=200, help="Rasterisation DPI for page.png (default 200).")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds allowed per LaTeX run (default 300).")
    parser.add_argument("--diagnostics-dir", help="On failure, keep the build directory here.")
    parser.add_argument("--json", action="store_true", help="Print the whole report instead of a summary.")
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Report whether the external toolchain is present and exit; 0 if it is, 3 if not.",
    )
    return parser


def print_summary(report: Dict[str, Any]) -> None:
    geometry = report["geometry"]
    print(
        "%s [%s] / %s: %s  (pass %d, warn %d, fail %d, not_checked %d)"
        % (
            report["venue"]["id"],
            report.get("layout", {}).get("id", "narrow"),
            report["case"],
            report["status"],
            report["counts"][PASS],
            report["counts"][WARN],
            report["counts"][FAIL],
            report["counts"][NOT_CHECKED],
        )
    )
    print(
        "  line width %.2f mm -> target %.2f mm; drawn %.2f mm; scale %.4f"
        % (
            report["template"]["float_linewidth_mm"],
            geometry["target_width_mm"],
            geometry["placed_width_mm"],
            geometry["scale"],
        )
    )
    print(
        "  page: PDF index %s (printed %s) of %s; body %s pt, caption %s pt"
        % (
            report["page"]["pdf_page_index_zero_based"],
            report["page"]["printed_page_number"],
            report["page"]["total_pages_in_full_document"],
            report["type_sizes"]["body_font_size_pt"],
            report["type_sizes"]["caption_font_size_pt"],
        )
    )
    for entry in report["checks"]:
        if entry["status"] in (WARN, FAIL, NOT_CHECKED):
            print("  [%s] %s: %s" % (entry["status"], entry["id"], entry["message"]))
    print("  preview: %s" % report["outputs"]["page_png"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.check_dependencies:
        absent = missing_tools()
        if absent:
            print("missing: %s" % ", ".join(sorted(absent)), file=sys.stderr)
            print(INSTALL_HINT, file=sys.stderr)
            return 3
        print("toolchain present: %s" % ", ".join(sorted(REQUIRED_TOOLS)))
        return 0

    missing_args = [
        name for name, value in (("--venue", args.venue), ("--case", args.case),
                                 ("--output-dir", args.output_dir))
        if not value
    ]
    if missing_args:
        print("error: %s required for an evaluation run." % ", ".join(missing_args), file=sys.stderr)
        return 2

    try:
        fixtures = Fixtures.from_args(args)
        report = evaluate(
            fixtures=fixtures,
            venue_id=args.venue,
            case_id=args.case,
            output_dir=args.output_dir,
            spec_path=args.spec,
            figure_dir=args.figure_dir,
            base_profile_path=args.base_profile,
            caption=args.caption,
            png_dpi=args.png_dpi,
            timeout=args.timeout,
            diagnostics_dir=args.diagnostics_dir,
            layout_id=args.layout,
        )
    except MissingToolError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 3
    except (ContextError, figure_core.SpecError, figure_core.ProfileError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)
    return 1 if report["status"] == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
