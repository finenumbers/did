# Sync engine

## CONTRACT_BACKED

- Which provider methods run per mode (from `*-contract.md`)
- SipOut: `get_cities`, `free_list` (single call), `connected_list`
- Runexis: regions/cities; free/purchased return limitations
- No undocumented pagination or city crawl

## OPERATIONAL

- Job lifecycle, logging, upsert/`payload_hash`, soft-absence, dry-run, TX batching
