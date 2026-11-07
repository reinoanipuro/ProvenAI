# ProvenAI web app

`web/app/` is the engineer's interface: a start page to drop a design document
and a result page with the issues marked in red, the summary and the next
steps. It started as a Lovable prototype and now only talks to the ProvenAI
checker in `backend/lovable.py`. There is no demo data: if the checker cannot
be reached, the app says so instead of showing other results.

## Run it

`start.ps1` in the project folder starts the checker and the app together. To
run the app on its own:

```powershell
cd web\app
npm install
npm run dev        # http://localhost:8080
npm test           # tests
```

The checker address defaults to `http://localhost:8000/lovable`. Change it on
the Settings page, or set `VITE_API_URL` before starting.

## Pages

| Route | File | What it shows |
|---|---|---|
| `/` | `src/components/app/Home.tsx` | Drop zone, whether the checker is running |
| `/inspections/$id` | `src/components/app/Result.tsx` | Progress, verdict, summary, the document with red marks (`PdfView.tsx` for PDFs, a text view otherwise), next steps with regulation pages |
| `/history` | `src/routes/history.tsx` | Earlier checks |
| `/settings` | `src/routes/settings.tsx` | Checker address |

## API it uses

| Call | Backend |
|---|---|
| `POST /lovable/inspections` (files) | Starts a check in the background, returns its id |
| `GET /lovable/inspections/{id}` | Progress, results, red mark positions, next steps, summary |
| `GET /lovable/inspections/{id}/files/{file}` | The uploaded PDF, for the viewer |
| `GET /lovable/inspections/{id}/files/{file}/text` | The text of a Word or text file |
| `GET /source/page?filename&page&quote` | A regulation page with the quote highlighted |
| `GET /lovable/inspections`, `GET /lovable/health` | Earlier checks, and whether the checker runs |
