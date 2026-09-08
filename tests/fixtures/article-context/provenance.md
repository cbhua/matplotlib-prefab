# Where the body text in this fixture comes from

`body.tex` exists for one reason: the conference context evaluation needs a page
of *real* running prose — normal paragraph density, real citations, real inline
maths, a real cross-reference — so that a figure dropped into it can be judged at
the size a reader would actually meet it. Lorem ipsum or blank vertical space
would not show whether the figure's labels hold up next to body text.

## Source

Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones,
Aidan N. Gomez, Łukasz Kaiser and Illia Polosukhin, *Attention Is All You Need*,
arXiv:1706.03762 (2017).

Supplied by the repository owner as `.tmp/conference_template/attn_is_all_u_need.tar.gz`
(SHA256 `2e7a7d9ee2520d22eb23dae0cb148e167be02a30d6cb3f11b1c67723194339c6`). That
archive is kept out of the repository; only the excerpt below was copied in.

## What was taken

| Fixture section | Source file in the archive | Extent |
| --- | --- | --- |
| `\section{Introduction}` | `introduction.tex` | the four active prose paragraphs, in order, complete |
| `\section{Background}` first paragraph | `background.tex` | paragraph 1, complete |
| the two paragraphs before the figure | `background.tex` | paragraphs 2 and 3, complete |
| the paragraph after the figure | `background.tex` | paragraph 4, complete |
| `\section{Attention}` | `model_architecture.tex` | the `\subsection{Attention}` lead paragraph, plus two sentences of `\subsubsection{Scaled Dot-Product Attention}` |

Roughly one and a half pages of prose in a single-column venue — enough for a
title page plus one full body page, which is all the evaluation needs. The rest
of the article (`results.tex`, `training.tex`, `visualizations.tex`, the model
figures under `Figures/` and `vis/`, `nips_2017.sty`) was **not** copied.

## Every edit made to the excerpt

1. **Drafting comments removed.** The sources carry commented-out `\marginpar`
   notes to co-authors and long commented-out alternative drafts. All of those
   `%`-prefixed lines were dropped. No uncommented prose was altered.
2. **One paragraph break closed up.** In `introduction.tex` a `\marginpar`
   comment sat between two halves of what is one paragraph ("This inherently
   sequential nature…" / "Recent work has achieved…"). With the comment gone the
   two halves are joined into the single paragraph they were written as.
3. **`\clearpage` inserted** in the middle of Background, with a comment marking
   it as a fixture edit. It guarantees the target figure lands on an ordinary
   body page instead of competing with the title block for the first page. It
   changes nothing about that body page — margins, running head, folio, leading
   and caption style are the venue's own.
4. **`\input{context-figure}` inserted** between Background paragraphs 3 and 4.
   That is the insertion point for the figure under test.
5. **Section levels flattened.** `\subsection{Attention}` and its subsubsection
   became one `\section{Attention}`, because the excerpt has no enclosing
   `\section{Model Architecture}` to hang them under. The `\label{sec:attention}`
   moved with it, so the forward `\ref{sec:attention}` in Background still
   resolves to a real, numbered section on the page.
6. **Two sentences reordered** in the final paragraph, so the excerpt reads
   coherently without the equations, the Figure~\ref and the
   `\subsubsection` heading that separated them in the original.
7. **`Figure~\ref{fig:multi-head-att}` dropped** from that paragraph, along with
   the sentence naming it. The figure it points at is not part of this excerpt,
   and a dangling reference would defeat the point of the compile check.

Nothing was added to the prose. No citation key was invented, stubbed out or
silently defined away.

## Citations

Every `\citep` key that survives in `body.tex` has a real entry in
`references.bib` — 21 works, plus the source article itself. Titles and full
author lists were checked against the arXiv API on 2026-09-08; the one
non-arXiv entry, `hochreiter2001gradient`, is the 2001 book chapter in *A Field
Guide to Dynamical Recurrent Neural Networks* (Kremer & Kolen eds., IEEE Press).

The original `Figures/` and `vis/` graphics, and the `nips_2017.sty` the article
was typeset with, are deliberately absent: this excerpt is set in the 2026
conference styles under `tests/fixtures/conferences/`, not in the article's own.

## What the page is not

The figure that lands in this text is rendered by this repository from a spec in
`tests/data/`. It is synthetic evaluation data. It is not a result from
*Attention Is All You Need*, and its caption says as much on the page. The
compiled page is a typesetting fixture; it is not a submission, a preprint, or a
claim that anything here was accepted anywhere.
