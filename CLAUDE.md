# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A collection of standalone scripts (no package/CLI wrapper, no test suite) that turn PDF investment
research reports into a local ChromaDB vector store for semantic + keyword search. Each script is run
directly with `python <script>.py` and most have file paths hardcoded at the top rather than accepting
CLI args (`import_chunks_to_db.py` is a partial exception — it reads `sys.argv[1]` but currently has that
line commented out in favor of a hardcoded path; check before assuming it takes an argument).

Dependencies (no requirements.txt exists): `pdfplumber`, `voyageai`, `chromadb`, `python-dotenv`, `numpy`
(ad hoc scripts only). `.env` holds `VOYAGE_API_KEY`, loaded via `python-dotenv`.

## Two parallel, incompatible chunking pipelines

There are two separate PDF → chunk-JSON pipelines with **different chunk schemas**. Anything that reads
chunk JSON must know which pipeline produced it:

- **Type A** (`pdf_chunk_typeA.py`) — for short daily 晨報/快訊 reports. Chunks 1:1 per PDF page, no
  structural analysis. Report filenames are hardcoded in a list inside the script. Output schema:
  `{"source_file", "page_number", "text"}`, written to `~/Desktop/chunks_typeA.json`.
- **Font-heuristic v2** (`pdf_chunk_MorganStanly.py`) — for long structured sell-side reports (currently
  tuned for Morgan Stanley's layout). Output schema: `{"section", "subsection", "title", "start_page",
  "content"}`, written to `<pdf_stem>.chunks.v2.json` next to the source PDF.

`build_db.py` (embeds Type A chunks) and `import_chunks_to_db.py` (embeds v2 chunks) both write into the
**same ChromaDB collection** (`morning_reports`, persisted at `./chroma_db/`, gitignored), but each derives
`ids`/`metadatas` differently to match its own chunk schema — `build_db.py` uses
`f"{source_file}_p{page_number}"`, `import_chunks_to_db.py` uses `f"{source_file}_p{start_page}_{idx}"`.
Don't cross-wire a chunk-JSON file from one pipeline into the other pipeline's importer.

## `pdf_chunk_MorganStanly.py` internals

Classifies each PDF text line into a heading level purely from **font size** (no regex/keyword guessing —
an earlier text-rule-based approach is documented in the file's module docstring as having failed):

- `LEVEL1_MIN_SIZE = 18` → section heading, `LEVEL2_MIN_SIZE = 11` → subsection heading, else body text.
- Any line starting with `Exhibit <n>` is always force-split into its own chunk regardless of font size,
  since each exhibit/table is treated as a self-contained semantic unit.
- `DISCLOSURE_MARKERS` + `DISCLOSURE_MIN_SIZE` locate where the legal disclosure section starts; everything
  from that page onward is dropped from chunking.
- `is_report_index_chunk()` drops chunks that are mostly a list of past-report citations (detected by
  counting `(DD Mon YYYY)`-style date patterns in the chunk text) — these are index/reference lists with
  no analytical content and just dilute vector search quality.
- Two-column pages are handled by first grouping chars into lines by `top` position, then assigning each
  whole line to the left or right column based on where the line *starts* (not per-character), then
  reading all left-column lines before all right-column lines. A per-character column split was tried
  first and rejected — it sliced full-width paragraphs/table rows in half.

**Font thresholds and `DISCLOSURE_MARKERS` are calibrated to Morgan Stanley's specific PDF layout.**
Other brokers in `/Users/weilichuan/Desktop/PDF/外資/` (UBS, Citi, Daiwa, ML, 华创证券, etc.) very likely
use different font sizes and disclosure wording — applying this script unmodified to their PDFs risks
silently wrong heading detection and an undetected/misplaced disclosure cutoff. Check font-size
distribution on a new broker's PDF before trusting its chunk output.

## VoyageAI rate limits shape the embedding code

Accounts without a payment method on file are capped at **3 RPM / 10K TPM**, regardless of remaining free
token balance. This is why every embedding script (`build_db.py`, `import_chunks_to_db.py`,
`embad_test.py`) batches texts (`batch_size`), sleeps between batches, and retries on failure with a fixed
backoff — these aren't arbitrary and shouldn't be stripped out without accounting for the rate limit.
`voyage-3` gets 200M free tokens; other models have different free-token pools (see
https://docs.voyageai.com/docs/pricing).

## `search_test.py` hybrid search

Supports an optional `keyword` variable that, when set, pre-filters via ChromaDB's
`where_document={"$contains": keyword}` before ranking the filtered subset by embedding distance, and
widens `n_results` to 10 in that mode. This exists because pure vector search on long narrative chunks
that mention multiple companies tends to rank the company you actually care about far outside top-3 when
it's a secondary subject of the paragraph rather than the main topic. `$contains` is a literal
case/language-sensitive substring match — it will not bridge a Chinese company name (e.g. 博通) to its
English form in the source text (Broadcom).
