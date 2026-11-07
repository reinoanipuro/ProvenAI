# ProvenAI

ProvenAI checks ship design documents against maritime and accessibility
regulations. Python makes every pass or fail decision, a local Mistral model
only reads text and writes summaries, and every result links to the regulation
page it comes from.

## Start

After the one-time setup below, start everything with one command in
PowerShell, in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

It opens the checker (port 8000) and the web app (port 8080) in their own
windows and opens http://localhost:8080. Close the two windows to stop it.

Drop a design document: a PDF with text, Word (.docx), TXT, MD or CSV. Pages
without text, such as scans or drawings, are reported and not checked. The
result page shows:

- the verdict, and a summary of the whole document: Python's summary at once,
  then Mistral's AI summary, which is kept only if every number in it is in
  the results;
- the document with every issue boxed in red where it is written;
- numbered next steps: what to fix, what to confirm, and what Mistral and
  Python could not resolve and the engineer must check by hand, each with the
  regulation file and page. Opening a step shows that page with the quote
  highlighted.

The result is shown as soon as Python has checked the values. The AI summary,
and the AI reading of regulations for values no rule covers, follow in the
background, and the page updates by itself.

## Try it with random test documents

```powershell
python scripts/make_random_plan.py              # random planning PDF + answer key
python tests/eval_random_plan.py --seed 42      # check one end to end and score it
```

The generator writes values that meet and break the limits, in varied wording,
with notes no rule covers. The answer key comes from the limits as the
regulations state them, not from the checker's code. Samples are in
`data/samples/designs/`.

## How the check works

```text
Design document
  -> text is read from the file (PDF text layer, Word, text)
  -> Mistral finds the design values; Python keeps only values really in the text
  -> approved rule?  yes -> Python calculates PASS or FAIL against the quoted limit
                     no  -> the RAG finds the closest regulation passages
  -> result shown, with red marks, next steps and regulation pages
  -> in the background: Mistral reads those passages for a limit (Python reviews
     it), and writes the summary (Python rejects it if it adds numbers)
```

Each result has a level, so the engineer knows how far to trust it:

| Level | Meaning | Can fail a design? |
|---|---|---|
| Approved rule | A rule in `data/rule_library.json`, its quote confirmed on the regulation page | Yes |
| Read from regulation by AI | Mistral found the requirement, Python confirmed the quote and limit are in the passage | Possible issue, to confirm |
| Manual review | Nothing reliable found; the closest passages are shown | No |

Add a rule by adding an entry to `data/rule_library.json`. No code changes are
needed.

## Setup (once)

1. Python environment and packages:

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. [Ollama](https://ollama.com) and the model, which runs on the CPU and needs
   about 3 GB of memory:

   ```powershell
   ollama pull ministral-3:3b
   ```

   To use another model, for example the larger `ministral-3:8b` (about 6 GB),
   pull it and set `$env:PROVENAI_LLM_MODEL = "ministral-3:8b"` before
   starting.

3. The regulation index (see below). `start.ps1` uses `PROVENAI_INDEX_DIR` if it
   is set, otherwise `.runtime\chroma`.

4. The web app's packages are installed by `start.ps1` on its first run
   (`npm install` in `web/app`).

## Regulations and the RAG

```text
PDF regulations -> text extraction -> structure-aware chunks
-> local embeddings -> ChromaDB -> CrossEncoder reranking -> cited results
```

Put regulation PDFs in `data/regulations/` and rebuild the index after adding
or replacing PDFs:

```powershell
python rebuild_rag.py
```

The first build downloads the embedding and reranking models, which are then
cached. Scanned PDFs are rejected, because only text is indexed. To search the
index directly while the checker runs:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/rag/search `
  -ContentType "application/json" -Body '{"query":"minimum escape route width","top_k":5}'
```

## Tests

```powershell
python -m pytest                     # backend
cd web\app; npm test                 # web app
```

Accuracy on cases with known answers (needs the index and Ollama):

```powershell
python tests/eval_checks.py          # confirmed values, about a minute
python tests/eval_checks.py --llm    # Mistral reads each case, slow
python tests/eval_rag.py             # regulation search quality
python tests/eval_random_plan.py     # a random planning PDF, end to end
```

## Project layout

```text
start.ps1               starts the checker and the web app
backend/api.py          FastAPI app: RAG search, regulation pages, /lovable API
backend/lovable.py      the web app's API: checks, red mark positions, next steps, summary
backend/intake.py       reads documents and asks Mistral for the design values
backend/documents.py    text from PDF, Word and text files
backend/checker.py      rule checks, regulation lookups and Python's reviews
backend/rules.py        rule library, units and limits
backend/llm.py          Mistral through Ollama, always in a fixed JSON schema
backend/pages.py        regulation page images with the quote highlighted
backend/rag.py          regulation search (RAG)
data/rule_library.json  approved rules, each with its regulation quote and page
data/regulations/       regulation PDFs
web/app/                the web app (React, TanStack): start page and result page
scripts/                random test documents
tests/                  tests and accuracy evaluations
```

## Team ownership

- **Data Engineering and AI member 1:** `backend/rag.py`, `rebuild_rag.py`,
  and `data/regulations/`
- **Data Engineering and AI member 2:** the checker (`backend/`), the rule
  library, and tests
- **Industrial Engineering and Management member:** the web app (`web/app/`),
  `data/samples/`, and product documentation
