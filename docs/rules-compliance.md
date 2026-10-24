# Reuse, attribution and media permissions

## Build on existing work
Trophy is an ongoing project. Agents may implement features at any time and build on existing ideas, designs and compatible licensed code. There is no event eligibility requirement, mandatory clean-room rewrite or restriction to a single library.

| Source | What it offers | How we can use it |
|---|---|---|
| [subatomic-hamster/replay](https://github.com/subatomic-hamster/replay) | Sports capture, analysis, replay, commentary and viewing designs and code; the inventory records MIT licensing | Learn from, extend, adapt, copy or vendor compatible code, including apps, renderers, services and infrastructure. Preserve required copyright/license notices and record the incorporated revision |
| [courtcam](https://github.com/subatomic-hamster/courtcam) | Replay's separately published computer-vision library; the inventory records MIT licensing | Use as a reproducibly versioned dependency, adapt it or replace it as useful. `services/courtcam-adapter` is the current integration point |
| `docs/plan/` and `docs/research/` | Product plans, integration notes and upstream measurements | Use as starting points and revise them as evidence changes; upstream results are not Trophy measurements |

When incorporating third-party code, record the source, revision, relevant license and local use in `docs/licenses.md`, and retain notices required by that license. Check the selected revision and any bundled dependencies, models or assets separately. An MIT code license does not automatically cover weights, datasets or private footage.

## Media and participant privacy
- Use footage that we own or have permission to use for the intended purpose. CC BY and CC0 are convenient defaults; other licenses are welcome when their terms are met. Keep credits in `data/clips/credits.json`.
- Check dataset terms for evaluation, public demos, redistribution and commercial use separately. A research label or demo setting is not blanket permission.
- Replay's private footage is not implicitly available to Trophy. Obtain permission before using it. Use identifying player data with consent, and anonymize or blur non-consenting people in shared clips; media involving minors needs appropriate permission.
- Keep large or private media in ignored local storage or access-controlled object storage. Small licensed, non-sensitive test fixtures may be committed when useful.
- Label synthetic fixtures, generated views and upstream benchmarks accurately.

## What remains essential
Protect credentials, participant privacy, license obligations, truthful reporting, user work and authorized resource limits. These safeguards prevent concrete harm or misleading results. Architecture, providers, model choices, ownership boundaries, branch names, version upgrades and implementation schedules remain adaptable; see [CLAUDE.md](../CLAUDE.md).
