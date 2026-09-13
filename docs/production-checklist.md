# Pre-Production Checklist

This is a checklist of conditions that must be true before running NextTable
anywhere other than a developer's own machine. It is **not** a guide to any
specific hosting platform, infrastructure setup, or CI/CD pipeline - it only
states what must hold true regardless of where the app is deployed. For the
day-to-day local dev workflow, see [`docs/development.md`](./development.md).

Every item below is checked against the current codebase
(`backend/config/settings.py`, `backend/manage.py`, `pyproject.toml`) - not
generic Django defaults.

## Environment variables

`backend/config/settings.py` reads these from the environment (via `python-dotenv`
locally, or real environment variables in a deployed environment):

- [ ] `SECRET_KEY` is set to a real, unique, secret value. The code falls
      back to a hardcoded string
      (`django-insecure-dev-only-fallback-key-do-not-use-in-production`) if
      `SECRET_KEY` is unset - this fallback must never be in effect outside
      local development.
- [ ] `DEBUG` is set to `False`. The code defaults to `True` when unset
      (`os.environ.get('DEBUG', 'True') == 'True'`), so this must be set
      explicitly - it will not default safely.
- [ ] `ALLOWED_HOSTS` is set to a comma-separated list of the actual
      hostname(s) the app will be served under (e.g.
      `example.com,www.example.com`). It defaults to an empty list when
      unset, which combined with `DEBUG=False` will make Django reject all
      requests with `DisallowedHost`.

## Dependencies

- [ ] Dependencies are installed from the locked/pinned versions -
      `uv sync --frozen` (uses `uv.lock`) - not resolved fresh against
      latest releases.

## Database and migrations

- [ ] All migrations have been applied to the target database:
      `backend/manage.py migrate`.
- [ ] The database is not the default SQLite file
      (`backend/config/settings.py`'s `DATABASES['default']` points at
      `REPO_ROOT / 'db.sqlite3'`) unless a single-file SQLite database is a
      deliberate, accepted choice for the deployment target - SQLite has no
      built-in concurrent-write story and the file must live on persistent,
      backed-up storage if used.
- [ ] The `seed_demo_data` management command (see `docs/development.md`)
      has **not** been run against this database, and the `staff_demo` /
      `manager_demo` accounts it creates (password `devpassword123`) do not
      exist in it. That command is explicitly local-development-only.

## Static files

- [ ] `backend/manage.py collectstatic` has been run, gathering static assets
      (including the compiled Tailwind stylesheet) into `STATIC_ROOT`
      (`frontend/staticfiles/` per `backend/config/settings.py`).
- [ ] The compiled `frontend/static/css/app.css` reflects the current templates - if
      templates changed since the last commit that touched CSS, it has been
      rebuilt per `docs/setup/tailwind.md` and collected.
- [ ] Something other than Django's development server is serving the
      contents of `STATIC_ROOT` (Django's `runserver` static handling is not
      intended for production use, and this app has no `django.contrib
      .staticfiles` production serving configured beyond the dev default).

## Admin / superuser accounts

- [ ] At least one real superuser account exists for the deployed database,
      created with `backend/manage.py createsuperuser`, using a strong, unique
      password - not `devpassword123` or any other credential from
      `seed_demo_data`.
- [ ] Staff/manager `WorkerProfile` accounts needed for actual restaurant
      staff have been created deliberately (not via `seed_demo_data`), with
      real credentials communicated securely.

## HTTPS

- [ ] The app is served over HTTPS only. `backend/config/settings.py` does not
      currently set any of Django's HTTPS-enforcement settings
      (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
      `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, etc.), so HTTPS
      termination and enforcement must be handled by the deployment
      environment, or these settings must be added, before going live -
      otherwise session and CSRF cookies can be transmitted over plain HTTP.

## Backups

- [ ] There is a backup plan for the production database file/instance,
      taken on a schedule appropriate to how often data changes (waitlist
      and table state changes constantly during service hours).
- [ ] Backups have been tested for restore, not just creation.
- [ ] If using the default SQLite database, backup means copying/snapshotting
      the actual `db.sqlite3` file (and doing so safely with respect to
      concurrent writes) - there is no separate database server to back up.

## Out of scope for this checklist

Per the originating issue, this document intentionally does not cover:

- Which hosting/deployment platform to use
- CI/CD pipeline setup
- Infrastructure provisioning (servers, containers, load balancers, etc.)

Those are separate decisions to be made and documented elsewhere when
needed.
