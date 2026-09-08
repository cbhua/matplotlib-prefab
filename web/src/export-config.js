/**
 * The hand-off: everything another agent needs to redraw this figure, and
 * nothing that would make the claim bigger than the evidence.
 *
 * Two shapes come out of here.
 *
 * `handoffText` is prose for a coding agent: the resolved profile, the spec, the
 * physical size, the versions, and the exact command. It says what is
 * reproducible and what is not — the same style over *different data* gives a
 * different legend position, different ticks and a different layout, and an
 * export that implied otherwise would be lying about the one thing people will
 * assume.
 *
 * `bundle` is the machine-readable form. The profile inside it is a profile the
 * repository's validator accepts, unchanged: the metadata that would make it
 * fail — venue, mode, versions, digests — lives in an envelope *around* it, not
 * in extra keys inside it.
 */

const SCHEMA_VERSION = '1';

function stableStringify(value) {
  return JSON.stringify(value, null, 2);
}

/** The envelope. `profile` stays exactly what the renderer validated. */
export function buildBundle(state) {
  const { page, spec, profile, resolvedType, environment, assets, render } = state;
  return {
    schema_version: SCHEMA_VERSION,
    kind: 'matplotlib-prefab-figure-handoff',
    note: 'Written by the browser style lab. `profile` is a complete style profile the '
        + "repository's validator accepts as-is; everything else is envelope. Do not "
        + 'merge the envelope into the profile — the validator rejects unknown fields on '
        + 'purpose, so a typo cannot be silently ignored.',
    generated_at_utc: new Date().toISOString(),
    target: {
      venue_id: page.venue.id,
      venue: page.venue.name,
      year: page.venue.year,
      venue_mode: page.venue.mode,
      layout: page.layout.id,
      layout_label: page.layout.label,
      float_environment: page.layout.float_environment,
      width_rule: page.layout.target_width_rule,
      figure_width_mm: profile.canvas.width_mm,
      figure_height_mm: profile.canvas.width_mm * profile.canvas.aspect_ratio,
      insert_at: `\\includegraphics[width=\\linewidth] inside a ${page.layout.float_environment}`,
      keep_size: 'Insert at its own size. Do not scale it: the figure was drawn at the '
               + 'width the template gives it, so any scale factor also shrinks the type.',
    },
    profile,
    resolved_type: resolvedType,
    spec,
    spec_included: true,
    render: render || null,
    environment,
    assets,
    reproduce: {
      command: 'python skills/scientific-figures/scripts/render.py'
             + ' --spec spec.json --profile profile.json --output-dir out/',
      writes: ['figure.pdf', 'figure.png', 'spec.json', 'profile.resolved.json', 'report.json'],
      verify: 'The report.json it writes carries the same checks the preview ran. '
            + 'A clean report is not a visual review.',
    },
    limits: {
      same_data_only: 'These settings reproduce *this* figure. Applied to different data, '
                    + 'the automatic legend placement, the tick values and the constrained '
                    + 'layout all move, so the result will not be identical — only the style '
                    + 'will be.',
      environment_bound: 'Byte-identical output needs the matplotlib version named under '
                       + '`environment`. A different matplotlib draws the same figure slightly '
                       + 'differently.',
      not_a_compile: 'The preview shows this figure on a calibrated fixture page. It is not '
                   + 'evidence that your own paper compiles, that the float lands where you '
                   + 'want it, or that your macros are compatible.',
    },
  };
}

/**
 * What the checks said about this exact figure, so the receiving agent is not
 * told about a problem it could have been warned of, and does not "fix" a
 * warning the person exporting had already seen and accepted.
 */
function checkLines(report) {
  const problems = report.checks.filter((c) => c.status === 'warn' || c.status === 'fail');
  const lines = [`Checks at this size: ${report.counts.pass} pass, ${report.counts.warn} warn, `
                 + `${report.counts.fail} fail, ${report.counts.not_checked} not checked.`];
  for (const check of problems) lines.push(`  - ${check.status} ${check.id}: ${check.message}`);
  lines.push('  - visual_review is open. Rendering successfully is not looking at it.');
  lines.push('These were already visible to the person who chose these settings. Report them; '
             + 'do not silently change values to make them go away.');
  lines.push('');
  return lines;
}

/** The prose an agent is meant to be handed. */
export function handoffText(state) {
  const bundle = buildBundle(state);
  const { target, profile, resolved_type: resolvedType, environment, assets, spec } = bundle;
  const lines = [
    'Reproduce this figure with matplotlib-prefab.',
    '',
    `Target: ${target.venue} (${target.venue_mode} layout), ${target.layout_label}.`,
    `Draw it ${target.figure_width_mm.toFixed(3)} mm wide by `
      + `${target.figure_height_mm.toFixed(3)} mm high and insert it at that size, with `
      + `${target.insert_at}.`,
    target.keep_size,
    '',
    'Resolved type (size in points, at the printed size):',
    ...Object.entries(resolvedType).map(([role, entry]) =>
      `  ${role.padEnd(8)} ${String(entry.size_pt).padStart(6)} pt  ${entry.weight}`),
    '',
    'Full style profile — save as profile.json:',
    '```json',
    stableStringify(profile),
    '```',
    '',
    'Figure spec — save as spec.json:',
    '```json',
    stableStringify(spec),
    '```',
    '',
    'Then run:',
    '```',
    bundle.reproduce.command,
    '```',
    '',
    `Rendered in the browser by ${environment.renderer} on matplotlib `
      + `${environment.matplotlib}, numpy ${environment.numpy}, Python ${environment.python} `
      + `(Pyodide ${assets.pyodide_version}).`,
    `Shared rendering code: figure_core.py sha256 ${assets.figure_core_sha256}.`,
    '',
    ...(bundle.render && bundle.render.checks
      ? checkLines(bundle.render.checks)
      : []),
    'What this does and does not promise:',
    `  - ${bundle.limits.same_data_only}`,
    `  - ${bundle.limits.environment_bound}`,
    `  - ${bundle.limits.not_a_compile}`,
    '',
    'Do not "improve" these values. They are the ones that were chosen and looked at. '
      + 'If something here does not work, say so and report what you actually used.',
  ];
  return lines.join('\n');
}

/**
 * Copy to the clipboard, and say honestly whether it worked.
 * A page served over plain HTTP, or one the user has not interacted with, may
 * not have clipboard permission at all; the caller shows the text instead.
 */
export async function copyToClipboard(text) {
  try {
    if (!navigator.clipboard) throw new Error('no clipboard API in this context');
    await navigator.clipboard.writeText(text);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

export function downloadJson(name, payload) {
  const blob = new Blob([stableStringify(payload) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke on the next turn: revoking synchronously can cancel the download in
  // some browsers before it has read the blob.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export { stableStringify };
