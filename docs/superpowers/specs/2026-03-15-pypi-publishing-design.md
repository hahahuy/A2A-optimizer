# PyPI Publishing Setup — Design Spec
**Date:** 2026-03-15
**Package:** `ascp-optimizer`
**Repo:** `github.com/hahahuy/A2A-optimizer`
**Status:** Approved

---

## Goal

Make `pip install ascp-optimizer` work from PyPI, with automated publishing via GitHub Actions on version tags, and CI tests on every push/PR.

---

## 1. `pyproject.toml` Fixes

### 1.1 Build Backend (Bug Fix)
Current value is broken:
```toml
# WRONG
build-backend = "setuptools.backends.legacy:build"

# CORRECT
build-backend = "setuptools.build_meta"
```

### 1.2 Add Project URLs
```toml
[project.urls]
Homepage = "https://github.com/hahahuy/A2A-optimizer"
Repository = "https://github.com/hahahuy/A2A-optimizer"
"Bug Tracker" = "https://github.com/hahahuy/A2A-optimizer/issues"
```

### 1.3 Add Author
```toml
authors = [
  {name = "hahahuy"}
]
```

### 1.4 Scope Package Discovery
```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["ascp*"]
exclude = ["tests*"]
```

---

## 2. `.gitignore` Updates

Replace current minimal `.gitignore` with full Python packaging exclusions:

```gitignore
# Worktrees
.worktrees/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd

# Build & packaging
dist/
build/
*.egg-info/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Editors
.vscode/
.idea/
```

Additionally, remove already-tracked `__pycache__` entries from git index:
```bash
git rm -r --cached "**/__pycache__" "**/*.pyc"
```

---

## 3. GitHub Actions Workflows

### 3.1 `ci.yml` — Test on every push/PR

**File:** `.github/workflows/ci.yml`
**Triggers:** `push` to `master`, `pull_request` targeting `master`
**Matrix:** Python 3.10, 3.11, 3.12

```
Steps:
  1. actions/checkout@v4
  2. actions/setup-python@v5  (matrix.python-version)
  3. pip install -e ".[dev]"
  4. python -m pytest -v
```

### 3.2 `publish.yml` — Test + Build + Publish on version tags

**File:** `.github/workflows/publish.yml`
**Triggers:** `push` tags matching `v*`
**Python:** 3.12 only (no matrix needed for publish)
**Permissions:** `id-token: write`, `contents: read` (required for OIDC)
**Environment:** `pypi` (must match Trusted Publisher config on pypi.org)

```
Jobs:
  test:
    steps:
      1. actions/checkout@v4
      2. actions/setup-python@v5 (3.12)
      3. pip install -e ".[dev]"
      4. python -m pytest -v

  publish:
    needs: [test]          ← only runs if test job passes
    steps:
      1. actions/checkout@v4
      2. actions/setup-python@v5 (3.12)
      3. pip install build
      4. python -m build   → produces dist/*.whl and dist/*.tar.gz
      5. pypa/gh-action-pypi-publish@release/v1
         (no password/token — OIDC trusted publisher)
```

---

## 4. PyPI Trusted Publisher Setup

### 4.1 One-Time Manual Setup (pypi.org)

Before the first publish, register a Trusted Publisher on pypi.org:

1. Go to **pypi.org → Your Account → Publishing → Add a new pending publisher**
   *(Use "pending" publisher if the package doesn't exist yet on PyPI)*
2. Fill in:
   - **PyPI Project Name:** `ascp-optimizer`
   - **Owner:** `hahahuy`
   - **Repository:** `A2A-optimizer`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. Save.

This allows GitHub Actions to publish to PyPI without any stored secrets.

### 4.2 GitHub Environment Setup

In the GitHub repo settings:
1. Go to **Settings → Environments → New environment**
2. Name it `pypi`
3. Optionally add protection rules (e.g. require manual approval before publish)

### 4.3 Document in `docs/PUBLISHING.md`

A `PUBLISHING.md` file will be created documenting the release process:

```
Release checklist:
1. Bump version in pyproject.toml
2. git commit -m "chore: bump version to X.Y.Z"
3. git tag vX.Y.Z
4. git push && git push --tags
→ GitHub Actions runs tests, builds, and publishes automatically
```

---

## 5. Files Changed / Created

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Edit | Fix build backend, add URLs, author, exclude tests |
| `.gitignore` | Edit | Full Python packaging exclusions |
| `.github/workflows/ci.yml` | Create | Test matrix on push/PR |
| `.github/workflows/publish.yml` | Create | Test + build + OIDC publish on `v*` tags |
| `docs/PUBLISHING.md` | Create | Step-by-step release guide |

---

## 6. Out of Scope

- Version bumping automation (`bump2version`, `python-semantic-release`) — manual edit of `pyproject.toml` is sufficient for now
- TestPyPI pre-flight — first publish goes directly to PyPI via Trusted Publisher
- Changelog generation — separate concern

---

## 7. Success Criteria

- [ ] `python -m build` produces valid `dist/ascp_optimizer-0.1.0-py3-none-any.whl` and `.tar.gz`
- [ ] CI workflow runs and passes on push to `master`
- [ ] Pushing `v0.1.0` tag triggers `publish.yml`, tests pass, package appears on pypi.org
- [ ] `pip install ascp-optimizer` installs successfully
- [ ] `from ascp import SchemaRegistry` works after install
