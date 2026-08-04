# Deploying (Render + Neon + Vercel/Netlify)

The backend is host-agnostic — everything environment-specific is read from env vars
(`config/settings.py`), so this same setup works on any host that runs Python. Moving
hosts later means setting the same env vars on the new host and updating DNS — no code
changes needed.

## 1. Database — Neon

1. Create a free project at [neon.tech](https://neon.tech).
2. Copy the connection string it gives you (starts with `postgres://` or
   `postgresql://`) — this is your `DATABASE_URL`.

## 2. Backend — Render

1. Push this repo to GitHub (Render deploys from a Git repo).
2. In Render, "New +" → "Blueprint", point it at the repo — it'll pick up
   `render.yaml` at the repo root automatically and create the web service
   (`rootDir: backend`, free plan, build runs `collectstatic` + `migrate`, start runs
   `gunicorn`).
3. In the service's Environment tab, set:
   - `DATABASE_URL` — the Neon connection string from step 1
   - `ALLOWED_HOSTS` — your Render URL's host, e.g. `attendance-backend.onrender.com`
     (add your custom API domain here too once you have one, comma-separated)
   - `CORS_ALLOWED_ORIGINS` — your frontend's URL, e.g. `https://yourapp.vercel.app`
   - `CSRF_TRUSTED_ORIGINS` — same as above but include the scheme, e.g.
     `https://yourapp.vercel.app` (only matters for session-authenticated requests —
     mainly `/admin/` login)
   - `FRONTEND_URL` — your frontend's URL, used in password-reset email links
   - Email vars (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, etc.) if you want the
     "forgot password" email to actually send instead of just logging to Render's
     console
4. Deploy. First request after idle time will be slow (~30-50s) — free tier sleeps
   after inactivity; the Neon database itself is unaffected by this.
5. Create an admin user on the live database:
   `render shell` (or the dashboard's Shell tab) → `python manage.py createsuperuser`.

**Uploaded course-material files are lost on redeploy** — Render's free tier disk is
ephemeral. Accepted trade-off for now; revisit with S3/Cloudflare R2 storage later if
it matters.

## 3. Frontend — Vercel or Netlify

1. Point it at the `frontend/` directory of this repo, build command `npm run build`,
   output directory `dist`.
2. **Before triggering a build**, set the env var `VITE_API_BASE_URL` in the hosting
   platform's dashboard (Vercel: Project Settings → Environment Variables; Netlify:
   Site configuration → Environment variables) to your Render backend's URL (e.g.
   `https://attendance-backend.onrender.com`) — this is baked in at build time, so
   changing it later requires a redeploy of the frontend (not just a settings change).
   `vite build` refuses to run at all if this isn't set (see `vite.config.js`), rather
   than silently shipping a bundle that calls `undefined/api/...`.
3. Deploy.

## 4. Optional: custom domain

Put the backend behind a subdomain (e.g. `api.yourapp.com`) from the start. Then a
future host migration is just repointing that one DNS record — the frontend's
`VITE_API_BASE_URL` never needs to change, so no frontend rebuild either.

## Moving to a different host later

1. Set the same env vars (section 2, step 3 above) on the new host.
2. Point `DATABASE_URL` at the same Neon database — no data migration needed, Neon
   isn't tied to Render.
3. Redeploy the backend on the new host.
4. Repoint DNS (either the custom API domain, or `VITE_API_BASE_URL` + a frontend
   rebuild if you didn't set up a custom domain).
