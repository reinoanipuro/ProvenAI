# ProvenAI

ProvenAI checks ship designs against maritime and accessibility regulations.
Python makes every decision, a local Mistral model only reads text and writes
summaries, and every result links to the regulation page it comes from.

## Start

After the one-time setup (see Installation, Local language model and the
regulation index below), start everything with one command in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

It opens the checker (port 8000) and the web app (port 8080) in their own
windows and opens http://localhost:8080. Drop a 2D picture of a design (PNG,
JPG) or a design document (PDF, Word or text). The result page shows:

- the verdict, and a summary of the whole design: Python's summary at once,
  then Mistral's AI summary, which is kept only if every number in it is in
  the results;
- the design with every issue boxed in red where it is printed (pictures and
  scanned pages are read with local OCR: OnnxTR, the ONNX build of docTR by
  Mindee, France);
- numbered next steps: what to fix, what to confirm, and what Mistral and
  Python could not resolve and the engineer must check by hand, each with the
  regulation file and page. Opening a step shows that page with the quote
  highlighted.

The result is shown as soon as Python has checked the values; the AI summary
and the AI reading of regulations for values no rule covers follow in the
background, and the page updates by itself.

To try it with random, unbiased test designs and an answer key:
`python scripts/make_random_plan.py` (text PDF) and
`python scripts/make_plan_picture.py` (2D deck plan picture).

## How the design check works

```text
Design text or question
  -> Mistral reads the design items           (the engineer confirms the values)
  -> approved rule?   yes -> Python calculates PASS or FAIL
                      no  -> RAG finds passages, Mistral reads the requirement,
                             Python reviews it, then calculates
  -> RAG confirms the quote on the cited page
  -> Mistral writes a summary, Python rejects it if it adds numbers
  -> result, margin, citation, highlighted page, steps to verify by hand
```

Each result has a level, so the engineer knows how far to trust it:

| Level | Meaning | Can fail a design? |
|---|---|---|
| Approved rule | A rule in `data/rule_library.json`, checked by a person | Yes |
| Read from regulation by AI | Mistral found the requirement, Python confirmed the quote and limit are really in the passage, with a confidence level | No, it reports possible issues |
| Manual review | Nothing reliable found; the closest passages are shown | No |

Add a rule by approving an AI-read requirement in the interface, or by adding an
entry to `data/rule_library.json`. No code changes are needed.

## RAG workflow

```text
PDF regulations -> text extraction -> structure-aware chunks
-> local embeddings -> ChromaDB -> CrossEncoder reranking -> cited results
```

The current RAG supports text-based PDFs. Scanned PDFs are rejected clearly
because OCR is not included yet.

## Add compliance PDFs

Put compliance PDFs in:

```text
data/regulations/
```

Rebuild the local vector index after adding or replacing PDFs:

```powershell
python rebuild_rag.py
```

The command extracts PDF text, creates chunks, generates local embeddings, and
stores the chunks in ChromaDB. Each result includes the PDF filename, page
number, section, source text, vector score, and reranking score.

## Search the regulatory knowledge base

Start the backend:

```powershell
uvicorn backend.api:app --reload
```

Then search the index from another PowerShell terminal:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/rag/search `
  -ContentType "application/json" `
  -Body '{"query":"minimum escape route width","top_k":5}'
```

The index must be rebuilt before searching. If it is not ready, the API
returns an actionable error explaining how to build it.

## Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

The first index build downloads the embedding and reranking models. The models
are cached locally for later runs.

## Web app

`web/app/` is the web front end built with Lovable. It uses the backend's
`/lovable` API (`backend/lovable.py`). `web/README.md` explains how to run it,
how its API maps to the checker, and how to update it from Lovable. The
Streamlit page in `frontend/` stays as a fallback.

```powershell
cd web\app
npm install
npm run dev
```

## Local language model

Install [Ollama](https://ollama.com) and download the model:

```powershell
ollama pull ministral-3:8b
```

It runs on the CPU and needs about 6 GB of memory. Each Mistral step takes about
a minute on a laptop. Set `PROVENAI_LLM_MODEL` to use another model.

## Run the demo

If the index is stored outside the project, set its location in every terminal:

```powershell
$env:PROVENAI_INDEX_DIR = "C:\path\to\index"
```

Start the backend in one terminal:

```powershell
uvicorn backend.api:app
```

Start the Streamlit frontend in a second terminal:

```powershell
streamlit run frontend/app.py
```

Open the URL printed by Streamlit, usually `http://localhost:8501`.

## Test it step by step

1. **Drop documents:** on the Design check tab, drop the sample files in
   `data/samples/designs/` (a text file and a Word file), and click "Read the
   documents". Check the values and where each was found, turn off the Mistral
   summary, and click "Check the design". The corridor fails by 115 mm.
   PDFs, CSV files and pictures can be dropped too. Pictures and drawing pages
   without text are stored for 2D reading, which is a later step. To type
   instead, open "Or type a description or question instead".
2. **See why:** on a result, turn on "Show the regulation page". The cited
   requirement is highlighted on the PDF page.
3. **Regulation text without a rule:** pick "Ballast water system" or
   "Regulation question", and turn off "Use approved rules". The result is read
   from the regulation by Mistral, with Python's review and a confidence level.
4. **Not covered:** pick "Not covered (no DNV rules)". The honest answer is
   manual review, with the closest passages, not a guess.
5. **Rule library:** the Rule library tab lists every approved rule with its page.

## Run the tests

```powershell
python -m pytest
```

Measure accuracy on cases with known answers (needs the index):

```powershell
python tests/eval_checks.py          # confirmed values, about a minute
python tests/eval_checks.py --llm    # Mistral reads each case as text, slow
python tests/eval_rag.py             # regulation search quality
```

## Team ownership

- **Data Engineering and AI member 1:** `backend/rag.py`,
  `rebuild_rag.py`, and `data/regulations/`
- **Data Engineering and AI member 2:** `backend/models.py`,
  `backend/api.py`, and tests
- **Industrial Engineering and Management member:** `frontend/app.py`,
  `data/samples/`, and product documentation
