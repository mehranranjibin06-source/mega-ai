"""
اتصال واقعی به گیت‌هاب — با کلید (Personal Access Token) خودِ کاربر.

این ماژول بدون هیچ واسطه‌ای با API گیت‌هاب حرف می‌زند:
ساخت مخزن، خواندن و نوشتن فایل، فرستادن یک پوشه‌ی کامل در **یک کامیت** (Git Data API)،
issue، جست‌وجو. هیچ کلیدی جایی جز فایل .env خودت ذخیره نمی‌شود.

متغیرهای محیطی:
    GITHUB_TOKEN   کلید دسترسی (github.com/settings/tokens — دسترسی repo/public_repo)
    GITHUB_API     آدرس API (پیش‌فرض https://api.github.com — برای تست می‌توان به سرور محلی داد)
    GITHUB_USER    نام کاربری (اختیاری؛ اگر ندهی از /user خوانده می‌شود)
"""
from __future__ import annotations

import asyncio
import base64
import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

DEFAULT_API = "https://api.github.com"

# پوشه‌هایی که هرگز فرستاده نمی‌شوند (کلید و داده‌ی خصوصی)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".next", ".cache",
             ".idea", ".vscode", "coverage", "out"}
# این‌ها همیشه (حتی اگر .gitignore نبود) فرستاده نمی‌شوند — داده‌ی شخصی کاربر
PRIVATE_DIRS = {"data", "workspace", "skills"}
SKIP_FILES = {".env", ".git-credentials", ".netrc", "id_rsa", "id_ed25519",
              ".DS_Store", "Thumbs.db"}
SKIP_PATTERNS = ("*.pyc", "*.log", "*.bundle", "*.sqlite", "*.db", "*.zip",
                 "*.tar.gz", "*.tgz", "*.7z", "*.rar", "*.psd", "*.iso")
MAX_FILE_BYTES = 8 * 1024 * 1024          # فایل بزرگ‌تر از این رد می‌شود (محدودیت گیت‌هاب)
DEFAULT_MAX_FILES = 400


class GitHubError(Exception):
    """خطای گیت‌هاب با پیام فارسی قابل‌فهم."""


def token_from_env() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def api_base() -> str:
    return (os.environ.get("GITHUB_API") or DEFAULT_API).rstrip("/")


def _hint(status: int, body: str) -> str:
    b = (body or "").lower()
    if status == 401:
        return "توکن نامعتبر یا منقضی است — یک توکن تازه از github.com/settings/tokens بساز."
    if status == 403:
        if "rate limit" in b or "secondary" in b:
            return "سقف درخواست‌های گیت‌هاب پر شده؛ کمی بعد دوباره امتحان کن."
        return "دسترسی کافی نیست — مطمئن شو توکن دسترسی «repo» دارد."
    if status == 404:
        return "پیدا نشد — یا نام مخزن/مسیر اشتباه است، یا مخزن خصوصی است و توکن دسترسی ندارد."
    if status == 422:
        return "داده نامعتبر یا این نام قبلاً استفاده شده (گیت‌هاب نام مخزن تکراری را رد می‌کند)."
    if status == 409:
        return "تضاد در تاریخچه — شاخه‌ی مخزن تغییر کرده؛ یک بار دیگر امتحان کن."
    return f"گیت‌هاب خطای {status} برگرداند."


def load_gitignore(root: Path) -> list[str]:
    """الگوهای .gitignore پروژه (خطوط ساده؛ نگاتیو‌ها و کامنت‌ها نادیده گرفته می‌شوند)."""
    f = Path(root) / ".gitignore"
    pats: list[str] = []
    if f.is_file():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("!"):
                pats.append(line.rstrip("/"))
    return pats


def gitignore_match(rel: Path, patterns: Iterable[str]) -> bool:
    s = str(rel).replace(os.sep, "/")
    for pat in patterns:
        p = pat.lstrip("/")
        if not p:
            continue
        if fnmatch.fnmatch(s, p) or s.startswith(p + "/") or fnmatch.fnmatch(rel.name, p):
            return True
        if any(fnmatch.fnmatch(part, p) for part in rel.parts):
            return True
    return False


