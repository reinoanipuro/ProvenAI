<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.
<!-- LOVABLE:END -->

## Project rules
- All API calls and types go through `src/lib/api.ts`; demo mode and network-error fallback use `src/lib/mockData.ts` — keeps the app usable with zero backend.
- PASS/FAIL/UNKNOWN is decided only in `src/lib/rulesEngine.ts` (covered by `rulesEngine.test.ts`); missing or conflicting evidence must yield UNKNOWN — core product principle.
- Keep finding titles and revision display comparisons in `src/lib/presentation.ts`; these format engine results without making compliance decisions.
- JSON rule imports are validated and self-tested through `src/lib/api.ts`, remain proposals until engineer approval, and failing rules cannot be approved.
- Revision comparisons use explicit previous-revision references; never invent changes from inspection names or counts.
- Home and inspection results share CheckerWorkspace, a viewport-height CAD canvas with independent ruled notes and an inline bottom properties inspector; one shared presentation avoids diverging checking flows.
- RUN CHECK stages existing API results as client-side redline stroke animations; presentation timing and decorative cloud geometry never change compliance decisions.
- Pre-bundle newly used Radix packages in Vite optimizeDeps.include; late dependency optimization can mix React instances and crash hooks in an already-open preview.
- Reference drawings are CDN asset pointers displayed by DrawingViewer; demo finding geometry lives exclusively in normalized src/data/overlays.json mappings resolved by drawingOverlays.ts, never in PDF bboxes or compliance logic, so calibration changes cannot alter verdicts.
- DrawingStart owns the empty/load state; uploaded PDFs are preview-only in demo mode and never inherit reference findings, because demo fixtures are not document extraction.
- Daily reports derive verdicts from inspection results and today's work from browser-session run events in checkerSession; unavailable daily baselines, source pages and model versions stay explicitly unavailable rather than fabricated.

- CheckerHeader owns shared title, workflow, counters and primary action; headerPresentation derives action stages from review state without altering compliance decisions.
