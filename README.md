# TaskFlow — a lightweight Trello-style task manager

Built with **Django** and **PostgreSQL**. The UI is in **French**; this README stays in English since it's for you, the developer, not the app's users. Two roles:

- **Admin** — creates tasks, assigns them to a team member, manages users, verifies/finalizes tasks, and sees the full dashboard/board.
- **Member (Membre)** — sees only the tasks assigned to them, and can move them between **À faire → En cours → À vérifier**. Once a task reaches À vérifier, it's locked — only an admin can move it from there to Terminé (or anywhere else). A member can never set a task to Terminé themselves.

## Features

- **Dashboard** (Tableau de bord) — task counts, a status doughnut chart, a priority bar chart, team workload (admin), recent tasks, and a date-range filter (Aujourd'hui / Cette semaine / Ce mois-ci / a custom range — defaults to the current week).
- **Task board** (Tableau des tâches) — a Trello-style Kanban board with four columns (À faire, En cours, À vérifier, Terminé), drag-and-drop cards sorted by priority (Critique first), a hover lift effect, and confirmation prompts before submitting a task for verification or marking it Terminé. Falls back to a plain dropdown + button if JavaScript is off.
- **Task detail page** — click anywhere on a card to open it. Comments and file attachments live here; both admins and the assigned member can post comments and upload/download files (JPG, JPEG, PNG, PDF, DOC/DOCX, XLS/XLSX, TXT, CSV, or SQL — max 10MB each). Anyone can delete their own comment/upload; admins can delete any.
- **User management** (Utilisateurs) — admin-only CRUD for users, plus a "reset password" action. Password strength rules are intentionally disabled — any password, including something like `123`, is accepted.
- Role-based permissions enforced on every view, not just hidden in the UI.

## Project layout

```
task_manager/
├── manage.py
├── requirements.txt
├── .env.example
├── task_manager/     # settings, root urls
├── accounts/         # custom User model (email/name/role), login, user management
├── tasks/            # Task/Comment/Attachment models, Kanban board, task CRUD
├── dashboard/         # reporting home page + date-range filter
├── templates/         # base.html (shared layout)
└── static/            # css/style.css, js/board.js, js/dashboard.js, js/file-input.js
```

## 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally (or reachable over the network)

## 2. Set up the database

```sql
CREATE DATABASE task_manager;
CREATE USER task_manager_user WITH PASSWORD 'change-me';
GRANT ALL PRIVILEGES ON DATABASE task_manager TO task_manager_user;
```
(Skip this and use your existing `postgres` user/DB if you prefer — just update `.env` to match.)

## 3. Install and configure

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env with your real DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT
```

## 4. Create the database schema

```bash
python manage.py makemigrations accounts tasks
python manage.py migrate
```

> **Upgrading an existing install?** The `tasks` app now includes `Comment` and
> `Attachment` models. Run the two commands above again — Django will detect
> them and generate a new migration automatically, no manual SQL needed.
>
> **Already had attachments working and just pulled the file-type restriction?**
> Run `makemigrations`/`migrate` again — it'll generate a small, safe `AlterField`
> migration for `Attachment.file` (allowed extensions changed). It doesn't touch
> any existing data, and there's no need to drop the database for this one.
>
> **Pulling the French/À vérifier update?** This one changed status choices,
> priority/role choices, and added `verbose_name` to several fields — all of
> which Django tracks as model state. Run `makemigrations`/`migrate` one more
> time; it's another safe, no-data-loss migration (existing tasks keep their
> current status — `TO_VERIFY` is just a new option going forward, nothing
> gets moved into it automatically).

## 5. Create your first admin account

```bash
python manage.py createsuperuser
```

You'll be prompted for **email**, **name**, and **password**. This account is automatically
given the `Admin` role (it's what `UserManager.create_superuser` sets), so it can create tasks,
assign them, and manage other users right away.

## 6. Run it

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` and sign in. New teammates should be added from **Users → New user**
(this is the only way regular Member accounts get created — there's no public sign-up page, by design).

## How the permissions work

| Action | Admin | Member |
|---|---|---|
| Create / edit / delete tasks | ✅ | ❌ |
| Assign a task to someone | ✅ | ❌ |
| Move their own tasks between À faire ↔ En cours ↔ À vérifier | ✅ | ✅ (own tasks only, and only before they reach À vérifier) |
| Move a task out of À vérifier, or set/change Terminé | ✅ | ❌ (locked — admin-only from that point on) |
| See all tasks / all users' workload | ✅ | ❌ (sees only their own tasks) |
| Manage users (create/edit/delete/reset password) | ✅ | ❌ |

This is enforced in `accounts/mixins.py` (`AdminRequiredMixin`) and directly inside
`tasks/views.py::update_task_status`, not just by hiding buttons in the template.

## Notes & things you may want to customize

- **Django admin** at `/admin/` is also wired up (`accounts/admin.py`, `tasks/admin.py`) if you want
  a quick way to poke at the data — the in-app **Users** and **Task Board** pages are the intended UI though.
- Charts on the dashboard use [Chart.js](https://www.chartjs.org/) from a CDN — swap `dashboard/templates/dashboard/home.html`'s script tag for a local copy if you need to run fully offline.
- Drag-and-drop in `static/js/board.js` is plain HTML5 drag/drop + `fetch()` — no frontend framework or build step required.
- To add more fields later (a due date, labels, etc.), extend the `Task` model in `tasks/models.py`
  and re-run `makemigrations`/`migrate`.
- **Attachments are stored on disk** under `media/task_attachments/<task_id>/…` (path set by `MEDIA_ROOT`
  in `settings.py`). Files are deliberately **not** served directly under `/media/` — every download goes
  through `tasks.views.download_attachment`, which checks the requester can access that task first. If you
  deploy behind Nginx/Apache, you don't need a `media` alias for this reason; just make sure the `media/`
  folder is writable by the app process.

### Fixed since the first version

- **Card text overflow** — long unbroken strings (like a description with no spaces) could push past the
  card's edge. Fixed with `overflow-wrap`/`word-break` on the relevant text elements and `min-width: 0`
  on the flex containers that hold them (`static/css/style.css`).
- **Drag-and-drop "Cannot read properties of null" popup** — dropping a card triggered a race condition:
  the browser's native `dragend` event cleared the script's "currently dragged card" reference before the
  save request finished, so the follow-up code crashed instead of moving the card. Fixed by capturing the
  card into a local variable at the moment of drop (`static/js/board.js`).
