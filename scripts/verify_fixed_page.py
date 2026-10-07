#!/usr/bin/env python3
"""Re-run the one-page HTML experiment against the frozen LaTeX PDF/raster.

No LaTeX or Pyodide needed. The committed 150 DPI PDF raster is the immutable
visual oracle; geometry and text are freshly extracted from the original PDF.
Run: .venv/bin/python scripts/verify_fixed_page.py
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/web'))
from pdf_layout import describe_page
from PIL import Image, ImageChops, ImageFilter, ImageOps
import numpy as np

BASE = ROOT / 'tests/web/calibration/baselines/icml2026/narrow'
DPI = 150
THRESHOLDS = {'position_mm': .03, 'width_mm': .05,
              'unmatched_ink_fraction': .05, 'ink_ratio_min': .85, 'ink_ratio_max': 1.15}
# Coordinates in PDF points, y down. Every substantive area gets its own gate:
# whitespace cannot dilute a missing heading or folio into a passing page score.
REGIONS = {
    'whole_page': (0, 0, 612, 792), 'header': (50, 40, 550, 62),
    'caption': (54, 215, 292, 273), 'body': (54, 290, 292, 719),
    'formula': (307, 65, 543, 120), 'references': (307, 128, 543, 719),
    'folio': (280, 729, 318, 745),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_ink(reference, candidate):
    """Bidirectional ink mismatch within 1 pixel (0.169 mm), no image alignment."""
    if reference.size != candidate.size:
        return {'pass': False, 'size_mismatch': [reference.size, candidate.size]}
    regions = {}
    for name, box in REGIONS.items():
        box = tuple(round(v * DPI / 72) for v in box)
        a, b = reference.crop(box).convert('L'), candidate.crop(box).convert('L')
        a_mask, b_mask = np.asarray(a) < 200, np.asarray(b) < 200
        a_near = np.asarray(a.filter(ImageFilter.MinFilter(3))) < 200
        b_near = np.asarray(b.filter(ImageFilter.MinFilter(3))) < 200
        missing = float((a_mask & ~b_near).sum() / max(1, a_mask.sum()))
        extra = float((b_mask & ~a_near).sum() / max(1, b_mask.sum()))
        a_ink = (255 - np.asarray(a, dtype=float)).sum()
        b_ink = (255 - np.asarray(b, dtype=float)).sum()
        ratio = float(b_ink / max(1, a_ink))
        regions[name] = {'missing_ink': missing, 'extra_ink': extra, 'ink_ratio': ratio,
            'pass': max(missing, extra) <= THRESHOLDS['unmatched_ink_fraction']
                and THRESHOLDS['ink_ratio_min'] <= ratio <= THRESHOLDS['ink_ratio_max']}
    return {'pass': all(v['pass'] for v in regions.values()), 'regions': regions}


def compare_geometry(measured):
    pdf = describe_page(str(BASE / 'page.pdf'))
    runs = pdf['runs']
    failures, errors = [], {'baseline_mm': [], 'left_mm': [], 'width_mm': [], 'size_pt': []}
    actual = {r['index']: r for r in measured['runs']}
    expected_text = {i for i, r in enumerate(runs) if not r['maths']}
    expected_math = {i for i, r in enumerate(runs) if r['maths']}
    if set(actual) != expected_text or set(measured['math']) != expected_math:
        failures.append('missing/extra text or mathematical runs')
    for i, got in actual.items():
        want = runs[i]
        if got['text'] != want['text']: failures.append(f'text changed at run {i}')
        errors['baseline_mm'].append(abs(got['baseline_pt'] - want['y_pt']) * 25.4 / 72)
        errors['left_mm'].append(abs(got['x_pt'] - want['x_pt']) * 25.4 / 72)
        errors['width_mm'].append(abs(got['width_pt'] - want['width_pt']) * 25.4 / 72)
        errors['size_pt'].append(abs(got['size_pt'] - want['size_pt']))
    maxima = {key: max(values, default=999) for key, values in errors.items()}
    for key, limit in [('baseline_mm', THRESHOLDS['position_mm']), ('left_mm', THRESHOLDS['position_mm']),
                       ('width_mm', THRESHOLDS['width_mm']), ('size_pt', .01)]:
        if maxima[key] > limit: failures.append(key)
    if abs(measured['paper']['width_pt'] - pdf['width_pt']) > .01 or abs(measured['paper']['height_pt'] - pdf['height_pt']) > .01:
        failures.append('paper size')
    form = pdf['forms'][0]
    # Slot dimensions are independently checked from the PDF form placement.
    expected_slot = {'x_pt': form['x_pt'], 'top_pt': pdf['height_pt'] - form['y_pt'] - form['height_pt'],
                     'width_pt': form['width_pt'], 'height_pt': form['height_pt']}
    slot_errors = {key: abs(measured['slot'][key] - value) * 25.4 / 72 for key, value in expected_slot.items()}
    if max(slot_errors.values()) > THRESHOLDS['position_mm']: failures.append('slot')
    return {'pass': not failures, 'failures': failures, 'text_runs': len(actual),
            'math_runs': len(measured['math']), 'max_errors': maxima, 'slot_error_mm': slot_errors}


def verify(page, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    page.wait_for_function('window.__ready || window.__referenceError')
    assert page.evaluate('window.__referenceError || null') is None
    measured = page.evaluate('window.__fixedPage.measure()')
    page.locator('.fixed-paper').screenshot(path=str(out / 'browser.png'))
    reference = Image.open(BASE / 'page.png').convert('L')
    candidate = Image.open(out / 'browser.png').convert('L')
    geometry = compare_geometry(measured)
    pixels = compare_ink(reference, candidate)
    if reference.size == candidate.size:
        Image.merge('RGB', (ImageOps.invert(reference), Image.new('L', reference.size),
                           ImageOps.invert(candidate))).save(out / 'overlay.png')
        ImageOps.invert(ImageChops.difference(reference, candidate)).save(out / 'difference.png')
    sources = [BASE / 'page.pdf', BASE / 'page.png', ROOT / 'web/public/generated/conferences/icml2026/narrow/page.json',
               *(ROOT / 'web/src' / name for name in ('fixed-paper.js', 'fixed-paper.css', 'reference.js', 'figure-view.js')),
               ROOT / 'web/reference.html', ROOT / 'web/reference/icml2026-narrow.json',
               ROOT / 'web/public/generated/fonts/fonts.json', Path(__file__),
               *sorted((ROOT / 'web/public/generated/fonts').glob('*.woff2'))]
    report = {'status': 'pass' if geometry['pass'] and pixels['pass'] else 'fail',
              'browser': page.context.browser.version, 'dpi': DPI, 'thresholds': THRESHOLDS,
              'geometry': geometry, 'pixels': pixels,
              'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
              'note': 'Frozen line breaks and measured positions; HTML text and local fonts, SVG only for maths. '
                      'Compared to the committed LaTeX PDF and its 150 DPI raster; neither is regenerated. '
                      'No registration, rescaling, whitespace-normalized score, or figure mask.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / '.tmp/fixed-page-regression'))
    args = parser.parse_args()
    from lab import browser_runtime
    from server import static_server
    with static_server(str(ROOT / 'web')) as origin, browser_runtime() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={'width': 1800, 'height': 1300}, device_scale_factor=DPI / 96)
        page.goto(origin + '/reference.html?capture=1')
        report = verify(page, args.output)
        browser.close()
    print(json.dumps({'status': report['status'], 'geometry': report['geometry'], 'pixels': report['pixels'], 'output': args.output}, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
