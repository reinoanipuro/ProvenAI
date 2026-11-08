# ProvenAI

**ProvenAI reads a ship design document, finds the values in it (door widths,
ramp slopes, rail heights ...), and checks each one against the regulations.
It marks every problem in the document and shows the exact regulation page that
says why.**

Built for the Since AI 2026 hackathon, Meyer Turku challenge "Automated Class &
Regulatory Compliance Checking".

The one rule the whole project follows: **Python makes every pass or fail
decision. The AI only reads text and writes summaries**, and a result is only
shown as a finding if its regulation quote is really on the regulation page.

---

## What you get

Drop a design document (PDF with text, Word `.docx`, `.txt`, `.md`, `.csv`) and
the result page shows:

- **The verdict:** Compliant or Not compliant, with counters for issues, things
  to check and things that are OK.
- **A summary** of the whole document. Python writes one at once, then the local
  AI writes a better one. The AI summary is thrown away if it contains a number
  that Python did not calculate.
- **The document itself** with a box around every value that has a problem
  (red = issue, amber = to check). Click a box to see why.
- **"What to do now":** a numbered to-do list in the order the values appear in
  the document. Values on the same item are grouped under one main task. Each
  note has the comparison (for example `760 mm < 815 mm minimum`), the quote
  from your document, and the regulation file and page. Tick a step's number
  when you have dealt with it.

The result appears as soon as Python has checked the values. The AI summary and
the AI reading of regulations for uncovered values follow in the background and
the page updates by itself.

---

## Quick start

