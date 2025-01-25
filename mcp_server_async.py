import asyncio
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
import httpx
import os
import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
import uvicorn
from pathlib import Path
import sys

# ?ㅼ젙 媛?
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

# ?섍꼍蹂??濡쒕뱶 諛?寃利?
REPO_PATH_STR = os.getenv("TARGET_PATH")
if REPO_PATH_STR:
    REPO_PATH = Path(REPO_PATH_STR)
else:
    REPO_PATH = Path(__file__).resolve().parent
    print(f"?좑툘 TARGET_PATH媛 ?ㅼ젙?섏? ?딆븯?듬땲?? ?꾩옱 ?꾨줈?앺듃 ?붾젆?좊━ ?ъ슜: {REPO_PATH}")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOG_FILE = os.getenv("LOG_FILE", "mcp_commit_log.txt")

if not GITHUB_USERNAME or not GITHUB_TOKEN:
    print("???ㅻ쪟: GITHUB_USERNAME 諛?GITHUB_TOKEN ?섍꼍蹂?섍? ?꾩슂?⑸땲??")
    print("   .env ?뚯씪???뺤씤?섏꽭??")
    # sys.exit(1) # ?쒕쾭媛 二쎌? ?딅룄濡?寃쎄퀬留??섍퀬 ?섏뼱媛??섎룄 ?덉쑝?? ?꾩닔?쇰㈃ ?좎?

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# 鍮꾨룞湲?濡쒓퉭 ?⑥닔
async def log_message(msg: str):
    # ?뚯씪 I/O???ъ쟾???숆린?곸씠吏留?濡쒓퉭? 吏㏃쑝誘濡??덉슜 (?꾨줈?뺤뀡?먯꽑 aiofiles 沅뚯옣)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")

# 鍮꾨룞湲?Git 紐낅졊???ㅽ뻾
async def run_git_command(args: List[str]) -> str:
    # asyncio.subprocess瑜??ъ슜?섏뿬 鍮꾨룞湲??ㅽ뻾
    process = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(REPO_PATH),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        # diff 紐낅졊??寃쎌슦 return code 1??蹂寃쎌궗???덉쓬???섎??????덉쑝誘濡??덉쇅 泥섎━ 二쇱쓽
        # ?섏?留??ш린?쒕뒗 ?쇰컲?곸씤 ?ㅻ쪟 ?곹솴 泥댄겕
        # git diff??蹂寃쎌궗??씠 ?덉쑝硫?醫낅즺肄붾뱶 1???꾨떂 (0??. git diff --exit-code ?듭뀡 ?몃븣留??ㅻ쫫.
        raise Exception(f"Git error: {stderr.decode().strip()}")
    
    return stdout.decode().strip()

def is_valid_convention(message: str) -> bool:
    message = message.strip("`\"' \n")
    valid_types = ["feat", "fix", "chore", "docs", "refactor", "test", "perf", "style", "ci", "build"]
    if ": " not in message:
        return False
    type_part = message.split(":", 1)[0]
    return type_part in valid_types

async def get_modified_files() -> List[str]:
    try:
        # 蹂寃쎈맂 ?뚯씪 紐⑸줉
        output_changed = await run_git_command(["diff", "--name-only"])
        changed = output_changed.splitlines() if output_changed else []
        
        # Untracked ?뚯씪 紐⑸줉
        output_untracked = await run_git_command(["ls-files", "--others", "--exclude-standard"])
        untracked = output_untracked.splitlines() if output_untracked else []
        
        files = changed + untracked
        await log_message(f"蹂寃??뚯씪 紐⑸줉: {files}")
        return files
    except Exception as e:
        await log_message(f"??Git 紐낅졊???ㅻ쪟: {e}")
        return []

async def get_file_diff(file: str) -> str:
    try:
        # staged ?먮뒗 modified ?뚯씪??diff
        try:
            diff = await run_git_command(["diff", "--", file])
            if diff.strip():
                return diff
        except:
            pass
        
        # untracked ?뚯씪 泥섎━
        file_path = REPO_PATH / file
        if file_path.exists() and file_path.is_file():
            try:
                # ?뚯씪 ?쎄린
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return f"New file: {file}\n\n{content[:1000]}"
            except Exception as e:
                await log_message(f"?좑툘 ?뚯씪({file}) ?쎄린 ?ㅽ뙣: {e}")
                return f"New file: {file}"
        return ""
    except Exception as e:
        await log_message(f"???뚯씪({file}) diff 異붿텧 ?ㅽ뙣: {e}")
        return ""

# 鍮꾨룞湲?LLM ?몄텧
async def generate_commit_message(file: str, diff: str) -> str:
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

