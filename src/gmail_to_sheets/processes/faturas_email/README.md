# Faturas Email Process

Saves email attachments into a Google Drive folder, then labels and
archives the message. Opt-in: registered only when
`FATURAS_EMAIL_ENABLED=true` and at least one route is configured.

## Routes

`FATURAS_EMAIL_ROUTES` is a JSON array, one object per sender:

| key | required | meaning |
|-----|----------|---------|
| `sender` | yes | query becomes `in:inbox from:<sender>` |
| `drive_folder_id` | yes | destination Drive folder |
| `label` | yes | Gmail label applied on archive (nested with `/`) |
| `filename_token` | yes | middle token of the Drive file name |
| `query` | no | overrides the default `in:inbox from:<sender>` |
| `attachment_ext` | no | overrides `FATURAS_EMAIL_ATTACHMENT_EXT` (default `.pdf`) |

## Flow

Per route, once per run:

1. `check_pending` does a cheap `search_messages(..., max_results=1)` for
   every route.
2. Pick the **oldest** matching inbox message.
3. For every attachment matching the extension (MIME tree walked
   recursively): name it `AAAA_MM_DD_<token>_<original>` where the date is
   the message received date (`TIMEZONE`). If that name already exists in
   the folder, a ` (1)`, ` (2)`, ... suffix is added before the extension —
   the file is never overwritten.
4. Upload each attachment.
5. Apply the route `label` and archive the message — **always**, even when
   there was no matching attachment or the files already existed, so the
   message leaves the inbox and is not reprocessed.

## Auth

Drive uploads use the **Gmail OAuth account** (not the Sheets service
account, which has no Drive storage quota). The token needs the
`https://www.googleapis.com/auth/drive.file` scope in addition to
`gmail.modify`; adding it requires re-running the OAuth consent once. The
folder must be writable by that account.

`drive.file` is per-file: the app can upload into the folder, but it only
*sees* files it created there. Duplicate detection therefore compares
against the app's own past uploads (a file a person dropped in by hand is
invisible and never causes a `(1)` rename).

## Notes

- Never writes to any spreadsheet; independent of `CONTAORDEM`.
- Runs last (`priority = 50`).
- One message per route per run (same conservative pattern as Extrato); a
  backlog drains over successive ticks.
