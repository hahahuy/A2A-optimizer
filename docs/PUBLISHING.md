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
1. Run all 99 tests on Python 3.10, 3.11, and 3.12
2. Build `dist/ascp_optimizer-0.2.0-py3-none-any.whl` and `.tar.gz`
3. Publish to PyPI via OIDC (no token needed)

The package will be live at **https://pypi.org/project/ascp-optimizer/** within ~30 seconds.

## Verify the Release

```bash
pip install ascp-optimizer==0.2.0
python -c "from ascp import SchemaRegistry; print('ok')"
```
