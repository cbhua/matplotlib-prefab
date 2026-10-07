// Shared figure-slot and packaged-font helpers. No paper layout dependencies.
/** Put a rendered figure into the slot, at the slot's exact size. */
export function setFigure(slot, svgMarkup) {
  slot.classList.remove('mpf-slot-empty');
  slot.innerHTML = svgMarkup;
  const figure = slot.firstElementChild;
  if (figure && figure.tagName.toLowerCase() === 'svg') {
    // matplotlib writes a physical size in CSS points and a matching viewBox.
    // Letting it fill the slot keeps the drawing at the size the slot measures
    // rather than at whatever the browser's default sizing would make of it —
    // and if the two ever disagree, the geometry check says so.
    figure.setAttribute('width', '100%');
    figure.setAttribute('height', '100%');
    figure.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  }
  return figure;
}

export function clearFigure(slot) {
  slot.innerHTML = '';
  slot.classList.add('mpf-slot-empty');
}

/** The @font-face rules for the packaged faces, built from the font manifest. */
export function fontFaceCss(fonts, base) {
  const seen = new Set();
  const rules = [];
  for (const face of Object.values(fonts.faces)) {
    const key = `${face.css_family}|${face.weight}|${face.style}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rules.push(
      `@font-face{font-family:"${face.css_family}";`
      + `src:url("${base}${face.asset}") format("woff2");`
      + `font-weight:${face.weight};font-style:${face.style};font-display:block;}`,
    );
  }
  return rules.join('\n');
}