You need Windows, Python 3.11+, Node.js, and [Ollama](https://ollama.com).

**Once:**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull ministral-3:3b
python rebuild_rag.py          # builds the regulation search index (a few minutes)
```

**Every time:**

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

This starts Ollama (if it is not running), the checker (port 8000) and the web
app (port 8080), and opens http://localhost:8080. The first run also installs
the web app's packages. Close the two windows to stop it.

Then drop a document on the page and wait. On a laptop CPU a check takes about
2 to 6 minutes, because the AI is running without a graphics card.

---

## How it works, for beginners

Think of a **junior engineer with a highlighter and a rulebook**:

1. They read your document.
2. They underline every number that matters ("door width: 760 mm").
3. They look up the rule for each one in the rulebook.
4. They compare the number with the limit and mark problems in red.
5. For every mark they write down *which page of the rulebook* says so.

ProvenAI does exactly that, with one important difference: **the "junior
engineer" (the AI) is never allowed to decide who passes.** It can read and
suggest. A plain, predictable Python program checks the arithmetic, and a second
Python check confirms the quoted rule text is really on that rulebook page.

### The pipeline, step by step

```text
  YOU drop a document
          |
          v
 1. READ        backend/documents.py
    Get the text out of the PDF, Word or text file.
    Pages that are scans or drawings (no text) are reported, not guessed at.
          |
          v
 2. FIND VALUES  backend/intake.py  +  local AI (Mistral)
    The AI lists the design values it sees: "door D-212, clear width, 760 mm".
    Python then throws away anything not word-for-word in the document,
    so the AI cannot invent a value.
          |
          v
 3. DECIDE       backend/rules.py, backend/checker.py
          |
          |-- Is there an APPROVED RULE for this kind of value?
          |       (data/rule_library.json, e.g. "door clear width >= 815 mm")
          |
          |   YES --> Python compares the number with the limit.  PASS or FAIL.
          |           Python also confirms the rule's quote is on its page.
          |
          |   NO  --> RAG search finds the closest regulation passages.
          |           The AI proposes a limit and a quote from them.
          |           Python checks the quote and the numbers are really there.
          |             found and verified --> "possible issue, please confirm"
          |             nothing reliable   --> "check by hand" + closest page
          |
          v
 4. BUILD THE RESULT   backend/lovable.py
    Group values, locate each one on the PDF page (for the red boxes),
    write the to-do list, write a plain Python summary.  The page opens now.
          |
          v
 5. IN THE BACKGROUND
    The AI writes a better summary (rejected if it adds numbers),
    and reads regulation passages for values no rule covers.
```

### Who decides what

| Job | Who does it |
|---|---|
| Read text out of the file | Python |
| Spot design values in the text | AI (Mistral), then Python verifies each one |
| Calculate PASS or FAIL | **Python only** |
| Find regulation text for an unknown value | RAG search (Python) |
| Propose a limit from regulation text | AI, then Python verifies quote and numbers |
| Write the summary | AI, then Python rejects it if it invents numbers |

### How far to trust each result

| Level | What it means | Can it fail a design? |
|---|---|---|
| **Approved rule** | A rule in `data/rule_library.json`; its quote was confirmed on the regulation page | Yes |
| **Read from regulation by AI** | The AI found a requirement; Python confirmed the quote and numbers are in the passage | Possible issue, an engineer confirms |
| **Manual review** | Nothing reliable found; the closest regulation pages are shown | No, never |

### Architecture

```text
  BROWSER  (React web app, web/app, port 8080)
     |  upload file / poll result / show PDF + notes
     v
  BACKEND  (FastAPI, backend/, port 8000)
     |
     |-- documents.py   read the file
     |-- intake.py ----------------+
     |-- checker.py ---------------+--->  OLLAMA  (local Mistral, port 11434)
     |-- rules.py                         reads values, reads passages,
     |-- lovable.py (orchestrates)        writes summaries. Never decides.
     |-- pages.py   regulation page image with the quote highlighted
     |
     '-- rag.py  (regulation search)
            question
              |-- vector search   ChromaDB + small embedding model
              |-- keyword search  BM25
              |-- merge both lists (reciprocal rank fusion)
              '-- re-rank the best 20 with a cross-encoder
                    -> the best passages, with file, page and section

  FILES ON DISK
     data/rule_library.json   approved rules (limit, quote, source page)
     data/regulations/*.pdf   the regulation texts
     .runtime/chroma          the search index built from those PDFs
     .runtime/inspections     saved results      .runtime/uploads   your files
```

Everything runs on your own machine. No document is sent to the internet.

### The RAG in plain words

RAG means "retrieval augmented generation": **look it up before answering**.
The regulation PDFs are cut into pieces at their real section headings
(`backend/rag.py`), turned into numbers that capture meaning (embeddings) and
stored in ChromaDB. When the checker needs the rule for an unknown value it asks
the search, which combines a meaning search with a keyword search, re-orders the
best 20 results with a more careful model, and returns passages that each know
their file, page and section. The AI then reads only those passages instead of
guessing from memory. The same search also confirms that every approved rule's
quote exists on its page.

---

## Folder structure

```text
ProvenAI/
|-- start.ps1                 one command that starts everything
|-- rebuild_rag.py            rebuild the regulation search index
|-- requirements.txt          Python packages
|
|-- backend/                  the checker (Python, FastAPI)
|   |-- api.py                the server: health, RAG search, regulation pages, /lovable routes
|   |-- lovable.py            the web app's API: runs a check, red-box positions, to-do list, summary
|   |-- documents.py          text from PDF, Word and text files
|   |-- intake.py             asks the AI for design values; Python verifies them
|   |-- rules.py              rule library, units, number parsing, limit comparison
|   |-- checker.py            rule checks, regulation lookups, reviews of AI answers
|   |-- llm.py                the AI (Ollama) with fixed JSON answers
|   |-- rag.py                regulation search
|   |-- onnx_models.py        fast search models (ONNX, no PyTorch needed)
|   '-- pages.py              regulation page image with the quote highlighted
|
|-- data/
|   |-- rule_library.json     approved rules: limit + quote + source page
|   |-- regulations/          regulation PDFs and catalog.json (what each PDF is)
|   '-- samples/designs/      example documents and their answer keys
|
|-- web/app/                  the web app (React, TanStack, Vite)
|   '-- src/
|       |-- routes/           pages: start, earlier checks, result
|       |-- components/app/   Home, Result (notes and verdict), PdfView (document viewer)
|       '-- lib/              API calls, types, settings
|
|-- scripts/                  generators for random test documents
|-- tests/                    unit tests and accuracy evaluations
|
|-- .runtime/                 created at run time, not in git:
|   |-- chroma/               the search index
|   |-- inspections/          saved check results
|   '-- uploads/              uploaded files
'-- .venv/                    Python environment, not in git
```

---

## Adding or changing rules

A rule is data, not code. Add an entry to `data/rule_library.json` with the
attribute it limits, the minimum or maximum, and the **exact quote and page**
from a PDF in `data/regulations/`. The system checks the quote is on that page
every run. If it is not, the result is flagged instead of trusted.

Currently the library has 20 approved rules for ADA and PVAG accessibility
(doors, corridors, ramps, handrails, turning space, thresholds, toilet and table
heights, reach height), the Load Line (sill and guard rail heights) and BWM
(ballast water exchange). Other regulations (SOLAS, MARPOL, COLREG, DNV) are
found through the regulation search and always need an engineer's review.

To add a regulation PDF, put it in `data/regulations/`, describe it in
`catalog.json`, and run `python rebuild_rag.py`.

---

## Settings you can change

| Variable | Default | Meaning |
|---|---|---|
| `PROVENAI_LLM_MODEL` | `ministral-3:3b` | Ollama model. Any installed Mistral model is used if this one is missing |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama runs (point it at a GPU server to go faster) |
| `PROVENAI_INDEX_DIR` | `.runtime/chroma` | Where the search index lives |
| `PROVENAI_LLM_TIMEOUT` | `600` | Seconds to wait for one AI answer |
| `PROVENAI_KEEP_ALIVE` | `30m` | How long Ollama keeps the model in memory |
| `PROVENAI_PYTHON` | `.venv` or `venv` | Python used by `start.ps1` |

---

## Tests

```powershell
python -m pytest                     # backend unit tests
cd web\app; npm test                 # web app tests
```

Accuracy checks on documents with known answers (need the index and Ollama):

```powershell
python scripts/make_random_plan.py            # random test PDF + answer key
python tests/eval_random_plan.py --seed 42    # run one end to end and score it
python tests/eval_checks.py                   # confirmed values, about a minute
python tests/eval_rag.py                      # regulation search quality
```

The answer keys come from the limits as the regulations state them, not from the
checker's code, so a test cannot agree with a bug by copying it.

---

## Known limits

- Only text can be read. Scanned pages and CAD drawings are reported as not
  checked, never guessed.
- Approved rules cover ADA, PVAG, Load Line and BWM. Everything else is an AI
  reading that an engineer must confirm.
- Without a graphics card a check takes minutes. Pointing `OLLAMA_URL` at a GPU
  machine is the main speed-up.
- Values are read as written: `1200 mm`, `1 200 mm`, `1,200 mm`, `36 in` and
  ratios such as `1:12` are understood. A value spread over several cells or
  sentences may be missed.
- All example documents are synthetic. No real yard or customer data is used.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| The page says the checker is not running | Run `start.ps1` and wait until the checker window has started |
| A check fails with "model not found" | Run `ollama pull ministral-3:3b` |
| No regulation passages are found | Run `python rebuild_rag.py` |
| Python changes do not show | Restart the checker window |

---

