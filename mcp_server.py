from fastapi import FastAPI, Request
from fastapi_mcp import FastApiMCP
import subprocess
import httpx
import os
import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import uvicorn
from pathlib import Path
from datetime import timezone
import sys

PORT = "8000"
HOST = "0.0.0.0"
app = FastAPI()
mcp = FastApiMCP(
    app,
    name="commit-tools",
    description="commit-tools with Local LLM",
    describe_full_response_schema=True,
    describe_all_responses=True,
)

load_dotenv()

# ?섍꼍蹂??濡쒕뱶 諛?寃利?REPO_PATH_STR = os.getenv("TARGET_PATH")
if REPO_PATH_STR:
    REPO_PATH = Path(REPO_PATH_STR)
else:
    # .env??TARGET_PATH媛 ?놁쑝硫??꾩옱 ?꾨줈?앺듃 ?붾젆?좊━ ?ъ슜
    REPO_PATH = Path(__file__).resolve().parent
    print(f"?좑툘 TARGET_PATH媛 ?ㅼ젙?섏? ?딆븯?듬땲?? ?꾩옱 ?꾨줈?앺듃 ?붾젆?좊━ ?ъ슜: {REPO_PATH}")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOG_FILE = os.getenv("LOG_FILE", "mcp_commit_log.txt")

if not GITHUB_USERNAME or not GITHUB_TOKEN:
    print("???ㅻ쪟: GITHUB_USERNAME 諛?GITHUB_TOKEN ?섍꼍蹂?섍? ?꾩슂?⑸땲??")
    print("   .env ?뚯씪???뺤씤?섏꽭??")
    print("   fallback 모드로 계속 실행합니다. (일부 API는 인증 정보가 필요합니다.)")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

@app.get("/")
def root():
    return {
        "message": "MCP Auto-Git-Convention Server",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "check_commit": "/github/check_commit",
            "batch_commit": "/commit/batch",
            "daily_commit": "/commit/daily"
        },
        "info": "MCP ?꾨줈?좎퐳? FastApiMCP媛 ?먮룞?쇰줈 泥섎━?⑸땲?? ??API瑜??ъ슜?섏꽭??"
    }


# 濡쒓퉭 ?⑥닔
def log_message(msg: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")

# Conventional Commit ?뺤떇 寃???⑥닔
def is_valid_convention(message: str) -> bool:
    message = message.strip("`\"' \n")
    valid_types = ["feat", "fix", "chore", "docs", "refactor", "test", "perf", "style", "ci", "build"]
    if ": " not in message:
        return False
    type_part = message.split(":", 1)[0]
    return type_part in valid_types

# 蹂寃??뚯씪?ㅼ쓣 媛?몄삤???⑥닔
def get_modified_files() -> List[str]:
    try:
        changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=str(REPO_PATH)).decode().splitlines()
        untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=str(REPO_PATH)).decode().splitlines()
        files = changed + untracked
        log_message(f"蹂寃??뚯씪 紐⑸줉: {files}")
        return files
    except subprocess.CalledProcessError as e:
        log_message(f"??Git 紐낅졊???ㅻ쪟: {e}")
        return []

# Untracked ?뚯씪 紐⑸줉 媛?몄삤湲?def list_untracked_files() -> List[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(REPO_PATH)
        ).decode().splitlines()
        return out
    except subprocess.CalledProcessError as e:
        log_message(f"異붿쟻?섏? ?딆? ?뚯씪 議고쉶 以??ㅻ쪟: {e}")
        return []  # 鍮?由ъ뒪??諛섑솚


# Untracked ?뚯씪 stage?섍린
def stage_all_untracked() -> List[str]:
    new_files = list_untracked_files()
    staged = []
    for f in new_files:
        try:
            subprocess.check_call(["git", "add", f], cwd=str(REPO_PATH))
            staged.append(f)
        except subprocess.CalledProcessError:
            log_message(f"???덈줈???뚯씪({f}) add ?ㅽ뙣")
    return staged

# ?뚯씪蹂?diff 媛?몄삤湲?(untracked ?뚯씪 泥섎━ ?ы븿)
def get_file_diff(file: str) -> str:
    try:
        # staged ?먮뒗 modified ?뚯씪??diff
        diff = subprocess.check_output(["git", "diff", "--", file], cwd=str(REPO_PATH)).decode()
        if diff.strip():
            return diff
        
        # diff媛 鍮꾩뼱?덉쑝硫?untracked ?뚯씪?????덉쓬 - ?꾩껜 ?댁슜 諛섑솚
        file_path = REPO_PATH / file
        if file_path.exists() and file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # ???뚯씪濡??쒖떆
                    return f"New file: {file}\n\n{content[:1000]}"  # 泥섏쓬 1000?먮쭔
            except Exception as e:
                log_message(f"?좑툘 ?뚯씪({file}) ?쎄린 ?ㅽ뙣: {e}")
                return f"New file: {file}"
        return ""
    except subprocess.CalledProcessError as e:
        log_message(f"???뚯씪({file}) diff 異붿텧 ?ㅽ뙣: {e}")
        return ""

