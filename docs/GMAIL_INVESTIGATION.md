# Gmail Investigation — ETAPA 1

## Account Information

| Field | Value |
|-------|-------|
| **Email** | `verbodavidabraga@gmail.com` |
| **Account Type** | Gmail (personal) |
| **Status** | Confirmed |

## Email Source (Montepio)

| Field | Value |
|-------|-------|
| **Sender Email** | `noreply@montepio.pt` |
| **Attachment Type** | `.txt` |
| **Content Format** | MT940 (international standard for bank statements) |
| **Status** | Confirmed |

## Gmail Search Query

**Tested and confirmed:**
```
in:inbox from:noreply@montepio.pt has:attachment
```

### Query Notes
- The previous Google Apps Script uses this exact query.
- Searches inbox folder specifically (not archived or other labels).
- Requires both sender match AND attachment presence.
- No specific filename pattern; any `.txt` attachment will match.

## Email Processing Behavior

| Behavior | Value |
|----------|-------|
| **Label Applied** | `Serviços/Banco/Montepio24/MT940` |
| **Post-Processing** | Archive (move out of inbox) |
| **Deduplication** | By filename |
| **Batch Size** | 100 threads per request |

## Known Information from Existing Script

The existing Google Apps Script (`downloadAttachmentsFromSender`) confirms:

1. **Multiple MT940 files arrive** — processing is batched (100 at a time)
2. **Duplicates are common** — filename-based deduplication is essential
3. **Archiving prevents reprocessing** — successfully processed emails are moved out of inbox
4. **Files go to Google Drive** — current implementation; will be changed to Google Sheets

## Next Steps (Phase 2: Authentication)

Once we confirm ETAPA 1 is complete:

1. Implement OAuth 2.0 flow for Gmail in Python
2. Test authentication with the confirmed account
3. Execute the search query programmatically
4. Verify results match expectations
5. Test attachment download

## Status

✓ ETAPA 1 COMPLETE

All discovery parameters confirmed. Ready for Phase 2 (Authentication).
