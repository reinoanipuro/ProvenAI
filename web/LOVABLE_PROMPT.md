# Notes for working on the app in Lovable

The app already exists (`web/app`). Paste the parts below into Lovable when
changing it, so it keeps working with the ProvenAI backend.

## Keep the API as it is

The backend at `<API URL>` (default `http://localhost:8000/lovable`) provides
exactly the calls in `src/lib/api.ts`: `/health`, `/rulesets`, `/rules`,
`POST /rules`, `POST /rules/{id}/approve`, `/inspections`, `POST /inspections`
(multipart `name`, `files`, `ruleset_ids`), `/inspections/{id}`, `.../answers`,
`.../results/{rid}/review`, `.../results/{rid}/notes`, `.../files/{fileId}`.
Keep these paths, request bodies and the types in `src/lib/types.ts`.

## Changes worth asking Lovable for

1. **Settings default** (needed, see `web/README.md`):

   > In src/lib/settings.ts, read the default API URL from
   > `import.meta.env["VITE_API_URL"]`, falling back to
   > `http://localhost:8000/lovable`, and make demo mode default to off unless
   > `import.meta.env["VITE_DEMO"]` is "true".

2. **No silent demo fallback** (recommended for the accuracy demo):

   > When demo mode is off and the API cannot be reached, show a clear error
   > instead of falling back to demo data, so results never come from the demo
   > fixtures without the user noticing.

3. **Results read by AI** (optional):

   > Results whose rule_set is "Read from regulation by AI" come from the
   > regulation text, not an approved rule. Show them with a distinct badge
   > "AI-read, needs confirmation", and never count them as confirmed violations.