# LLM?쇰줈 硫붿떆吏 ?앹꽦
def generate_commit_message(file: str, diff: str) -> str:
    prompt = f"""You are a Git commit message generator. Generate a single-line Conventional Commit message in English.

File: {file}
Changes:
{diff[:500]}

STRICT RULES:
1. Use ONLY these types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
2. Format: <type>: <description>
3. ONE line only, no newlines
4. No markdown, no quotes, no code blocks
5. Description must be concise (max 72 characters total)
6. Start with lowercase after colon

Examples:
- feat: add user authentication
- fix: resolve memory leak in parser
- docs: update installation guide
- refactor: simplify data processing logic

Generate commit message:"""
    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    }
    try:
        res = httpx.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
        res.raise_for_status()  # HTTP ?먮윭 泥댄겕
        commit_msg = res.json().get("response", "").strip()
        
        # ?꾩쿂由? 遺덊븘?뷀븳 臾몄옄 ?쒓굅
        commit_msg = commit_msg.strip("`\"' \n")  # 留덊겕?ㅼ슫, ?곗샂???쒓굅
        if commit_msg.startswith("```"):
            commit_msg = commit_msg.replace("```", "").strip()
        
        # 泥?以꾨쭔 ?ъ슜 (?뱀떆 ?щ윭 以꾩씠硫?
        if "\n" in commit_msg:
            commit_msg = commit_msg.split("\n")[0].strip()
        
        log_message(f"LLM?쇰줈遺??諛쏆? 硫붿떆吏 for {file}: {commit_msg}")
        return commit_msg
    except httpx.HTTPStatusError as e:
        log_message(f"??LLM HTTP ?ㅻ쪟({file}): {e.response.status_code}")
        return fallback_commit_message(file, diff)
    except Exception as e:
        log_message(f"??LLM ?몄텧 ?ㅽ뙣({file}): {e}")
        return fallback_commit_message(file, diff)

def fallback_commit_message(file: str, diff: str) -> str:
    """LLM 실패 시 최소 동작을 보장하는 fallback 메시지 생성."""
    file_lower = file.lower()
    diff_lower = diff.lower()

    if "test" in file_lower or "assert" in diff_lower:
        return "test: update test cases"
    if file_lower.endswith((".md", ".txt")):
        return "docs: update project documentation"
    if "fix" in diff_lower or "bug" in diff_lower or "error" in diff_lower:
        return "fix: resolve issue in changed files"
    if file_lower.endswith((".yml", ".yaml", "dockerfile", ".env")):
        return "chore: update configuration"
    return "chore: update project files"

# ?뚯씪 而ㅻ컠
def commit_file(file: str) -> Dict[str, Any]:
    result = {"file": file, "status": None, "message": None}
    diff = get_file_diff(file)
    if not diff.strip():
        result["status"] = "skipped"
        result["message"] = "蹂寃??댁슜 ?놁쓬"
        log_message(f"[?ㅽ궢] {file}: 蹂寃??댁슜???놁쓬")
        return result

    commit_msg = generate_commit_message(file, diff)
    if not commit_msg:
        result["status"] = "failed"
        result["message"] = "LLM?쇰줈遺??硫붿떆吏 ?앹꽦 ?ㅽ뙣"
        return result

    if not is_valid_convention(commit_msg):
        result["status"] = "skipped"
        result["message"] = f"?앹꽦??硫붿떆吏媛 Conventional Commit ?뺤떇???꾨떂: {commit_msg}"
        log_message(f"[?뺤떇 ?ㅻ쪟] {file}: {commit_msg}")
        return result

    try:
        subprocess.run(["git", "add", file], cwd=str(REPO_PATH), check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(REPO_PATH), check=True)
        result["status"] = "committed"
        result["message"] = commit_msg
        log_message(f"??{file} 而ㅻ컠?? {commit_msg}")
    except subprocess.CalledProcessError as e:
        result["status"] = "error"
        result["message"] = str(e)
        log_message(f"??Git 紐낅졊 ?ㅽ뙣({file}): {e}")
    return result

# 諛곗튂 而ㅻ컠
def batch_commit() -> Dict[str, Any]:
    """蹂寃쎈맂 ?뚯씪??而ㅻ컠?섍퀬 push ?⑸땲??"""
    results = []
    files = get_modified_files()
    if not files:
        return {"status": "no_changes", "message": "蹂寃쎈맂 ?뚯씪???놁뒿?덈떎."}
    for file in files:
        res = commit_file(file)
        results.append(res)
    try:
        subprocess.run(["git", "push"], cwd=str(REPO_PATH), check=True)
        push_status = "pushed"
        log_message("?뙋 紐⑤뱺 而ㅻ컠 ??push ?꾨즺")
    except subprocess.CalledProcessError as e:
        push_status = f"push error: {e}"
        log_message(f"??push ?ㅽ뙣: {e}")
    return {"status": "done", "push_status": push_status, "details": results}

@app.post("/commit/batch")
def batch_commit_endpoint():
    """??API: 蹂寃쎈맂 ?뚯씪??而ㅻ컠?섍퀬 push ?⑸땲??"""
    return batch_commit()

mcp.mount()
mcp.setup_server()

for tool in mcp.tools:
    print(f" - {tool.name}: {tool.description}")

if __name__ == "__main__":
    try:
        log_message("MCP server startup")
        log_message(f"?뙋 MCP ?쒕쾭 二쇱냼: http://{HOST}:{PORT}")
        uvicorn.run(app, host=HOST, port=int(PORT))
    except Exception as e:
        log_message(f"??MCP ?쒕쾭 ?ㅽ뻾 以??덉쇅 諛쒖깮: {e}")


