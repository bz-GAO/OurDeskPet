# Chat attachments

Chat treats images, text, code, CSV/TSV, DOCX and XLSX as one attachment group. A turn accepts at
most eight items in total. The composer shows them in one horizontal rail; the rail scrolls
only when its contents overflow. Image cards open the existing image preview. Other file
cards deliberately have no click action until a useful native preview exists.

Files enter the rail immediately with a parsing indicator. Each item is parsed independently,
so one invalid file does not discard the successful items. A ready card shows its filename and
extension, not its byte size. Removing a parsing item makes its eventual result unusable;
removing a ready item clears its pending selection while the library retains its snapshot.
Deleting the library entry releases image resources when no historical message still uses them.
Parsers do not create per-file child
processes or a persistent upload cache.

The current send path still places the parsed contents of ready files into that user turn.
Conversation and Project assistant keep separate in-memory file libraries, while the sidebar's
**Library** tab presents their deduplicated union for reuse. Every explicit upload is read again,
even when its path matches an earlier file, because local contents may have changed. Exact parsed
content metadata prevents duplicate library entries afterwards; the sidebar's **Reference** action
reuses that parsed snapshot. Source paths stay in memory and are not written into exported JSON. New conversation
always clears messages, draft and pending selections; its **Clear uploaded files** checkbox decides
whether the current page's library is also discarded. Exiting RinaDesk always clears both libraries
and releases image resources. The library is local and can be managed from the left sidebar;
referenced contents are sent to the configured model when the user sends a message.

The former 512 KiB text/code cap is removed. Every supported source file now shares the 8 MiB raw
file safety ceiling, and one turn may hold up to 16 MiB of parsed file data. The configured model
context remains the send-time limit until bounded retrieval is implemented.

Structured table/Office extraction has an additional 512 KiB output ceiling and reads at most 50 XLSX sheets.
Office output is bounded while traversing cells/paragraphs, including repeated shared strings;
XML reads are capped at 16 MiB per entry and 64 MiB cumulatively per attachment. CSV/TSV checks
the raw-file size before loading its bytes. Excel dates outside the supported calendar range
(including its fictitious 1900 leap day) retain their original numeric value.
It currently signals truncation inside the extracted text. These are parser limits, distinct
from the raw-file and per-turn limits; structured coverage warnings are planned below.

## Format roadmap (reviewed 2026-10-03)

The current-behavior column describes implemented support; the last column is planned work.

| Format | Current behavior | Next bounded increment |
| --- | --- | --- |
| Text/code | UTF-8, BOM UTF-16, restricted GB18030 fallback; code AST/outline | Preserve line ranges; bounded blocks; avoid full-content repetition |
| PDF | Rejected | Local text-layer extraction by page; page numbers and empty/scanned-page warnings |
| DOCX | Body order, heading levels, table rows/cells and horizontal spans | Coverage for omitted headers, footers, notes and images; richer merged-cell semantics |
| XLSX | Sheet/row/cell addresses, shared/inline strings, booleans/errors, date/time styles, merged ranges, formulas and cached values | Bounded row selection and more number/style semantics; never execute formulas |
| CSV/TSV | Quoted fields, escaped quotes, multiline cells, first-row headers and numbered records | User-selectable header behavior and bounded row selection |
| PPTX | Rejected | Slide order, text boxes and speaker notes; no claim of chart/image understanding |
| SRT/VTT | Raw text | Cue IDs and timestamps, useful for Yaki exports |
| HTML | Raw source text | Optional local readable-text extraction, with no scripts or remote resources |
| Scans, EPUB, ODF, legacy Office, audio/video | No dedicated parser | Later opt-in work after usage and packaging review |

### PDF first milestone

Evaluate PDF.js in a dedicated Web Worker: it fits the existing TypeScript/WebView stack
and provides page access and text extraction. This is a candidate, not a selected dependency.
Verify worker packaging, CSP, offline fonts/CMaps and cancellation on the installed Windows
build before committing to it. Read only the explicitly attached bytes; do not fetch URLs
embedded in a document or run document actions.

Extract page-local text with source page numbers. Empty or image-only pages must produce
a concise warning, not a successful blank attachment. Text extraction alone does not promise
correct multi-column reading order, tables or mathematical structure. Mixed PDFs must report
which pages were read and which need OCR. Password-protected files get an explicit unsupported
state until a password interaction exists; no silent password attempts.

Acceptance samples: Chinese/Japanese/English, rotated and multi-column pages, mixed scan/text,
empty, encrypted, damaged and oversized files. Check coverage, elapsed time, peak memory,
cancellation, repeated attach/remove, and app exit. Start with existing upload limits; determine
page/output/time ceilings from these fixtures, rather than increasing limits blindly.

OCR is a separate later capability: cache per-page results for the current process only,
expose partial coverage, and require explicit permission for any cloud vision call. A richer
engine such as Docling can be evaluated if layout quality justifies its runtime/model footprint.
Do not install a Python/model runtime solely to claim support for more extensions.

### Shared parsing and retrieval contract

1. Keep text, code and work-file modules; add PDF through `fileParser.ts` as another adapter.
   Return optional source blocks (page, paragraph, sheet/cell, slide, cue), coverage and warnings
   alongside existing `ParsedFilePayload` fields. Old exported JSON remains loadable.
2. Introduce parse-task IDs, bounded concurrency and cancellation. Removing a card currently
   invalidates its result; native `spawn_blocking` work may continue. Do not present logical
   removal as physical cancellation. Heavy workers need an actual stop path.
3. Deduplicate by content hash and parser version. Explicit uploads re-read source bytes;
   references reuse the parsed snapshot. Missing originals must not make imported paths readable.
4. Chunk resources at source boundaries. Select explicit attachments first, then filename matches,
   then bounded local relevance. Ask the user when several files have the same name.
5. Add read-only `search_conversation_files` / `read_conversation_file` with validated resource IDs
   and bounded results; providers without tools use bounded local selection. Vector indexing is
   not required for the first version. Preserve source labels through context compaction.
6. Distinguish a file card reference, already-sent message content and a library entry. Deletion
   removes live references and cancels parsing; it cannot retract data already sent to a provider.
   Define how historical excerpts and summaries are cleared before changing deletion behavior.
7. Keep non-image cards non-clickable as currently agreed. Preview navigation, drag/drop and true
   progress indicators can be a separate UI change; indeterminate work must not show fake percent.

Conversation-file tools must only access resources attached to that Chat page. They must not
accept arbitrary local paths, write files or inherit Project assistant source access.

References used for planning: [PDF.js architecture](https://mozilla.github.io/pdf.js/getting_started/),
[PDF.js page API](https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib-PDFPageProxy.html),
[PyMuPDF OCR notes](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html),
[Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/).
