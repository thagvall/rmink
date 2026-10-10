# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so the repo
holds no tokens.

## One-time setup (done on the PyPI websites)

Add a **pending publisher** on both sites. This works before the project exists.

| Field | pypi.org | test.pypi.org |
|---|---|---|
| PyPI project name | `rmink` | `rmink` |
| Owner | `thagvall` | `thagvall` |
| Repository name | `rmink` | `rmink` |
| Workflow name | `release.yml` | `release.yml` |
| Environment name | `pypi` | `testpypi` |

- pypi.org: Account → Publishing → *Add a new pending publisher*
- test.pypi.org: the same steps, with a separate account on test.pypi.org

The GitHub environments `pypi` and `testpypi` already exist. `pypi` only
accepts `v*` tags and waits for a maintainer to approve the deployment.

## Trying the pipeline (TestPyPI)

GitHub → Actions → *Release* → *Run workflow*. The workflow builds the
package, runs a smoke test and uploads the current version to TestPyPI.
To check it:

```bash
uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ rmink devices
```

TestPyPI never accepts the same version twice, so bump the `.devN` suffix in
`pyproject.toml` before each new trial upload.

## Releasing a version

1. Set `version` in `pyproject.toml` (e.g. `2.0.0`) and update `CHANGELOG.md`.
2. Commit, then tag and push:
   ```bash
   git tag v2.0.0 && git push origin main v2.0.0
   ```
3. Approve the `pypi` deployment in the Actions run.

The workflow checks that the tag matches the version, builds the package,
runs the smoke test, publishes to PyPI and creates a GitHub release with the
files. Tags such as `v2.0.0rc1` are marked as pre-releases.

## Known constraint

rmscene 0.8 pins `packaging<24`. Isolated installs (`uvx`, `pipx`, Docker)
resolve without problems, but installing rmink into an environment that
needs a newer `packaging` will conflict.
