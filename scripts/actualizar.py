#!/usr/bin/env python3
"""LicitAll — Comprobador y actualizador automático desde GitHub."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILENAME = "github_sync_config.json"
DEFAULT_REPO = "jesusdelval/LicitAll"
DEFAULT_BRANCH = "main"
WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")

PROTECTED_NAMES = {
    "licitall.db",
    "github_sync_config.json",
    "sync_update.log",
    ".git",
    ".env",
}


def log_sync(msg: str) -> None:
    """Append a timestamped line to sync_update.log."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(BASE_DIR / "sync_update.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def load_sync_config() -> dict:
    """Load repository, branch, and optional PAT from github_sync_config.json."""
    cfg_path = BASE_DIR / CONFIG_FILENAME
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return {
                    "repo": str(data.get("repo") or DEFAULT_REPO).strip(),
                    "branch": str(data.get("branch") or DEFAULT_BRANCH).strip(),
                    "token": str(data.get("token") or "").strip(),
                }
        except Exception as exc:
            log_sync(f"Error leyendo {CONFIG_FILENAME}: {exc}")
    return {"repo": DEFAULT_REPO, "branch": DEFAULT_BRANCH, "token": ""}


def get_local_version_info() -> dict:
    """Read version and last_commit_sha from version.json."""
    v_path = BASE_DIR / "version.json"
    if v_path.exists():
        try:
            with open(v_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"version": "1.0.0", "last_commit_sha": ""}


def save_local_version_info(version: str, commit_sha: str) -> None:
    """Persist updated version and commit SHA to version.json."""
    v_path = BASE_DIR / "version.json"
    with open(v_path, "w", encoding="utf-8") as fh:
        json.dump({"version": version, "last_commit_sha": commit_sha}, fh, indent=2, ensure_ascii=False)


def _github_get_bytes(url: str, token: str = "", timeout: int = 15) -> bytes:
    """Fetch bytes from GitHub with SSL verification, falling back to PowerShell proxy on Windows."""
    headers = {
        "User-Agent": "LicitAll-Updater/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception:
        if sys.platform != "win32":
            raise

    ps_script = (
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        "$wc = New-Object System.Net.WebClient; "
        "$wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy(); "
        "$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials; "
        "$wc.Headers.Add('User-Agent', 'LicitAll-Updater/1.0'); "
        "$wc.Headers.Add('Accept', 'application/vnd.github.v3+json'); "
        "if ($env:LA_TOKEN) { $wc.Headers.Add('Authorization', 'Bearer ' + $env:LA_TOKEN) }; "
        "$bytes = $wc.DownloadData($env:LA_URL); "
        "Write-Output ([Convert]::ToBase64String($bytes))"
    )
    env = os.environ.copy()
    env["LA_URL"] = url
    env["LA_TOKEN"] = token
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=max(timeout, 25),
        env=env,
        creationflags=WIN_NO_WINDOW,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError(res.stderr.strip() or "No se pudo conectar con GitHub")
    return base64.b64decode(res.stdout.strip())


def check_for_updates() -> dict:
    """Check whether GitHub has a newer commit than local version.json."""
    cfg = load_sync_config()
    repo = cfg["repo"]
    branch = cfg["branch"]
    token = cfg["token"]

    if not REPO_RE.fullmatch(repo) or not BRANCH_RE.fullmatch(branch):
        return {"ok": False, "has_update": False, "error": "Configuración de repositorio inválida"}

    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    try:
        raw = _github_get_bytes(url, token=token, timeout=12)
        data = json.loads(raw.decode("utf-8"))
        remote_sha = str(data.get("sha") or "")
        commit_msg = str((data.get("commit") or {}).get("message") or "").splitlines()[0]
        local_info = get_local_version_info()
        local_sha = str(local_info.get("last_commit_sha") or "")
        has_update = bool(remote_sha and remote_sha != local_sha)
        return {
            "ok": True,
            "has_update": has_update,
            "remote_sha": remote_sha,
            "local_sha": local_sha,
            "commit_message": commit_msg,
            "repo": repo,
            "branch": branch,
            "token": token,
        }
    except urllib.error.HTTPError as exc:
        msg = f"HTTP {exc.code}"
        if exc.code == 404:
            msg = "Repositorio no encontrado o privado sin token en github_sync_config.json"
        log_sync(f"Check update fallo: {msg}")
        return {"ok": False, "has_update": False, "error": msg}
    except Exception as exc:
        log_sync(f"Check update fallo: {exc}")
        return {"ok": False, "has_update": False, "error": str(exc)}


def _is_protected(rel_path: Path) -> bool:
    parts = rel_path.parts
    if not parts:
        return True
    if parts[0] in PROTECTED_NAMES or rel_path.name in PROTECTED_NAMES:
        return True
    if rel_path.suffix.lower() in (".db", ".xlsx"):
        return True
    return False


def download_and_deploy_update(remote_sha: str, repo: str, branch: str, token: str = "") -> dict:
    """Download GitHub zipball and deploy files without overwriting local DB/config."""
    zip_url = f"https://api.github.com/repos/{repo}/zipball/{branch}"
    try:
        zip_bytes = _github_get_bytes(zip_url, token=token, timeout=45)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmp_path)

            extracted_roots = [p for p in tmp_path.iterdir() if p.is_dir()]
            if not extracted_roots:
                return {"ok": False, "error": "Archivo ZIP vacío"}
            src_root = extracted_roots[0]

            updated_files = 0
            for src_file in src_root.rglob("*"):
                if not src_file.is_file():
                    continue
                rel = src_file.relative_to(src_root)
                if _is_protected(rel):
                    continue
                dest_file = BASE_DIR / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                updated_files += 1

        local_ver = get_local_version_info().get("version", "1.0.0")
        save_local_version_info(local_ver, remote_sha)
        log_sync(f"Actualización desplegada ({remote_sha[:7]}, {updated_files} archivos)")
        return {"ok": True, "updated_files": updated_files, "remote_sha": remote_sha}
    except Exception as exc:
        log_sync(f"Error desplegando actualización: {exc}")
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    info = check_for_updates()
    print(json.dumps({k: v for k, v in info.items() if k != "token"}, ensure_ascii=False, indent=2))
    if info.get("ok") and info.get("has_update"):
        res = download_and_deploy_update(
            remote_sha=info["remote_sha"],
            repo=info["repo"],
            branch=info["branch"],
            token=info.get("token", ""),
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
