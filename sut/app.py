"""TaskBoard SUT: users, projects, members, tasks with a status state machine.

Seeded bugs are switched by SUT_BUGS (see sut/bugs.py). Every injection point is an
`is_enabled("Bxx")` call in this file.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sut.bugs import enabled_bugs, is_enabled

STATIC_DIR = Path(__file__).parent / "static"
SEED_USERS = ("alice", "bob", "carol", "dave")
STATUSES = ("todo", "in_progress", "done")
TRANSITIONS = {("todo", "in_progress"), ("in_progress", "done"), ("in_progress", "todo")}
TITLE_MAX = 100
PRIORITY_MIN, PRIORITY_MAX = 1, 5
LIMIT_DEFAULT, LIMIT_MAX = 20, 100

SCHEMA = f"""
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE project_members (
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND {TITLE_MAX}),
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    priority INTEGER NOT NULL DEFAULT 3,
    assignee_id INTEGER REFERENCES users(id),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Database:
    """One shared SQLite connection guarded by a lock (works for :memory: across threads)."""

    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.executemany("INSERT INTO users (username) VALUES (?)", [(u,) for u in SEED_USERS])

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            return self.conn.execute(sql, params).lastrowid


class ProjectIn(BaseModel):
    name: str


class MemberIn(BaseModel):
    user_id: int


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 3


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    assignee_id: int | None = None


class TransitionIn(BaseModel):
    to: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _validation_error(field: str, msg: str) -> HTTPException:
    return HTTPException(422, detail=[{"loc": ["body", field], "msg": msg}])


def _validate_title(title: str) -> None:
    if not title.strip():
        raise _validation_error("title", "title must not be empty")
    # B04: the length check is skipped, so the DB CHECK constraint raises and the request 500s.
    if len(title) > TITLE_MAX and not is_enabled("B04"):
        raise _validation_error("title", f"title must be at most {TITLE_MAX} characters")


def _validate_priority(priority: int) -> None:
    # B06: upper bound is exclusive, so the valid value 5 is rejected.
    if is_enabled("B06"):
        valid = PRIORITY_MIN <= priority < PRIORITY_MAX
    else:
        valid = PRIORITY_MIN <= priority <= PRIORITY_MAX
    if not valid:
        raise _validation_error("priority", f"priority must be between {PRIORITY_MIN} and {PRIORITY_MAX}")


