# @ops-knowledge/semi-theme

Local Semi Design theme tokens for Ops-Knowledge. Vendored into the repo so
upstream theme-package updates can't silently break our UI.

## Origin

Forked from `@semi-bot/semi-theme-double@1.0.1` (DSM-generated, ID 28532).
Compatible with Semi Foundation `>= 2.95.1`.

## Usage

Wired up in `frontend/vite.config.ts` via `@douyinfe/vite-plugin-semi`:

```ts
import semi from "@douyinfe/vite-plugin-semi"
semi({ theme: "@ops-knowledge/semi-theme" })
```

The plugin reads `scss/` at build time and injects token overrides into
Semi's internal SCSS imports. No runtime cost beyond a slightly larger
compiled CSS bundle.

## Structure

| File | Purpose |
|------|---------|
| `scss/index.scss` | Entry — pulls in font, mixin, variables |
| `scss/_font.scss` | Font-face definitions |
| `scss/_palette.scss` | Brand color palette |
| `scss/variables.scss` | Token overrides (radius, spacing, sizes, etc.) |
| `scss/global.scss` | Global Semi token overrides |
| `scss/mixin.scss` | Reusable SCSS mixins |
| `scss/animation.scss` | Theme-specific keyframes |
| `scss/custom.scss` | Empty — reserved for project-local overrides |
| `scss/local.scss` | Empty — reserved for component-scoped tweaks |

## Customising

Edit any `scss/*.scss` file directly. `custom.scss` and `local.scss` are
intentionally empty and are the recommended place for new overrides — keeps
diffs against the upstream fork small and visible.

The plugin re-bundles the SCSS on every dev hot-reload, so changes appear
on save.

## Updating against upstream

When Semi Foundation gets a major release that touches the variable names,
re-pull `@semi-bot/semi-theme-double` (or whatever current DSM theme
package), diff the `scss/` against ours, and merge meaningfully.

Do NOT just overwrite — any deliberate Ops-Knowledge tweaks live in
`custom.scss` / `local.scss` and possibly inline edits to `variables.scss`.
