"""
گیت‌هاب تقلبی برای تست — همان API را جواب می‌دهد تا بتوانیم فرستادن پروژه را
کامل و واقعی (blobs → tree → commit → ref) آزمایش کنیم، بدون اینکه چیزی به اینترنت برود.

اجرا:  python tests/fake_github.py --port 8787
سپس:  GITHUB_API=http://127.0.0.1:8787 GITHUB_TOKEN=test-token-123 python -m pytest tests/test_github.py -v
"""
from __future__ import annotations

import base64
import json
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

TOKEN = "test-token-123"
app = FastAPI(title="Fake GitHub")

# ── حافظه‌ی درون‌فرآیندی
STATE: dict = {"repos": {}, "blobs": {}, "trees": {}, "commits": {}, "issues": {}}


def _slug(owner: str, repo: str) -> str:
    return f"{owner}/{repo}"


def _auth(authorization: str = "") -> str | None:
    if not authorization.startswith("Bearer "):
        return None
    return authorization[7:].strip()


def _deny():
    return JSONResponse({"message": "Bad credentials"}, status_code=401,
                        headers={"x-oauth-scopes": ""})


@app.get("/user")
async def user(authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    return JSONResponse({"login": "tester", "name": "کاربر آزمایشی", "public_repos": 3,
                         "avatar_url": "https://example.com/a.png"},
                        headers={"x-oauth-scopes": "repo, workflow"})


@app.get("/user/repos")
async def repos(authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    out = [{"name": r["name"], "full_name": full, "private": r["private"],
            "html_url": f"https://github.com/{full}", "default_branch": r["default_branch"],
            "description": r.get("description", ""), "updated_at": r.get("updated")}
           for full, r in STATE["repos"].items()]
    return out


@app.post("/user/repos")
async def create_repo(request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    full = _slug("tester", body["name"])
    if full in STATE["repos"]:
        return JSONResponse({"message": "Repository creation failed: name already exists"},
                            status_code=422)
    STATE["repos"][full] = {"name": body["name"], "private": bool(body.get("private")),
                            "default_branch": "main", "description": body.get("description", ""),
                            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "size": 0, "archived": False}
    return {"name": body["name"], "full_name": full, "private": bool(body.get("private")),
            "html_url": f"https://github.com/{full}", "default_branch": "main", "size": 0}


@app.get("/repos/{owner}/{repo}")
async def repo_info(owner: str, repo: str, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    r = STATE["repos"].get(_slug(owner, repo))
    if not r:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    r["size"] = sum(1 for c in STATE["commits"].values() if c["repo"] == _slug(owner, repo)) or r.get("size", 0)
    return {"full_name": _slug(owner, repo), "private": r["private"],
            "default_branch": r["default_branch"], "html_url": f"https://github.com/{owner}/{repo}",
            "size": r["size"]}


# ── Git Data API
@app.get("/repos/{owner}/{repo}/git/ref/heads/{branch}")
async def get_ref(owner: str, repo: str, branch: str, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    full = _slug(owner, repo)
    for c in reversed(list(STATE["commits"].values())):
        if c["repo"] == full and c["branch"] == branch:
            return {"ref": f"refs/heads/{branch}", "object": {"sha": c["sha"], "type": "commit"}}
    return JSONResponse({"message": "Not Found"}, status_code=404)


@app.post("/repos/{owner}/{repo}/git/blobs")
async def create_blob(owner: str, repo: str, request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    raw = base64.b64decode(body.get("content", "")) if body.get("encoding") == "base64" else \
        (body.get("content") or "").encode()
    sha = uuid.uuid4().hex
    STATE["blobs"][sha] = raw
    return {"sha": sha, "size": len(raw)}


@app.post("/repos/{owner}/{repo}/git/trees")
async def create_tree(owner: str, repo: str, request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    sha = uuid.uuid4().hex
    entries = {e["path"]: e["sha"] for e in body.get("tree", [])}
    base = body.get("base_tree")
    merged = dict(STATE["trees"].get(base, {})) if base else {}
    merged.update(entries)
    STATE["trees"][sha] = merged
    return {"sha": sha, "tree": [{"path": k, "sha": v} for k, v in merged.items()]}


@app.post("/repos/{owner}/{repo}/git/commits")
async def create_commit(owner: str, repo: str, request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    sha = uuid.uuid4().hex
    STATE["commits"][sha] = {"sha": sha, "repo": _slug(owner, repo), "tree": body.get("tree"),
                             "message": body.get("message", ""), "parents": body.get("parents") or [],
                             "branch": "main"}
    return {"sha": sha, "tree": {"sha": body.get("tree")}, "message": body.get("message")}


@app.post("/repos/{owner}/{repo}/git/refs")
async def create_ref(owner: str, repo: str, request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    branch = (body.get("ref") or "refs/heads/main").split("/")[-1]
    full = _slug(owner, repo)
    sha = body.get("sha")
    if sha in STATE["commits"]:
        STATE["commits"][sha]["branch"] = branch
    if full not in STATE["repos"]:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    return {"ref": f"refs/heads/{branch}", "object": {"sha": sha}}


@app.patch("/repos/{owner}/{repo}/git/refs/heads/{branch}")
async def update_ref(owner: str, repo: str, branch: str, request: Request,
                     authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    sha = body.get("sha")
    if sha in STATE["commits"]:
        STATE["commits"][sha]["branch"] = branch
    return {"ref": f"refs/heads/{branch}", "object": {"sha": sha}}


# ── Contents API
@app.get("/repos/{owner}/{repo}/contents/{path:path}")
async def get_contents(owner: str, repo: str, path: str, ref: str = "",
                       authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    full = _slug(owner, repo)
    head = _head_tree(full)
    if head is None:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    entries = STATE["trees"].get(head, {})
    if path in entries:
        data = STATE["blobs"].get(entries[path], b"")
        return {"type": "file", "path": path, "size": len(data),
                "content": base64.b64encode(data).decode(), "sha": entries[path],
                "html_url": f"https://github.com/{full}/blob/main/{path}"}
    kids = [k for k in entries if k.startswith(path.rstrip("/") + "/")]
    if kids:
        return [{"type": "file", "name": k.split("/")[-1], "path": k,
                 "size": len(STATE["blobs"].get(entries[k], b"")), "sha": entries[k]}
                for k in kids]
    return JSONResponse({"message": "Not Found"}, status_code=404)


@app.put("/repos/{owner}/{repo}/contents/{path:path}")
async def put_contents(owner: str, repo: str, path: str, request: Request,
                       authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    raw = base64.b64decode(body.get("content", ""))
    blob = uuid.uuid4().hex
    STATE["blobs"][blob] = raw
    full = _slug(owner, repo)
    tree = uuid.uuid4().hex
    head = _head_tree(full)
    merged = dict(STATE["trees"].get(head, {})) if head else {}
    merged[path] = blob
    STATE["trees"][tree] = merged
    commit = uuid.uuid4().hex
    STATE["commits"][commit] = {"sha": commit, "repo": full, "tree": tree,
                                "message": body.get("message", ""), "parents": [head] if head else [],
                                "branch": body.get("branch") or "main"}
    return {"content": {"path": path, "sha": blob,
                        "html_url": f"https://github.com/{full}/blob/main/{path}"},
            "commit": {"sha": commit, "message": body.get("message", "")}}


# ── issue و جست‌وجو
@app.post("/repos/{owner}/{repo}/issues")
async def create_issue(owner: str, repo: str, request: Request, authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    body = await request.json()
    num = len(STATE["issues"]) + 1
    STATE["issues"][num] = {"number": num, "title": body.get("title"), "state": "open",
                            "user": {"login": "tester"}, "repo": _slug(owner, repo)}
    return {**STATE["issues"][num],
            "html_url": f"https://github.com/{owner}/{repo}/issues/{num}"}


@app.get("/repos/{owner}/{repo}/issues")
async def list_issues(owner: str, repo: str, state: str = "open",
                      authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    out = []
    for i in STATE["issues"].values():
        if i["repo"] == _slug(owner, repo) and (state == "all" or i["state"] == state):
            out.append({**i, "html_url": f"https://github.com/{owner}/{repo}/issues/{i['number']}"})
    return out


@app.get("/search/code")
async def search_code(q: str = "", authorization: str = Header("")):
    if _auth(authorization) != TOKEN:
        return _deny()
    hits = []
    for full, tree in _all_trees().items():
        for path in STATE["trees"].get(tree, {}):
            if q and q.split(":")[-1].strip() in path:
                hits.append({"repository": {"full_name": full}, "path": path,
                             "html_url": f"https://github.com/{full}/blob/main/{path}"})
    return {"total_count": len(hits), "items": hits[:10]}


# ── کمک‌تابع‌های درونی
def _head_tree(full: str) -> str | None:
    for c in reversed(list(STATE["commits"].values())):
        if c["repo"] == full:
            return c["tree"]
    return None


def _all_trees() -> dict[str, str]:
    out = {}
    for c in STATE["commits"].values():
        out[c["repo"]] = c["tree"]
    return out


# ── اندپوینت اشکال‌زدایی: کل درخت و محتوای فایل‌ها
@app.get("/__debug/state")
async def debug_state():
    files = {}
    for full in STATE["repos"]:
        tree = _head_tree(full)
        if not tree:
            continue
        files[full] = {p: STATE["blobs"].get(sha, b"").decode("utf-8", "replace")
                       for p, sha in STATE["trees"][tree].items()}
    return {"repos": list(STATE["repos"]), "commits": len(STATE["commits"]),
            "issues": len(STATE["issues"]), "files": files}


@app.post("/__debug/reset")
async def debug_reset():
    STATE.update({"repos": {}, "blobs": {}, "trees": {}, "commits": {}, "issues": {}})
    return {"ok": True}


if __name__ == "__main__":
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