def _task_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def create_app(db_path: str | None = None) -> FastAPI:
    enabled_bugs()  # fail fast on unknown ids in SUT_BUGS
    db = Database(db_path or os.environ.get("SUT_DB", ":memory:"))
    app = FastAPI(title="TaskBoard SUT")

    def current_user(x_user: str | None = Header(default=None)) -> sqlite3.Row:
        if not x_user:
            raise HTTPException(401, "missing X-User header")
        user = db.one("SELECT * FROM users WHERE username = ?", (x_user,))
        if user is None:
            raise HTTPException(401, "unknown user")
        return user

    def get_project(pid: int) -> sqlite3.Row:
        project = db.one("SELECT * FROM projects WHERE id = ?", (pid,))
        if project is None:
            raise HTTPException(404, "project not found")
        return project

    def get_task(tid: int) -> sqlite3.Row:
        task = db.one("SELECT * FROM tasks WHERE id = ?", (tid,))
        if task is None:
            raise HTTPException(404, "task not found")
        return task

    def is_member(pid: int, uid: int) -> bool:
        return db.one("SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?", (pid, uid)) is not None

    def require_member(pid: int, uid: int) -> None:
        if not is_member(pid, uid):
            raise HTTPException(403, "not a project member")

    # ---------------------------------------------------------------- meta / UI

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        # B10: task titles are rendered as HTML instead of text.
        render_title = "titleEl.innerHTML = t.title;" if is_enabled("B10") else "titleEl.textContent = t.title;"
        # B05: the list is not reloaded after a successful create.
        after_create = "form.reset();" if is_enabled("B05") else "form.reset();\n      await loadTasks();"
        return html.replace("/*@RENDER_TITLE@*/", render_title).replace("/*@AFTER_CREATE@*/", after_create)

    @app.get("/api/users")
    def list_users() -> list[dict[str, Any]]:
        return [dict(r) for r in db.query("SELECT id, username FROM users ORDER BY id")]

    # ---------------------------------------------------------------- projects

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectIn, user=Depends(current_user)) -> dict[str, Any]:
        name = body.name.strip()
        if not name or len(name) > 100:
            raise _validation_error("name", "name must be 1-100 characters")
        pid = db.execute("INSERT INTO projects (name, owner_id) VALUES (?, ?)", (name, user["id"]))
        db.execute("INSERT INTO project_members VALUES (?, ?, 'owner')", (pid, user["id"]))
        return dict(get_project(pid))

    @app.get("/api/projects")
    def list_projects(user=Depends(current_user)) -> list[dict[str, Any]]:
        rows = db.query(
            "SELECT p.* FROM projects p JOIN project_members m ON m.project_id = p.id "
            "WHERE m.user_id = ? ORDER BY p.id",
            (user["id"],),
        )
        return [dict(r) for r in rows]

    @app.get("/api/projects/{pid}")
    def read_project(pid: int, user=Depends(current_user)) -> dict[str, Any]:
        project = get_project(pid)
        require_member(pid, user["id"])
        members = db.query(
            "SELECT u.id, u.username, m.role FROM project_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.project_id = ? ORDER BY u.id",
            (pid,),
        )
        return {**dict(project), "members": [dict(m) for m in members]}

    @app.post("/api/projects/{pid}/members", status_code=201)
    def add_member(pid: int, body: MemberIn, user=Depends(current_user)) -> dict[str, Any]:
        project = get_project(pid)
        if project["owner_id"] != user["id"]:
            raise HTTPException(403, "only the project owner can add members")
        if db.one("SELECT 1 FROM users WHERE id = ?", (body.user_id,)) is None:
            raise _validation_error("user_id", "unknown user")
        if is_member(pid, body.user_id):
            raise HTTPException(409, "already a member")
        db.execute("INSERT INTO project_members VALUES (?, ?, 'member')", (pid, body.user_id))
        return {"project_id": pid, "user_id": body.user_id, "role": "member"}

    # ---------------------------------------------------------------- tasks

    @app.get("/api/projects/{pid}/tasks")
    def list_tasks(
        pid: int,
        status: str | None = None,
        q: str | None = None,
        limit: int = LIMIT_DEFAULT,
        offset: int = 0,
        user=Depends(current_user),
    ) -> dict[str, Any]:
        get_project(pid)
        require_member(pid, user["id"])
        if not 1 <= limit <= LIMIT_MAX:
            raise HTTPException(422, f"limit must be between 1 and {LIMIT_MAX}")
        if offset < 0:
            raise HTTPException(422, "offset must be >= 0")
        sql, params = "SELECT * FROM tasks WHERE project_id = ?", [pid]
        if status is not None:
            if status not in STATUSES:
                raise HTTPException(422, f"status must be one of {STATUSES}")
            sql += " AND status = ?"
            params.append(status)
        if q:
            # B09: instr() is case-sensitive; LIKE is case-insensitive for ASCII.
            if is_enabled("B09"):
                sql += " AND instr(title, ?) > 0"
                params.append(q)
            else:
                escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql += " AND title LIKE ? ESCAPE '\\'"
                params.append(f"%{escaped}%")
        rows = db.query(sql + " ORDER BY id", tuple(params))
        total = len(rows)
        end = offset + limit
        # B01: when paging past the first page reaches the end, the end index is off by one.
        if is_enabled("B01") and offset > 0 and end >= total:
            end = total - 1
        return {"items": [_task_dict(r) for r in rows[offset:end]], "total": total, "limit": limit, "offset": offset}

    @app.post("/api/projects/{pid}/tasks", status_code=201)
    def create_task(pid: int, body: TaskCreate, user=Depends(current_user)) -> dict[str, Any]:
        get_project(pid)
        require_member(pid, user["id"])
        _validate_title(body.title)
        _validate_priority(body.priority)
        now = _now()
        tid = db.execute(
            "INSERT INTO tasks (project_id, title, description, priority, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, body.title, body.description, body.priority, user["id"], now, now),
        )
        return _task_dict(get_task(tid))

    @app.get("/api/tasks/{tid}")
    def read_task(tid: int, user=Depends(current_user)) -> dict[str, Any]:
        task = get_task(tid)
        # B03: membership check skipped on task detail.
        if not is_enabled("B03"):
            require_member(task["project_id"], user["id"])
        return _task_dict(task)

    @app.patch("/api/tasks/{tid}")
    def update_task(tid: int, body: TaskPatch, user=Depends(current_user)) -> dict[str, Any]:
        task = get_task(tid)
        require_member(task["project_id"], user["id"])
        changes = body.model_dump(exclude_unset=True)
        if "title" in changes:
            if changes["title"] is None:
                raise _validation_error("title", "title must not be null")
            _validate_title(changes["title"])
        if "priority" in changes:
            if changes["priority"] is None:
                raise _validation_error("priority", "priority must not be null")
            _validate_priority(changes["priority"])
        if "description" in changes and changes["description"] is None:
            changes["description"] = ""
        if changes.get("assignee_id") is not None:
            if db.one("SELECT 1 FROM users WHERE id = ?", (changes["assignee_id"],)) is None:
                raise _validation_error("assignee_id", "unknown user")
            # B08: assignee is not required to be a project member.
            if not is_enabled("B08") and not is_member(task["project_id"], changes["assignee_id"]):
                raise _validation_error("assignee_id", "assignee must be a project member")
        if changes:
            cols = ", ".join(f"{k} = ?" for k in changes)
            db.execute(f"UPDATE tasks SET {cols}, updated_at = ? WHERE id = ?", (*changes.values(), _now(), tid))
        return _task_dict(get_task(tid))

    @app.post("/api/tasks/{tid}/transition")
    def transition_task(tid: int, body: TransitionIn, user=Depends(current_user)) -> dict[str, Any]:
        task = get_task(tid)
        require_member(task["project_id"], user["id"])
        if body.to not in STATUSES:
            raise _validation_error("to", f"status must be one of {STATUSES}")
        allowed = set(TRANSITIONS)
        # B02: done is no longer terminal.
        if is_enabled("B02"):
            allowed.add(("done", "in_progress"))
        if (task["status"], body.to) not in allowed:
            raise HTTPException(409, f"cannot transition from {task['status']} to {body.to}")
        db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (body.to, _now(), tid))
        return _task_dict(get_task(tid))

    @app.delete("/api/tasks/{tid}", status_code=204)
    def delete_task(tid: int, user=Depends(current_user)) -> Response:
        task = get_task(tid)
        require_member(task["project_id"], user["id"])
        project = get_project(task["project_id"])
        may_delete = user["id"] in (project["owner_id"], task["created_by"])
        # B07: any project member may delete.
        if not may_delete and not is_enabled("B07"):
            raise HTTPException(403, "only the project owner or the task creator can delete")
        db.execute("DELETE FROM tasks WHERE id = ?", (tid,))
        return Response(status_code=204)

    return app


app = create_app()