def should_skip(rel: Path, extra_ignore: Iterable[str] = (),
                patterns: Iterable[str] = ()) -> bool:
    """آیا این مسیر نباید فرستاده شود؟ (کلید، داده‌ی شخصی، فایل حجیم، پوشه‌های موقت)"""
    parts = set(rel.parts)
    if parts & SKIP_DIRS or parts & PRIVATE_DIRS:
        return True
    if gitignore_match(rel, patterns):
        return True
    if rel.name in SKIP_FILES:
        return True
    if any(fnmatch.fnmatch(rel.name, pat) for pat in SKIP_PATTERNS):
        return True
    for pat in extra_ignore:
        if fnmatch.fnmatch(rel.name, pat) or fnmatch.fnmatch(str(rel), pat):
            return True
    return False


def collect_files(folder: str | Path, extra_ignore: Iterable[str] = (),
                  max_files: int = DEFAULT_MAX_FILES,
                  max_bytes: int = MAX_FILE_BYTES,
                  patterns: Optional[Iterable[str]] = None) -> tuple[list[tuple[Path, Path]], list[str]]:
    """فایل‌های قابل‌فرستادن را جمع می‌کند. برمی‌گرداند: [(مسیر مطلق، مسیر نسبی)]، [هشدارها]

    به‌صورت پیش‌فرض `.gitignore` پوشه هم رعایت می‌شود (مثل خود گیت).
    """
    root = Path(folder)
    if not root.is_dir():
        raise GitHubError(f"پوشه پیدا نشد: {root}")
    pats = list(patterns) if patterns is not None else load_gitignore(root)
    files: list[tuple[Path, Path]] = []
    warns: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if should_skip(rel, extra_ignore, pats):
            continue
        size = p.stat().st_size
        if size > max_bytes:
            warns.append(f"رد شد (بزرگ‌تر از {max_bytes // 1024 // 1024} مگابایت): {rel}")
            continue
        files.append((p, rel))
        if len(files) >= max_files:
            warns.append(f"فقط {max_files} فایل اول فرستاده می‌شود (بقیه رد شد).")
            break
    if not files:
        raise GitHubError("هیچ فایل قابل‌فرستادنی پیدا نشد (یا همه فیلتر شدند).")
    return files, warns


