# GitHub sync protocol

`outputs/tunings/backtest_run_history.csv` is a shared, append-only record of
backtest runs. It is intentionally the only generated output tracked in Git.
Its Git merge driver combines rows from both machines and removes only exact
duplicates, so a normal pull does not discard independently produced results.

## One-time setup on every clone

```powershell
python --version
powershell -ExecutionPolicy Bypass -File scripts/setup_git_sync.ps1
```

The setup script writes the local Git configuration that activates the
repository's versioned `.gitattributes` rule. It must be run once per clone,
including by any agent or machine that will merge or pull the history.

## Routine history sync

After a backtest finishes, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_backtest_history.ps1
```

The helper configures the merge driver, commits only the history, pulls with a
merge (which unions concurrent rows), and pushes. It stops before pulling if
any unrelated working-tree files are changed, preventing accidental overwrites.

For a manual workflow, first commit the history, then use `git pull --no-rebase`
(not `--ff-only`) and `git push`. Do not use `git checkout --` or a hard reset
to resolve a history conflict; rerun the setup script and retry the merge.