Generate commit message:"""
    
    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        # 鍮꾨룞湲??대씪?댁뼵???ъ슜 (?듭떖 蹂寃??ы빆)
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            res.raise_for_status()
            commit_msg = res.json().get("response", "").strip()
            
            commit_msg = commit_msg.strip("`\"' \n")
            if commit_msg.startswith("```"):
                commit_msg = commit_msg.replace("```", "").strip()
            if "\n" in commit_msg:
                commit_msg = commit_msg.split("\n")[0].strip()
            
            await log_message(f"LLM?쇰줈遺??諛쏆? 硫붿떆吏 for {file}: {commit_msg}")
            return commit_msg
            
    except httpx.HTTPStatusError as e:
        await log_message(f"??LLM HTTP ?ㅻ쪟({file}): {e.response.status_code}")
        return fallback_commit_message(file, diff)
    except Exception as e:
        await log_message(f"??LLM ?몄텧 ?ㅽ뙣({file}): {e}")
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
# Git Lock 媛앹껜 (?숈떆 ?곌린 諛⑹?)
git_lock = asyncio.Lock()

async def commit_file(file: str) -> Dict[str, Any]:
    result = {"file": file, "status": None, "message": None}
    
    # 1. Diff 媛?몄삤湲?(?쎄린 ?묒뾽? 蹂묐젹 媛??
    diff = await get_file_diff(file)
    if not diff.strip():
        result["status"] = "skipped"
        result["message"] = "蹂寃??댁슜 ?놁쓬"
        await log_message(f"[?ㅽ궢] {file}: 蹂寃??댁슜???놁쓬")
        return result

    # 2. LLM ?몄텧 (?쒓컙???ㅻ옒 嫄몃━??I/O ?묒뾽 - 蹂묐젹 ?ㅽ뻾 ?듭떖 援ш컙)
    commit_msg = await generate_commit_message(file, diff)
    if not commit_msg:
        result["status"] = "failed"
        result["message"] = "LLM?쇰줈遺??硫붿떆吏 ?앹꽦 ?ㅽ뙣"
        return result

    if not is_valid_convention(commit_msg):
        result["status"] = "skipped"
        result["message"] = f"?앹꽦??硫붿떆吏媛 Conventional Commit ?뺤떇???꾨떂: {commit_msg}"
        await log_message(f"[?뺤떇 ?ㅻ쪟] {file}: {commit_msg}")
        return result

    # 3. Git ?곌린 ?묒뾽 (諛섎뱶???쒖감 ?ㅽ뻾 ?꾩슂 - index.lock 異⑸룎 諛⑹?)
    async with git_lock:
        try:
            await run_git_command(["add", file])
            await run_git_command(["commit", "-m", commit_msg])
            result["status"] = "committed"
            result["message"] = commit_msg
            await log_message(f"??{file} 而ㅻ컠?? {commit_msg}")
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
            await log_message(f"??Git 紐낅졊 ?ㅽ뙣({file}): {e}")
    
    return result

async def batch_commit_logic() -> Dict[str, Any]:
    files = await get_modified_files()
    if not files:
        return {"status": "no_changes", "message": "蹂寃쎈맂 ?뚯씪???놁뒿?덈떎."}
    
    # asyncio.gather瑜??ъ슜?섏뿬 ?щ윭 ?뚯씪?????泥섎━瑜??숈떆??吏꾪뻾
    # LLM ?몄텧 ?湲??쒓컙??蹂묐젹濡?泥섎━??
    tasks = [commit_file(file) for file in files]
    results = await asyncio.gather(*tasks)
    
    try:
        await run_git_command(["push"])
        push_status = "pushed"
        await log_message("?뙋 紐⑤뱺 而ㅻ컠 ??push ?꾨즺")
    except Exception as e:
        push_status = f"push error: {e}"
        await log_message(f"??push ?ㅽ뙣: {e}")
        
    return {"status": "done", "push_status": push_status, "details": results}

@app.get("/")
async def root():
    return {
        "message": "MCP Auto-Git-Convention Server (Async)",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "batch_commit": "/commit/batch"
        }
    }

@app.post("/commit/batch")
async def batch_commit_endpoint():
    """??API: 蹂寃쎈맂 ?뚯씪??而ㅻ컠?섍퀬 push ?⑸땲??(Async)."""
    return await batch_commit_logic()

# MCP 留덉슫??
mcp.mount()
mcp.setup_server()

if __name__ == "__main__":
    try:
        print("Async MCP server startup")
        print(f"?뙋 二쇱냼: http://{HOST}:{PORT}")
        uvicorn.run(app, host=HOST, port=int(PORT))
    except Exception as e:
        print(f"??MCP ?쒕쾭 ?ㅽ뻾 以??덉쇅 諛쒖깮: {e}")
