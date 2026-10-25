# Vendored: Replay `packages/tv-core`

Copied unchanged from [subatomic-hamster/replay](https://github.com/subatomic-hamster/replay) at commit
`2db92c0e30f22ece0ffbee0d5d39ea7012cf0011` (2026-10-23), `packages/tv-core/src/{types,follow,clock,retry,display,replays}.ts`.
MIT licensed, "Copyright (c) 2026 Replay"; the notice is in `LICENSE` beside these files and recorded in `docs/licenses.md`.
Don't edit these files; adapt in `apps/watch/src/lib/` instead, so a later re-vendor stays a clean copy.

Watch uses `clock.ts` now. `display.ts`, `follow.ts` and `replays.ts` are vendored for later features (follow cam, multi-angle) but are excluded from `tsconfig.json` because they don't pass this repo's `noUncheckedIndexedAccess`; adapt them in `src/lib/` when used.