class GitHub:
    """کلاینت گیت‌هاب — همه‌ی متدها async و بی‌واسطه روی REST API."""

    def __init__(self, token: Optional[str] = None, api: Optional[str] = None,
                 timeout: int = 60, user: Optional[str] = None):
        self.token = (token if token is not None else token_from_env()).strip()
        self.api = (api or api_base()).rstrip("/")
        self.timeout = timeout
        self._user = (user or os.environ.get("GITHUB_USER") or "").strip()
        if not self.token:
            raise GitHubError(
                "کلید گیت‌هاب نداری. یک توکن بساز (github.com/settings/tokens با دسترسی repo) "
                "و در پنل → ⚙️ تنظیمات → «گیت‌هاب» بچسبان، یا در .env بگذار: GITHUB_TOKEN=…")

    # ------------------------------------------------------------ زیرساخت
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "MEGA-AI/1.0"}

    async def _req(self, method: str, path: str, *, json_body: Any = None, raw: bool = False,
                   client: Optional[httpx.AsyncClient] = None) -> Any:
        url = path if path.startswith("http") else f"{self.api}{path}"
        own = client is None
        c = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            r = await c.request(method, url, headers=self._headers(),
                                json=json_body if json_body is not None else None)
            text = r.text
            if r.status_code >= 400:
                msg = text
                try:
                    j = json.loads(text)
                    msg = j.get("message") or text
                except Exception:
                    pass
                raise GitHubError(f"{_hint(r.status_code, text)}  [HTTP {r.status_code}: {msg[:200]}]")
            if raw:
                return r.content
            return json.loads(text) if text.strip() else {}
        finally:
            if own:
                await c.aclose()

    # ------------------------------------------------------------ کاربر
    async def whoami(self) -> dict:
        d = await self._req("GET", "/user")
        self._user = d.get("login") or self._user
        return {"login": d.get("login"), "name": d.get("name"), "repos": d.get("public_repos"),
                "avatar": d.get("avatar_url"),
                "scopes": self._scopes}

    _scopes: str = ""

    @property
    def user(self) -> str:
        return self._user

    async def ensure_user(self) -> str:
        if not self._user:
            await self.whoami()
        return self._user

    async def scopes(self) -> str:
        """دسترسی‌های توکن (از هدر پاسخ) — برای راهنمایی کاربر."""
        url = f"{self.api}/user"
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(url, headers=self._headers())
            sc = r.headers.get("x-oauth-scopes") or ""
            if r.status_code >= 400:
                raise GitHubError(f"{_hint(r.status_code, r.text)}  [HTTP {r.status_code}]")
            body = r.json() if r.text.strip() else {}
            self._user = body.get("login") or self._user
            self._scopes = sc
            return sc

    # ------------------------------------------------------------ مخزن‌ها
    async def list_repos(self, limit: int = 30, include_private: bool = True) -> list[dict]:
        out: list[dict] = []
        page = 1
        while len(out) < limit and page <= 5:
            data = await self._req("GET", f"/user/repos?per_page=100&page={page}&sort=updated")
            if not isinstance(data, list) or not data:
                break
            for r in data:
                if not include_private and r.get("private"):
                    continue
                out.append({"name": r.get("name"), "full_name": r.get("full_name"),
                            "private": bool(r.get("private")), "url": r.get("html_url"),
                            "default_branch": r.get("default_branch") or "main",
                            "description": (r.get("description") or "")[:120],
                            "updated": r.get("updated_at")})
                if len(out) >= limit:
                    break
            page += 1
        return out

    async def repo_info(self, repo: str) -> dict:
        """repo می‌تواند «name» یا «owner/name» باشد."""
        if "/" not in repo:
            repo = f"{await self.ensure_user()}/{repo}"
        d = await self._req("GET", f"/repos/{repo}")
        return {"full_name": d.get("full_name"), "private": d.get("private"),
                "default_branch": d.get("default_branch") or "main",
                "url": d.get("html_url"), "size_kb": d.get("size"),
                "empty": (d.get("size") or 0) == 0}

    async def create_repo(self, name: str, private: bool = True, description: str = "",
                          auto_init: bool = False) -> dict:
        if "/" in name:                       # مثلاً owner/name → برای سازمان
            org, _, nm = name.partition("/")
            path = f"/orgs/{org}/repos"
            name = nm
        else:
            path = "/user/repos"
        body = {"name": name, "private": bool(private), "description": description[:350],
                "auto_init": bool(auto_init), "has_issues": True, "has_wiki": False}
        d = await self._req("POST", path, json_body=body)
        return {"full_name": d.get("full_name"), "url": d.get("html_url"),
                "private": d.get("private"), "default_branch": d.get("default_branch") or "main",
                "created": True}

    async def create_repo_if_missing(self, name: str, private: bool = True, description: str = "") -> dict:
        try:
            info = await self.repo_info(name)
            info["created"] = False
            return info
        except GitHubError as e:
            if "پیدا نشد" in str(e):
                return await self.create_repo(name, private=private, description=description)
            raise

    # ------------------------------------------------------------ فایل‌ها
    async def get_file(self, repo: str, path: str, ref: str = "") -> dict:
        if "/" not in repo:
            repo = f"{await self.ensure_user()}/{repo}"
        q = f"?ref={ref}" if ref else ""
        try:
            d = await self._req("GET", f"/repos/{repo}/contents/{path.strip('/')}{q}")
        except GitHubError as e:
            if "پیدا نشد" in str(e):
                return {"exists": False, "path": path}
            raise
        if isinstance(d, list):
            return {"exists": True, "path": path, "type": "dir",
                    "items": [{"name": i.get("name"), "path": i.get("path"), "type": i.get("type"),
                               "size": i.get("size")} for i in d]}
        content = ""
        if d.get("content"):
            try:
                content = base64.b64decode(d["content"]).decode("utf-8", "replace")
            except Exception:
                content = ""
        return {"exists": True, "path": d.get("path"), "type": "file", "size": d.get("size"),
                "sha": d.get("sha"), "content": content, "url": d.get("html_url")}

    async def put_file(self, repo: str, path: str, content: str | bytes, message: str,
                       branch: str = "", sha: Optional[str] = None) -> dict:
        """نوشتن یک فایل (Contents API) — برای تغییرهای کوچک."""
        if "/" not in repo:
            repo = f"{await self.ensure_user()}/{repo}"
        data = content.encode("utf-8") if isinstance(content, str) else content
        body: dict[str, Any] = {"message": message or f"update {path}",
                                "content": base64.b64encode(data).decode()}
        if branch:
            body["branch"] = branch
        if sha:
            body["sha"] = sha
        d = await self._req("PUT", f"/repos/{repo}/contents/{path.strip('/')}", json_body=body)
        return {"ok": True, "path": path,
                "commit": ((d.get("commit") or {}).get("sha") if isinstance(d, dict) else None),
                "url": ((d.get("content") or {}).get("html_url") if isinstance(d, dict) else None)}

    # ------------------------------------------------------------ فرستادن پوشه (Git Data API)
    async def _head_sha(self, repo: str, branch: str, client: httpx.AsyncClient) -> Optional[str]:
        try:
            d = await self._req("GET", f"/repos/{repo}/git/ref/heads/{branch}", client=client)
            return (d.get("object") or {}).get("sha")
        except GitHubError:
            return None

    async def _blob(self, repo: str, path: str, data: bytes, client: httpx.AsyncClient,
                    sem: asyncio.Semaphore) -> dict:
        async with sem:
            d = await self._req("POST", f"/repos/{repo}/git/blobs", client=client,
                                json_body={"content": base64.b64encode(data).decode(),
                                           "encoding": "base64"})
            return {"path": path, "mode": "100644", "type": "blob", "sha": d.get("sha")}

    async def push_folder(self, folder: str | Path, repo: str, *,
                          message: str = "", branch: str = "",
                          private: bool = True, create: bool = True,
                          description: str = "", extra_ignore: Iterable[str] = (),
                          patterns: Optional[Iterable[str]] = None,
                          max_files: int = DEFAULT_MAX_FILES,
                          concurrency: int = 8,
                          progress: Optional[Callable[[str], None]] = None) -> dict:
        """
        یک پوشه‌ی کامل را در **یک کامیت** به مخزن می‌فرستد (blobs → tree → commit → ref).
        خروجی: {ok, repo, url, branch, commit, files, skipped_warnings}
        """
        def say(msg: str) -> None:
            if progress:
                try:
                    progress(msg)
                except Exception:
                    pass

        files, warns = collect_files(folder, extra_ignore, max_files, patterns=patterns)
        owner_repo = repo
        info: dict = {}
        if create:
            say(f"▸ بررسی/ساخت مخزن {repo} …")
            info = await self.create_repo_if_missing(repo, private=private, description=description)
            owner_repo = info["full_name"]
        else:
            info = await self.repo_info(repo)
            owner_repo = info["full_name"]
        branch = branch or info.get("default_branch") or "main"
        url = info.get("url") or f"https://github.com/{owner_repo}"
        say(f"▸ مخزن: {owner_repo} (شاخه {branch}) — {len(files)} فایل آماده است")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            parent = await self._head_sha(owner_repo, branch, client)
            say("▸ ساخت blobها…" if parent else "▸ مخزن خالی است؛ کامیت اول را می‌سازم…")
            sem = asyncio.Semaphore(max(1, concurrency))
            tree = await asyncio.gather(*[
                self._blob(owner_repo, str(rel).replace(os.sep, "/"), p.read_bytes(), client, sem)
                for p, rel in files])
            say(f"▸ {len(tree)} فایل آپلود شد؛ ساخت درخت (tree) …")
            tree_body: dict[str, Any] = {"tree": tree}
            if parent:
                tree_body["base_tree"] = parent
            t = await self._req("POST", f"/repos/{owner_repo}/git/trees", client=client,
                                json_body=tree_body)
            tree_sha = t.get("sha")
            if not tree_sha:
                raise GitHubError("ساخت درخت مخزن ناموفق بود.")
            commit_body: dict[str, Any] = {
                "message": message or f"MEGA-AI: بروزرسانی {len(files)} فایل",
                "tree": tree_sha, "parents": [parent] if parent else []}
            c = await self._req("POST", f"/repos/{owner_repo}/git/commits", client=client,
                               json_body=commit_body)
            commit_sha = c.get("sha")
            if parent:
                await self._req("PATCH", f"/repos/{owner_repo}/git/refs/heads/{branch}",
                                client=client, json_body={"sha": commit_sha, "force": False})
            else:
                try:
                    await self._req("POST", f"/repos/{owner_repo}/git/refs", client=client,
                                    json_body={"ref": f"refs/heads/{branch}", "sha": commit_sha})
                except GitHubError as e:
                    if "قبلاً" in str(e) or "already exists" in str(e).lower() or "422" in str(e):
                        await self._req("PATCH", f"/repos/{owner_repo}/git/refs/heads/{branch}",
                                        client=client, json_body={"sha": commit_sha})
                    else:
                        raise
        say("✅ فرستاده شد.")
        return {"ok": True, "repo": owner_repo, "url": url, "branch": branch,
                "commit": commit_sha, "files": len(files), "created": bool(info.get("created")),
                "warnings": warns, "commit_url": f"{url}/commit/{commit_sha}" if commit_sha else url}

    async def push_session(self, session: str, repo: str, **kw) -> dict:
        """پوشه‌ی یک نشست (خروجی‌های ساخته‌شده) را می‌فرستد."""
        from .config import WORKSPACE
        folder = WORKSPACE / session
        if not folder.is_dir():
            raise GitHubError(f"نشست «{session}» پیدا نشد.")
        return await self.push_folder(folder, repo, **kw)

    async def push_project(self, **kw) -> dict:
        """خودِ پروژه‌ی MEGA-AI را می‌فرستد (با رعایت .gitignore و پرهیز از داده‌ی شخصی)."""
        root = Path(__file__).resolve().parent.parent
        extra = list(kw.pop("extra_ignore", []) or []) + ["data", "workspace", "skills/installed-pip.txt"]
        return await self.push_folder(root, extra_ignore=extra, **kw)

    # ------------------------------------------------------------ issue و جست‌وجو
    async def create_issue(self, repo: str, title: str, body: str = "",
                           labels: Optional[list[str]] = None) -> dict:
        if "/" not in repo:
            repo = f"{await self.ensure_user()}/{repo}"
        d = await self._req("POST", f"/repos/{repo}/issues",
                            json_body={"title": title[:250], "body": body or "",
                                       "labels": labels or []})
        return {"ok": True, "number": d.get("number"), "url": d.get("html_url")}

    async def list_issues(self, repo: str, state: str = "open", limit: int = 20) -> list[dict]:
        if "/" not in repo:
            repo = f"{await self.ensure_user()}/{repo}"
        d = await self._req("GET", f"/repos/{repo}/issues?state={state}&per_page={limit}")
        return [{"number": i.get("number"), "title": i.get("title"),
                 "state": i.get("state"), "url": i.get("html_url"),
                 "user": ((i.get("user") or {}).get("login"))} for i in (d or [])]

    async def search_code(self, query: str, limit: int = 10) -> list[dict]:
        d = await self._req("GET", f"/search/code?q={httpx.QueryParams({'q': query})['q']}&per_page={limit}")
        return [{"repo": (i.get("repository") or {}).get("full_name"), "path": i.get("path"),
                 "url": i.get("html_url")} for i in ((d or {}).get("items") or [])]


