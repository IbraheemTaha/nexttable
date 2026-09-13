# Local Development Workflow

This document describes how to set up and run NextTable locally. It reflects
the actual tooling in this repository as of this writing: Python dependency
management via [uv](https://docs.astral.sh/uv/), Django 5.0.9, SQLite, and
the Tailwind standalone CLI for CSS (see `docs/setup/tailwind.md`).

For the production/pre-deployment checklist, see
[`docs/production-checklist.md`](./production-checklist.md) - keep the two
separate.

## Prerequisites

- Python (version pinned in `.python-version`, currently 3.12) - matches
  `requires-python = ">=3.12"` in `pyproject.toml`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for
  dependency management and running commands. This project is uv-only -
  there is no `requirements.txt`/pip path.
- The Tailwind standalone CLI binary, only if you plan to change templates
  and need to rebuild CSS - see `docs/setup/tailwind.md` for download
  instructions. The compiled stylesheet (`frontend/static/css/app.css`) is committed,
  so this is not required just to run the app.

## 1. Install dependencies

```sh
uv sync
```

This creates/updates the project's `.venv` from `uv.lock`, installing both
the runtime dependencies (`django`, `python-dotenv`) and the dev dependency
group (`pytest`, `pytest-django`) declared in `pyproject.toml`.

## 2. Configure environment variables

Copy the example env file and adjust as needed:

```sh
cp .env.example .env
```

`backend/config/settings.py` loads `.env` via `python-dotenv` at startup
(`load_dotenv(REPO_ROOT / '.env')`). If no `.env` file exists at all, the app
still runs locally using a clearly-labeled insecure fallback `SECRET_KEY`, so
`.env` is optional for local development. The variables it recognizes:

| Variable        | Local default (if unset)                          | Notes |
|-----------------|----------------------------------------------------|-------|
| `SECRET_KEY`    | Hardcoded dev-only fallback string                  | Any non-empty string works locally; never reuse the fallback anywhere else. |
| `DEBUG`         | `True`                                              | String comparison against `'True'`; set to `False` for anything non-local. |
| `ALLOWED_HOSTS` | empty list                                          | Comma-separated hostnames, e.g. `example.com,www.example.com`. Empty is fine locally with `DEBUG=True`. |
| `BACKEND_PORT`  | `8000`                                              | Port the Django dev server binds to. Only actually read by `scripts/dev-backend.sh` and by the frontend's Vite proxy (`frontend/vite.config.ts`) - change it here rather than passing a port to `runserver` directly. |

## 3. Run migrations

```sh
uv run backend/manage.py migrate
```

(Or, without uv, with the virtualenv activated: `python backend/manage.py
migrate`.) This creates/updates `db.sqlite3` per the `default` database
configuration in `backend/config/settings.py` (SQLite, file-based, at the
repo root).

## 4. Seed local demo data (optional but recommended)

The `seed_demo_data` management command (added for issue #29) populates the
local database with realistic sample data for demos and manual testing:
restaurant settings, staff/manager user accounts, ETA rules, and tables. It
is safe to run multiple times (it uses `get_or_create`/`update_or_create`
throughout).

```sh
uv run backend/manage.py seed_demo_data
```

This creates two local-only accounts if they do not already exist:

- `staff_demo` (role: staff)
- `manager_demo` (role: manager)

Both use the password `devpassword123`, printed to the console when the
command creates them. **These credentials are for local development only -
never use them, or this command, against a production database.**

## 5. Create an admin/superuser account (optional)

Only needed if you want access to the Django admin (`/admin/`) locally:

```sh
uv run backend/manage.py createsuperuser
```

## 6. Start the development server

```sh
./scripts/dev-backend.sh
```

This reads `BACKEND_PORT` from `.env` (default `8000`) and starts
`manage.py runserver` on that port - use it instead of calling
`manage.py runserver` directly so the port stays in sync with the frontend's
Vite proxy. The app is served at http://127.0.0.1:8000/ by default. Static files (including the
compiled Tailwind stylesheet at `frontend/static/css/app.css`) are served directly by
`runserver` in development via `STATICFILES_DIRS`.

## 7. Run the test suite

Tests use `pytest` + `pytest-django` (configured in `pyproject.toml`:
`DJANGO_SETTINGS_MODULE = "config.settings"`, test files matched as
`tests.py`, `test_*.py`, `*_tests.py`). Tests currently live in
`backend/restaurant/tests.py` and `backend/config/tests.py`.

```sh
uv run pytest
```

Before writing new tests, read `docs/testing-guidelines.md` per this
project's contribution rules (`AGENTS.md`).

## Rebuilding CSS after template changes (optional)

If you edit any template's class names or `tailwind.config.js`, rebuild the
compiled stylesheet (see `docs/setup/tailwind.md` for full setup):

```sh
(cd frontend && ./bin/tailwindcss -i ./static/src/input.css -o ./static/css/app.css --minify)
```

Commit the resulting `frontend/static/css/app.css` alongside your template changes -
it is checked into the repo so the app runs without requiring the Tailwind
binary on every clone or CI run.

## Quick reference

```sh
uv sync                              # install/update dependencies
cp .env.example .env                 # local env config (optional)
uv run backend/manage.py migrate             # apply migrations
uv run backend/manage.py seed_demo_data      # local demo data (staff_demo/manager_demo)
uv run backend/manage.py createsuperuser     # optional: admin access
./scripts/dev-backend.sh                     # start dev server (reads BACKEND_PORT)
uv run pytest                        # run tests
```
