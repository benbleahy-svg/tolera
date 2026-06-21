# Paperless Parts KB — parked during build

The tier-5 PP knowledge base (186 articles) is **parked in `archive/kb-reference/`** until the build is finished, to keep the active tree focused on the normative specs. It's already distilled into the tier-1–3 sub-specs.

It remains **on disk and greppable** (grep ignores `.gitignore`), and is recoverable from git history (commit `1bdfb6c`). To restore it here:

```
mv ../../../archive/kb-reference paperless-parts-kb-reference
```

Tier-5 = descriptive only; superseded by the sub-specs and always by `../../subsystems/DACH-DELTA-LAYER.md`. Coverage vs spec is mapped in `../../analysis/KB-Coverage-Gap-Analysis.md`. See `CLAUDE.md` §4.
