# NextTable Frontend

This is the standalone React/Vite frontend for NextTable. It talks to the Django REST API under `/api/` using session-cookie authentication and CSRF protection.

## Local Development

Install dependencies:

```sh
npm install
```

Start the Django backend from the repository root:

```sh
uv run backend/manage.py runserver
```

Start the frontend from this directory:

```sh
npm run dev
```

Open:

```text
http://localhost:5173/
```

During development, `vite.config.ts` proxies `/api/*` to `http://localhost:8000`, so API calls are same-origin from the browser's point of view and Django's session cookie works without cross-site cookie setup.

## Scripts

```sh
npm run dev      # start Vite dev server on :5173
npm run build    # type-check and build production assets
npm run lint     # run oxlint
npm run preview  # preview the production build locally
```

## API Configuration

Local development usually needs no frontend env file because requests use relative `/api/*` URLs and the Vite proxy handles them.

For a deployed build, set:

```text
VITE_API_BASE_URL=https://your-api-domain.example
```

The backend must also allow the deployed frontend origin through `FRONTEND_ORIGINS`, which drives both `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.

## Routes

Public:

```text
/login
/check-in/:token
/check-in/status/:publicIdentifier
/check-in/status/:publicIdentifier/cancel
```

Staff or Manager:

```text
/staff
/staff/waitlist
/staff/tables
```

Manager only:

```text
/manager
/manager/workers
/manager/workers/new
/manager/workers/:userId
/manager/tables
/manager/tables/new
/manager/tables/:tableId
/manager/eta
/manager/eta/rules/new
/manager/eta/rules/:ruleId
/manager/eta/grace-period
```

## Auth Flow

On startup, `src/lib/AuthContext.tsx` calls:

```text
GET /api/auth/csrf/
GET /api/auth/me/
```

Unsafe requests send the `X-CSRFToken` header from the `csrftoken` cookie. All API requests use `credentials: "include"` so the Django session cookie is sent.

## Status

This frontend is the intended direction for NextTable. The old Django templates still exist temporarily until the React app has been manually verified and the cutover removes the legacy template layer.
