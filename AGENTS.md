# Repository instructions

## Repository ownership boundary

- This `mlfund` repository owns the analysis pipeline, source fund data, reports,
  and dashboard snapshot generation.
- `dashboard/` is a separate Git repository whose canonical remote is
  `https://github.com/tklim/fund-signal-dashboard.git`.
- Never stage or commit `dashboard/` from the outer repository. Use
  `git -C dashboard ...` for every dashboard Git operation.
- Never combine outer-pipeline changes and dashboard changes in one commit.

## Dashboard workflow

- Read `dashboard/AGENTS.md` before changing the web application.
- Do not edit `dashboard/app/fund-data.generated.ts` manually. Refresh it with
  `python scripts/export_dashboard_data.py` from this repository.
- Use `scripts/setup_dashboard_repo.ps1` to clone or validate the nested
  dashboard repository.
- Use `scripts/sync_dashboard_snapshot.ps1` to prepare, validate, commit, and
  push a dashboard data-refresh branch.
- Dashboard production changes require a pull request. Never push dashboard
  changes directly to `main`.

## Safety

- Preserve unrelated working-tree changes in both repositories.
- Inspect both `git status --short` and `git -C dashboard status --short` before
  and after cross-repository work.
- Do not store GitHub or Cloudflare credentials in either repository.