# ------------------------------------------------------------------ تست سریع
async def test_token(token: Optional[str] = None) -> dict:
    """کلید را واقعاً امتحان می‌کند و وضعیت را برمی‌گرداند (برای پنل)."""
    try:
        gh = GitHub(token)
    except GitHubError as e:
        return {"ok": False, "error": str(e), "hint": "توکن را در ⚙️ تنظیمات → گیت‌هاب بگذار."}
    try:
        scopes = await gh.scopes()
        me = await gh.whoami()
        can_repo = ("repo" in scopes) or ("public_repo" in scopes) or scopes == ""
        return {"ok": True, "login": me.get("login"), "name": me.get("name"),
                "scopes": scopes or "(نامشخص — توکن‌های ریزدانه scope ندارند)",
                "can_push": can_repo, "avatar": me.get("avatar"),
                "hint": "" if can_repo else "این توکن دسترسی نوشتن ندارد؛ توکنی با دسترسی repo بساز."}
    except GitHubError as e:
        return {"ok": False, "error": str(e), "hint": "توکن را بررسی کن."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "hint": "اتصال به گیت‌هاب برقرار نشد (اینترنت/پروکسی)."}


def save_token(token: str) -> None:
    """کلید را در .env ذخیره و فوراً فعال می‌کند (فایل با دسترسی ۶۰۰)."""
    from .config import save_keys
    save_keys({"GITHUB_TOKEN": token.strip()})
