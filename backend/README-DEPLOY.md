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
   - `SECRET_KEY` — a long random string (the app refuses to start without one once
     `DEBUG=False`, rather than silently falling back to an insecure default)
   - `DEBUG` — leave unset, or set to `False` explicitly. Defaults to `False` if unset,
     but set it anyway so it's obvious from the dashboard that debug mode is off —
     `DEBUG=True` in production leaks tracebacks and settings (including this same
     `SECRET_KEY`/`DATABASE_URL`) to anyone who triggers a 500
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
   - `ADMINS` — e.g. `Admin One:admin1@example.com,Admin Two:admin2@example.com` — who
     gets emailed the traceback when an unhandled 500 happens (see `LOGGING` in
     `config/settings.py`). Requires the email vars above to actually be set too;
     without both, an unhandled 500 is only visible in Render's console output, which is
     lost on the next restart/redeploy
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

## 5. Scheduled tasks (optional)

Nothing in this project runs on a schedule by itself — there's no Celery/APScheduler
setup, just plain Django management commands meant to be triggered by whatever
scheduler your host (or OS) provides. The first two are safe to run daily and are
no-ops when there's nothing to do, so it's fine to schedule them even before you need
them:

- `python manage.py send_admin_digest` — emails admins (see `ADMINS` env var, step 3
  above) a summary of overdue B2B invoices and due-but-unpaid B2C installments — the
  same "needs attention" cards the dashboard shows, for admins who don't have it open.
- `python manage.py auto_archive_completed_students` — archives a student once **every**
  one of their enrollments is finished (none still ongoing, at least one completed) and
  30+ days have passed since the last class on a completed enrollment. A student with
  one course done but another still in progress is left alone. Archiving here is
  non-destructive (just a status flag — fully reversible from the Students page's
  "Unarchive" button), so this is low-risk to leave running unattended.
- `python manage.py backup_database` — emails every staff account with an email on
  file a full gzipped JSON dump of the database (Django's `dumpdata`, generated
  in-process — no `pg_dump` or other external tooling needed, so this works
  identically on Render, locally, or any host that runs this Django app). Excludes
  content types, permissions, sessions, and API auth tokens (all auto-regenerated
  and/or sensitive to leak in an email attachment). **Does not include uploaded media
  files** (course materials, client logos) — see the note above about those being
  ephemeral on Render's free tier already. Unlike the two commands above, this one is
  not a no-op — it sends an email with an attachment every time it runs, so a **weekly**
  schedule is a more sensible default than daily unless you want a backup email every
  single day. Complementary to (not a replacement for) Neon's own point-in-time
  recovery/branching, which needs no setup and is already available on your Neon plan.
  To restore a dump: `gunzip` the attachment, then `python manage.py loaddata <file>.json`
  against a target database with migrations already applied.

On Render specifically: "New +" → "Cron Job" (a separate service type from the web
service — **not free**, billed per run with a $1/month minimum), same
repo/`rootDir: backend`/environment as the web service, with the command as the
"Command" field and a schedule like `0 2 * * *` (daily at 2am UTC). Render Cron Job
schedules run in UTC regardless of the app's `TIME_ZONE` setting (`Asia/Kolkata`) —
adjust the hour if you want it to land at a specific local time. On any other host, or
for local use, point `cron` (Linux/macOS) or Windows Task Scheduler at the same
command instead.

`backup_database` specifically is instead wired up for free via
**`.github/workflows/db-backup.yml`** — a GitHub Actions scheduled workflow (`cron:
'30 1 * * 1'`, weekly Monday 7:00 AM IST — GitHub Actions cron always runs in UTC, so
that's written as Monday 1:30 AM UTC — plus a manual "Run workflow" button via
`workflow_dispatch`) that installs `backend/requirements.txt` and runs
`python manage.py backup_database` directly against the production Neon database. To
enable it, add these as repo secrets (GitHub repo → **Settings** → **Secrets and
variables** → **Actions** → **New repository secret**), using the same values as the
Render web service's own env vars (step 2 above) — except `SECRET_KEY`, which can be
any random string here since this workflow never serves HTTP requests:
`SECRET_KEY`, `DATABASE_URL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
`DEFAULT_FROM_EMAIL`. GitHub disables a scheduled workflow automatically after 60 days
with no commits to the repo — push something (or use "Run workflow" manually) to
re-enable it if that ever happens. The same free-workflow approach works just as well
for `send_admin_digest`/`auto_archive_completed_students` if you'd rather not pay for
a Render Cron Job for those either — just add another `on.schedule` workflow file
following the same pattern.

## Moving to a different host later

1. Set the same env vars (section 2, step 3 above) on the new host.
2. Point `DATABASE_URL` at the same Neon database — no data migration needed, Neon
   isn't tied to Render.
3. Redeploy the backend on the new host.
4. Repoint DNS (either the custom API domain, or `VITE_API_BASE_URL` + a frontend
   rebuild if you didn't set up a custom domain).
