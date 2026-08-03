# Attendance App — Backend (Phase 1)

Django + Django REST Framework backend for the Apex Binary attendance/payout system.

## Setup

```bash
cd backend
python -m venv ../venv          # already created
source ../venv/Scripts/activate # Windows Git Bash; use ../venv/Scripts/Activate.ps1 for PowerShell
pip install -r requirements.txt
cp .env.example .env            # adjust SECRET_KEY etc. for real deployments
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Admin UI: http://127.0.0.1:8000/admin/

## What's set up (Phase 1)

- Django project `config` with apps: `students`, `trainers`, `clients`, `courses`, `enrollments`, `attendance`, `billing`
- All models from the plan, with migrations applied
- Django admin registered for every model (usable as a working backend UI before the React frontend exists)
- Auth: Django's built-in `User` model + DRF `TokenAuthentication`/`SessionAuthentication`
  - `POST /api/auth/login/` — body `{"username", "password"}` → returns token + role (`admin` if no linked Trainer, `trainer` otherwise)
  - `POST /api/auth/logout/` — deletes the caller's token (requires `Authorization: Token <key>` header)
- `Trainer.trainer_id` and `Student.student_id` auto-generate as `TRN-<year>-NNN` / `STU-<year>-NNN` on save

## Not yet built (later phases)

- CRUD API endpoints for Students/Trainers/Clients/Courses/Enrollments/Rates (Phase 2)
- Trainer-scoped attendance marking + permission classes (Phase 2)
- Billing cycle generation + payout calculation command (Phase 3)
- React frontend (Phase 4)
- CSV report exports (Phase 5)
