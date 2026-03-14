# PyPI Publishing Setup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pip install ascp-optimizer` work from PyPI with automated publishing via GitHub Actions on version tags and CI tests on every push/PR.

**Architecture:** Two GitHub Actions workflows (`ci.yml` for test-on-push, `publish.yml` for tag-triggered OIDC publish). PyPI authentication uses Trusted Publisher (OIDC) — no stored secrets needed. A one-time manual setup on pypi.org links the repo to the package.

**Tech Stack:** setuptools, python-build, pypa/gh-action-pypi-publish, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-15-pypi-publishing-design.md`

---

## Files Changed / Created

| File | Action |
|------|--------|
| `pyproject.toml` | Modify — fix build backend, add URLs + author, exclude tests from package discovery |
| `.gitignore` | Modify — add full Python packaging exclusions |
| `.github/workflows/ci.yml` | Create — test matrix on push/PR |
| `.github/workflows/publish.yml` | Create — test + build + OIDC publish on `v*` tags |
| `docs/PUBLISHING.md` | Create — step-by-step release guide |

---

## Chunk 1: Project Metadata

### Task 1: Fix `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Fix the build backend**

Replace the broken backend value:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Add author and project URLs**

Inside the `[project]` table, add `authors` after the `dependencies` key, then add a new `[project.urls]` section below:

```toml
# Inside [project] table — add after dependencies = []
authors = [
  {name = "hahahuy"}
]

# New section after [project] table ends
[project.urls]
Homepage = "https://github.com/hahahuy/A2A-optimizer"
Repository = "https://github.com/hahahuy/A2A-optimizer"
"Bug Tracker" = "https://github.com/hahahuy/A2A-optimizer/issues"
```

- [ ] **Step 3: Exclude tests from package discovery**

Replace the existing `[tool.setuptools.packages.find]` block:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["ascp*"]
exclude = ["tests*"]
```

- [ ] **Step 4: Verify the full file looks correct**

Run:
```bash
type pyproject.toml
```

Expected: `build-backend = "setuptools.build_meta"`, `authors`, `[project.urls]`, and `exclude = ["tests*"]` all present.

- [ ] **Step 5: Verify build works**

```bash
pip install build
python -m build
```

Expected: `dist/ascp_optimizer-0.1.0-py3-none-any.whl` and `dist/ascp_optimizer-0.1.0.tar.gz` created. No errors.

- [ ] **Step 6: Verify tests still pass**

The project uses pytest (declared as `pytest>=7` in `[project.optional-dependencies.dev]`). Run:

```bash
python -m pytest -v
```

Expected: `99 passed`

- [ ] **Step 7: Clean up dist and commit**

```bash
rm -rf dist/ build/
git add pyproject.toml
git commit -m "chore: fix build backend, add project URLs and author"
```

---

### Task 2: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Replace `.gitignore` with full Python packaging exclusions**

Full content:

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

- [ ] **Step 2: Remove already-tracked `__pycache__` and `.pyc` files from git index**

```bash
git rm -r --cached "**/__pycache__" "**/*.pyc" 2>/dev/null || true
```

Expected: All `__pycache__` directories and `.pyc` files removed from tracking (they'll be ignored going forward).

- [ ] **Step 3: Verify `.pytest_cache/` and `__pycache__/` are now ignored**

```bash
git status
```

Expected: No `__pycache__/` or `.pyc` files listed as untracked or modified.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: full Python packaging .gitignore"
```

---

## Chunk 2: GitHub Actions + Publishing Docs

### Task 3: Create `ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflows directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

Full content:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: python -m pytest -v
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add test workflow on push and PR"
```

---

### Task 4: Create `publish.yml`

**Files:**
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Create `.github/workflows/publish.yml`**

Full content:

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

jobs:
  test:
    name: Test before publish
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: python -m pytest -v

  publish:
    name: Build and publish to PyPI
    needs: [test]
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build package
        run: |
          pip install build
          python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: add tag-triggered publish workflow with OIDC"
```

---

### Task 5: Create `docs/PUBLISHING.md`

**Files:**
- Create: `docs/PUBLISHING.md`

- [ ] **Step 1: Create `docs/PUBLISHING.md`**

Full content:

```markdown
# Publishing Guide

## One-Time Setup (pypi.org Trusted Publisher)

Before the first release, register a Trusted Publisher on pypi.org:

1. Go to **https://pypi.org/manage/account/publishing/**
2. Click **"Add a new pending publisher"**
3. Fill in:
   - **PyPI Project Name:** `ascp-optimizer`
   - **Owner:** `hahahuy`
   - **Repository name:** `A2A-optimizer`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
4. Save.

## One-Time Setup (GitHub Environment)

1. Go to **https://github.com/hahahuy/A2A-optimizer/settings/environments**
2. Click **New environment**
3. Name it `pypi`
4. Optionally add protection rules (e.g. required reviewers before publish)
5. Save.

## Releasing a New Version

```bash
# 1. Bump version in pyproject.toml
#    e.g. version = "0.2.0"

# 2. Commit the version bump
git add pyproject.toml
git commit -m "chore: bump version to 0.2.0"

# 3. Tag the release
git tag v0.2.0

# 4. Push commit and tag
git push && git push --tags
```

GitHub Actions will:
1. Run all 99 tests on Python 3.12
2. Build `dist/ascp_optimizer-0.2.0-py3-none-any.whl` and `.tar.gz`
3. Publish to PyPI via OIDC (no token needed)

The package will be live at **https://pypi.org/project/ascp-optimizer/** within ~30 seconds.

## Verify the Release

```bash
pip install ascp-optimizer==0.2.0
python -c "from ascp import SchemaRegistry; print('ok')"
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/PUBLISHING.md
git commit -m "docs: add publishing guide"
```

---

### Task 6: Push and verify CI

- [ ] **Step 1: Push all commits to GitHub**

```bash
git push
```

- [ ] **Step 2: Verify CI triggers**

Go to **https://github.com/hahahuy/A2A-optimizer/actions**

Expected: A new `CI` workflow run appears for the push to `master`. All 3 matrix jobs (Python 3.10, 3.11, 3.12) should pass.

- [ ] **Step 3: Confirm success criteria**

- [ ] `python -m build` produced valid `.whl` and `.tar.gz` (verified in Task 1)
- [ ] CI workflow runs and passes on push to `master`
- [ ] `docs/PUBLISHING.md` documents the one-time pypi.org + GitHub Environment setup
- [ ] `publish.yml` is ready and will trigger on next `v*` tag push

---

## After This Plan

**To publish `v0.1.0` to PyPI:**
1. Complete the one-time setup in `docs/PUBLISHING.md` (pypi.org Trusted Publisher + GitHub Environment)
2. Run:
   ```bash
   git tag v0.1.0
   git push --tags
   ```
3. Watch **https://github.com/hahahuy/A2A-optimizer/actions** for the publish job.
4. Verify at **https://pypi.org/project/ascp-optimizer/**
