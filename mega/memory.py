"""
MEGA-AI  |  حافظه و یادگیری
------------------------------------------------
هر اجرا در SQLite ذخیره می‌شود: پرامپت، پاسخ هر خبره، امتیاز داور، نتیجه‌ی نهایی.
از دل این داده‌ها «جدول امتیاز مدل‌ها» ساخته می‌شود و انتخاب خبرگانِ اجراهای بعدی
هوشمندانه‌تر می‌شود (مدلی که در یک نوع کار بهتر بوده، بیشتر دعوت می‌شود).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT, created REAL, prompt TEXT, task_type TEXT,
  mode TEXT, final TEXT, meta TEXT
);
CREATE TABLE IF NOT EXISTS stages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER, role TEXT, model TEXT, provider TEXT,
  text TEXT, seconds REAL, ok INTEGER, tokens INTEGER, created REAL
);
CREATE TABLE IF NOT EXISTS scores (
  task_type TEXT, model TEXT, runs INTEGER DEFAULT 0, points REAL DEFAULT 0,
  wins INTEGER DEFAULT 0, updated REAL, PRIMARY KEY (task_type, model)
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, title TEXT, created REAL, updated REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created);
"""


class Memory:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        return c

    # ------------------------------------------------------------------ نشست‌ها
    def ensure_session(self, sid: str, title: str = "") -> None:
        now = time.time()
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO sessions(id,title,created,updated) VALUES(?,?,?,?)",
                      (sid, title or "نشست جدید", now, now))
            if title:
                c.execute("UPDATE sessions SET title=?, updated=? WHERE id=?", (title, now, sid))

    def sessions(self, limit: int = 30) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM sessions ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def history(self, session_id: str, limit: int = 8) -> list[dict]:
        """چند تبادل آخر همان نشست، برای اینکه سیستم مکالمه را به یاد داشته باشد."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT prompt, final FROM runs WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit)).fetchall()
        return [{"prompt": r["prompt"], "final": r["final"]} for r in reversed(rows)]

    # ------------------------------------------------------------------ ذخیره
    def start_run(self, session_id: str, prompt: str, task_type: str, mode: str, meta: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO runs(session_id,created,prompt,task_type,mode,final,meta) VALUES(?,?,?,?,?,?,?)",
                (session_id, time.time(), prompt, task_type, mode, "", json.dumps(meta, ensure_ascii=False)))
            return int(cur.lastrowid or 0)

    def add_stage(self, run_id: int, role: str, model: str, provider: str,
                  text: str, seconds: float, ok: bool, tokens: int = 0) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO stages(run_id,role,model,provider,text,seconds,ok,tokens,created)"
                      " VALUES(?,?,?,?,?,?,?,?,?)",
                      (run_id, role, model, provider, text, seconds, int(ok), tokens, time.time()))

    def finish_run(self, run_id: int, final: str, meta: Optional[dict] = None) -> None:
        with self._conn() as c:
            if meta is not None:
                c.execute("UPDATE runs SET final=?, meta=? WHERE id=?",
                          (final, json.dumps(meta, ensure_ascii=False), run_id))
            else:
                c.execute("UPDATE runs SET final=? WHERE id=?", (final, run_id))

    # ------------------------------------------------------------------ یادگیری
    def record_scores(self, task_type: str, scores: dict[str, float], count_win: bool = True) -> None:
        """امتیازهای داور (۰..۱۰) را در جدول یادگیری انبار می‌کند."""
        if not scores:
            return
        best = max(scores.values()) if scores else 0
        with self._conn() as c:
            for model, sc in scores.items():
                if not isinstance(sc, (int, float)):
                    continue
                win = 1 if (count_win and sc >= best - 0.01) else 0
                c.execute(
                    "INSERT INTO scores(task_type,model,runs,points,wins,updated) VALUES(?,?,1,?,?,?) "
                    "ON CONFLICT(task_type,model) DO UPDATE SET runs=runs+1, points=points+?,"
                    " wins=wins+?, updated=?",
                    (task_type, model, float(sc), win, time.time(), float(sc), win, time.time()))

    def leaderboard(self, task_type: str | None = None, min_runs: int = 1, limit: int = 15) -> list[dict]:
        with self._conn() as c:
            if task_type:
                rows = c.execute(
                    "SELECT * FROM scores WHERE task_type=? AND runs>=? ORDER BY (points/runs) DESC, wins DESC LIMIT ?",
                    (task_type, min_runs, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT task_type, model, SUM(runs) runs, SUM(points) points, SUM(wins) wins,"
                    " MAX(updated) updated FROM scores GROUP BY task_type, model"
                    " HAVING SUM(runs)>=? ORDER BY (SUM(points)*1.0/SUM(runs)) DESC LIMIT ?",
                    (min_runs, limit)).fetchall()
        return [{**dict(r), "avg": round((r["points"] or 0) / max(r["runs"] or 1, 1), 2)} for r in rows]

    def model_trust(self, task_type: str) -> dict[str, float]:
        """میانگین امتیاز هر مدل در این نوع کار؛ برای وزن‌دهی به انتخاب خبرگان."""
        with self._conn() as c:
            rows = c.execute("SELECT model, SUM(points) p, SUM(runs) n FROM scores WHERE task_type=? GROUP BY model",
                             (task_type,)).fetchall()
        return {r["model"]: (r["p"] / r["n"]) if r["n"] else 5.0 for r in rows}

    def stats(self) -> dict:
        with self._conn() as c:
            runs = c.execute("SELECT COUNT(*) n FROM runs").fetchone()["n"]
            stages = c.execute("SELECT COUNT(*) n FROM stages").fetchone()["n"]
            models = c.execute("SELECT COUNT(DISTINCT model) n FROM stages").fetchone()["n"]
        return {"runs": runs, "stages": stages, "models": models}


    # ------------------------------------------------- پاک‌سازی و تاریخچه
    def prompts(self, session_id: str = "", limit: int = 200) -> list[dict]:
        """تاریخچهٔ پرامپت‌ها (همه‌ی نشست‌ها یا فقط یک نشست)."""
        with self._conn() as c:
            if session_id:
                rows = c.execute(
                    "SELECT id, session_id, prompt, task_type, mode, created, final "
                    "FROM runs WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (session_id, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, session_id, prompt, task_type, mode, created, final "
                    "FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["final"] = (d.get("final") or "")[:400]
            out.append(d)
        return out

    def session_list(self, limit: int = 50) -> list[dict]:
        """نشست‌ها + تعداد پرامپت هرکدام + آخرین پرامپت (برای پنجرهٔ تاریخچه)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.id, s.title, s.created, s.updated, "
                "  (SELECT COUNT(*) FROM runs r WHERE r.session_id = s.id) AS n, "
                "  (SELECT prompt FROM runs r WHERE r.session_id = s.id ORDER BY id DESC LIMIT 1) AS last_prompt "
                "FROM sessions s ORDER BY s.updated DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def delete_run(self, run_id: int) -> int:
        """پاک کردن یک پرامپت (و مراحلش)."""
        with self._conn() as c:
            c.execute("DELETE FROM stages WHERE run_id=?", (run_id,))
            cur = c.execute("DELETE FROM runs WHERE id=?", (run_id,))
        return cur.rowcount or 0

    def delete_session(self, session_id: str) -> int:
        """پاک کردن یک نشست کامل با همهٔ پرامپت‌هایش."""
        with self._conn() as c:
            ids = [r["id"] for r in c.execute("SELECT id FROM runs WHERE session_id=?", (session_id,)).fetchall()]
            if ids:
                q = ",".join("?" * len(ids))
                c.execute(f"DELETE FROM stages WHERE run_id IN ({q})", ids)
                c.execute(f"DELETE FROM runs WHERE id IN ({q})", ids)
            c.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        return len(ids)

    def clear_history(self, keep_learning: bool = True) -> dict:
        """همهٔ پرامپت‌ها و نشست‌ها را پاک می‌کند (امتیاز مدل‌ها می‌تواند بماند)."""
        with self._conn() as c:
            runs = c.execute("SELECT COUNT(*) n FROM runs").fetchone()["n"]
            c.execute("DELETE FROM stages")
            c.execute("DELETE FROM runs")
            c.execute("DELETE FROM sessions")
            if not keep_learning:
                c.execute("DELETE FROM scores")
        return {"deleted_runs": runs}

    def run_detail(self, run_id: int) -> dict:
        with self._conn() as c:
            run = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            st = c.execute("SELECT role,model,provider,text,seconds,ok,tokens FROM stages WHERE run_id=?",
                           (run_id,)).fetchall()
        return {"run": dict(run) if run else None, "stages": [dict(s) for s in st]}


MEMORY = Memory()
