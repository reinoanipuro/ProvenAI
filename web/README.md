# ProvenAI web app (Lovable)

`web/app/` is the web front end built in Lovable, copied from
<https://github.com/aapodaniel/screenshot-perfect>. It talks to the ProvenAI
backend through the API under `/lovable`, provided by `backend/lovable.py`.
The Streamlit page in `frontend/` stays as a fallback.

## Run it

Start the backend (from the project root, in its Python environment):

```powershell
$env:PROVENAI_INDEX_DIR = "C:\path\to\index"   # if the index is outside the project
uvicorn backend.api:app
```

Start the web app in a second terminal. Install the packages once; keep
`node_modules` out of OneDrive if you can, because it holds many thousands of files:

```powershell
cd web\app
npm install
npm run dev
```

`web/app/.npmrc` sets `legacy-peer-deps=true`, because npm 10 otherwise crashes
on this project ("Cannot read properties of null (reading 'edgesOut')"). Lovable
itself uses Bun, which does not need it.

Open the address `npm run dev` prints. The app uses
`http://localhost:8000/lovable` with demo data off by default. Change either in
the app's **Settings** page, or with `VITE_API_URL` and `VITE_DEMO=true` before
`npm run dev`.

> The app falls back to its built-in demo data whenever the backend cannot be
> reached, and only shows a short warning. Before a demo, check the backend is
> running, or results may come from the demo data, not from the documents.

## How the app's API maps to the backend

| App call | What the backend does |
|---|---|
| `POST /lovable/inspections` (files, name, rule sets) | Stores the files and starts a check in the background. The app polls until it is done. |
| `GET /lovable/inspections/{id}` | Progress, elements and results. |
| `GET /lovable/rulesets`, `GET /lovable/rules` | The approved rule library (ADA, PVAG, Load Line, BWM), with self-tests run by the backend. |
| `POST /lovable/rules`, `POST /lovable/rules/{id}/approve` | A rule proposed from pasted text. It can only be approved if the text is found in a regulation PDF, so every approved rule has a source page. |
| `POST /lovable/inspections/{id}/answers` | Values entered by the engineer, rechecked at once. |
| `.../review`, `.../notes`, `.../files/{id}` | Review marks, notes and the original files. |

How results are mapped onto the app's model:

- **Elements**: one per design element found in the documents. The app only knows
  doors, cabins and corridors, so other elements are shown as the closest type.
- **Position on the drawing**: values read from a PDF are located on their page,
  so the app can mark them. Values from text or Word files have no position.
- **Rules with a minimum and a maximum** (for example handrail height) become two
  checks, `...-min` and `...-max`, because the app has one limit per check.
- **PASS / FAIL** always comes from the backend's Python rules. Sources that
  disagree give UNKNOWN, as the app expects.
- **Items without an approved rule** are looked up in the regulations by Mistral
  (at most 6 per inspection, about 1 to 3 minutes each). They are listed under
  "Read from regulation by AI" and always need review.

## Update from Lovable

The app keeps changing in Lovable. To bring in the latest version, copy it over
`web/app` again, keeping `node_modules`:

```powershell
git clone https://github.com/aapodaniel/screenshot-perfect $env:TEMP\lovable-app
robocopy $env:TEMP\lovable-app web\app /E /XD .git node_modules
```

Then check `web/app/src/lib/settings.ts` still points at the ProvenAI backend
and `web/app/.npmrc` is still there (see above and below), and run the backend
tests: `python -m pytest tests/test_lovable.py`.

### One change to make in Lovable

The copy here changes the app's default settings in `src/lib/settings.ts`, so it
uses this backend with demo data off. Ask Lovable to make the same change, or it
will be lost on the next update:

> In src/lib/settings.ts, read the default API URL from
> `import.meta.env["VITE_API_URL"]`, falling back to
> `http://localhost:8000/lovable`, and make demo mode default to off unless
> `import.meta.env["VITE_DEMO"]` is "true".

`LOVABLE_PROMPT.md` describes the backend API in more detail for further work in Lovable.
