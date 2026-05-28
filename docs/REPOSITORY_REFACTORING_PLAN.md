# Repository Refactoring Proposal (Structure-Only)

This proposal focuses on a **structure-only refactor** of the repository (prefer `git mv` over content edits), to improve discoverability and maintenance while preserving behavior.

## Goals

- Keep processing logic and data files unchanged.
- Group files by responsibility (code, data, generated outputs, docs).
- Make the root directory cleaner and easier to navigate.

## Proposed target structure

```text
SEEM-CZ/
├── Makefile
├── README.md
├── docs/
│   └── REPOSITORY_REFACTORING_PLAN.md
├── src/
│   └── scripts/                  # moved from ./scripts
├── data/                         # unchanged source corpus location
├── workspace/
│   └── teitok/                   # moved from ./teitok
├── outputs/
│   ├── compare_annot/            # moved from ./compare_annot
│   └── logs/                     # moved from ./logs
└── templates/
    └── html_compare/             # moved from ./template
```

## Recommended migration steps

1. Create destination directories.
2. Move directories with `git mv`:
   - `scripts -> src/scripts`
   - `teitok -> workspace/teitok`
   - `compare_annot -> outputs/compare_annot`
   - `logs -> outputs/logs`
   - `template -> templates/html_compare`
3. Update path references in `Makefile` only (no script logic changes).
4. Run the existing Make targets (dry-run first, then selected real targets).

## Why this structure

- `src/` clearly identifies executable project code.
- `workspace/` groups TEITOK working files that are project-specific but not source code.
- `outputs/` separates generated/report artifacts from source inputs.
- `templates/` isolates reusable HTML/template assets.
- `docs/` centralizes operational and maintenance documentation.

## Scope control

- Avoid changing Python script internals unless path resolution is hardcoded and cannot be redirected from `Makefile`.
- Keep refactor incremental (can be done in phases by directory).
- If desired, temporary symlinks can be used during transition to reduce path breakage risk.
