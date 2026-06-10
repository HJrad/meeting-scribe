# Team Sync — Meeting Notes

**Date:** 2026-01-15 · **Participants:** Sam (host), Alice, Bob · **Language:** en

## TL;DR
Team aligned on shipping the v2 export pipeline behind a feature flag. Alice
owns the API contract; Bob takes the migration. Go-live targeted for next sprint
pending load-test sign-off.

## Decisions
- Roll out v2 export behind `export_v2` flag, default off.
- Keep the legacy endpoint for one release cycle, then deprecate.

## Action Items
| Owner | Task | Due |
|---|---|---|
| Alice | Finalize export API contract | Jan 22 |
| Bob   | Write data migration + rollback | Jan 24 |
| Sam   | Schedule load test + sign-off    | Jan 26 |

## Risks & Open Questions
- Load-test capacity unconfirmed — may slip go-live.
- Open: do we backfill historical exports, or forward-only?
