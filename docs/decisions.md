# Decisions

Record of significant technical decisions for NextTable, with reasoning,
so they aren't silently reopened later. Newest entries at the top.

---

## 2026-09-13 - Data access: Django ORM directly, via per-app service functions

**Decided by:** Ibraheem Taha (Software Engineer), issue #1

**Decision:** Persistence will use Django's built-in ORM directly against
SQLite, not SQLAlchemy and not a separate repository/data-access-object
abstraction layer. Business logic that touches multiple models or enforces
rules (e.g. queue priority, table matching) should live in plain Python
functions in a `services.py` (or similar) module per app, which themselves
call the Django ORM - but the ORM itself is not hidden behind an interface.

**Reasoning:**

- The stack (docs/plan.md) is Django end-to-end: Django templates, Django's
  auth, and Django's admin. All of these are built to work with Django
  models. Introducing SQLAlchemy alongside Django ORM would mean either
  running two persistence layers side by side, or losing `django.contrib.admin`,
  migrations, and `contrib.auth` - a large amount of built-in functionality
  the MVP plan (single restaurant, staff/manager accounts, simple CRUD-heavy
  waitlist flows) benefits from directly.
- The MVP is intentionally small (docs/plan.md): one restaurant, no
  multi-tenancy, simple state machines for guests/tables. A full
  repository/data-access-service abstraction (hiding the ORM behind
  interfaces so it could be swapped later) adds indirection the project
  doesn't need yet and isn't asking for - YAGNI. If the project ever
  outgrows the Django ORM, that's a much bigger, separate decision to
  revisit here.
- Business logic (queue priority ranking, table-matching, wait estimation)
  is still kept out of views/templates and out of models' `save()` methods
  by convention: each app groups this logic into plain functions (e.g.
  `waitlist/services.py`) that take/return plain Python values or model
  instances and call the ORM directly. This keeps logic unit-testable and
  views thin, without requiring a full data-access abstraction layer.
- This task does not add any app models or service modules - that starts
  in #3, #6, and #8, once this decision is in place.

**Alternatives considered:**

- *SQLAlchemy*: more powerful/flexible query building and a
  framework-independent data layer, but duplicates what Django's ORM
  already does here, loses tight integration with `contrib.admin`/migrations/
  `contrib.auth`, and adds a second ORM's worth of learning/maintenance cost
  for no MVP-scoped benefit.
- *Isolated data-access service layer (repository pattern) hiding the ORM
  behind an interface*: gives a clean seam for swapping persistence
  technology later, but for a single-restaurant MVP with a fixed SQLite/
  Django stack, this is speculative complexity. The "keep business logic in
  service functions" half of this pattern is adopted (see above); the
  "hide the ORM behind a swappable interface" half is not.

**Reopening this decision:** If a future need (e.g. a second persistence
backend, or splitting out a service with a different data store) makes this
worth reconsidering, update this entry (or add a new dated entry) before
changing the approach - do not reopen it silently in an unrelated issue.
