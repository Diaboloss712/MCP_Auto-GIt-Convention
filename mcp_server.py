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
import requests
from datetime import timezone
import sys

# 설정 값
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

# 환경변수 로드 및 검증
REPO_PATH_STR = os.getenv("TARGET_PATH")
if REPO_PATH_STR:
    REPO_PATH = Path(REPO_PATH_STR)
else:
    # .env에 TARGET_PATH가 없으면 현재 프로젝트 디렉토리 사용
    REPO_PATH = Path(__file__).resolve().parent
    print(f"⚠️ TARGET_PATH가 설정되지 않았습니다. 현재 프로젝트 디렉토리 사용: {REPO_PATH}")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOG_FILE = os.getenv("LOG_FILE", "mcp_commit_log.txt")

# 필수 환경변수 검증
if not GITHUB_USERNAME or not GITHUB_TOKEN:
    print("❌ 오류: GITHUB_USERNAME 및 GITHUB_TOKEN 환경변수가 필요합니다.")
    print("   .env 파일을 확인하세요.")
    sys.exit(1)

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
        "info": "MCP 프로토콜은 FastApiMCP가 자동으로 처리합니다. 웹 API를 사용하세요."
    }


# 로깅 함수
def log_message(msg: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")

# Conventional Commit 형식 검사 함수
def is_valid_convention(message: str) -> bool:
    message = message.strip("`\"' \n")
    valid_types = ["feat", "fix", "chore", "docs", "refactor", "test", "perf", "style", "ci", "build"]
    if ": " not in message:
        return False
    type_part = message.split(":", 1)[0]
    return type_part in valid_types

# 변경 파일들을 가져오는 함수
def get_modified_files() -> List[str]:
    try:
        changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=str(REPO_PATH)).decode().splitlines()
        untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=str(REPO_PATH)).decode().splitlines()
        files = changed + untracked
        log_message(f"변경 파일 목록: {files}")
        return files
    except subprocess.CalledProcessError as e:
        log_message(f"❌ Git 명령어 오류: {e}")
        return []

# Untracked 파일 목록 가져오기
def list_untracked_files() -> List[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(REPO_PATH)
        ).decode().splitlines()
        return out
    except subprocess.CalledProcessError as e:
        log_message(f"추적되지 않은 파일 조회 중 오류: {e}")
        return []  # 빈 리스트 반환


# Untracked 파일 stage하기
def stage_all_untracked() -> List[str]:
    new_files = list_untracked_files()
    staged = []
    for f in new_files:
        try:
            subprocess.check_call(["git", "add", f], cwd=str(REPO_PATH))
            staged.append(f)
        except subprocess.CalledProcessError:
            log_message(f"❌ 새로운 파일({f}) add 실패")
    return staged

# 파일별 diff 가져오기 (untracked 파일 처리 포함)
def get_file_diff(file: str) -> str:
    try:
        # staged 또는 modified 파일의 diff
        diff = subprocess.check_output(["git", "diff", "--", file], cwd=str(REPO_PATH)).decode()
        if diff.strip():
            return diff
        
        # diff가 비어있으면 untracked 파일일 수 있음 - 전체 내용 반환
        file_path = REPO_PATH / file
        if file_path.exists() and file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 새 파일로 표시
                    return f"New file: {file}\n\n{content[:1000]}"  # 처음 1000자만
            except Exception as e:
                log_message(f"⚠️ 파일({file}) 읽기 실패: {e}")
                return f"New file: {file}"
        return ""
    except subprocess.CalledProcessError as e:
        log_message(f"❌ 파일({file}) diff 추출 실패: {e}")
        return ""

# LLM으로 메시지 생성
def generate_commit_message(file: str, diff: str) -> str:
    prompt = (
        f'''파일 `{file}`의 변경 내용은 다음과 같습니다:\n{diff}\n\n
        이 변경 내용을 기반으로 한 줄짜리 Conventional Commit 형식의 커밋 메시지를 영어로 생성해 주세요.
        \n 형식은 반드시 다음을 따르세요: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`, `style: ...`, `chore: ...` 등.
        내용이 다양할 경우 가장 핵심적인 convention을 하나만 골라 생성해주세요.
        마크다운 코드 블록이나 따옴표 없이 순수한 커밋 메시지만 생성하세요.'''
    )
    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    }
    try:
        res = httpx.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
        res.raise_for_status()  # HTTP 에러 체크
        commit_msg = res.json().get("response", "").strip()
        log_message(f"LLM으로부터 받은 메시지 for {file}: {commit_msg}")
        return commit_msg
    except httpx.HTTPStatusError as e:
        log_message(f"❌ LLM HTTP 오류({file}): {e.response.status_code}")
        return ""
    except Exception as e:
        log_message(f"❌ LLM 호출 실패({file}): {e}")
        return ""

# 파일 커밋
def commit_file(file: str) -> Dict[str, Any]:
    result = {"file": file, "status": None, "message": None}
    diff = get_file_diff(file)
    if not diff.strip():
        result["status"] = "skipped"
        result["message"] = "변경 내용 없음"
        log_message(f"[스킵] {file}: 변경 내용이 없음")
        return result

    commit_msg = generate_commit_message(file, diff)
    if not commit_msg:
        result["status"] = "failed"
        result["message"] = "LLM으로부터 메시지 생성 실패"
        return result

    if not is_valid_convention(commit_msg):
        result["status"] = "skipped"
        result["message"] = f"생성된 메시지가 Conventional Commit 형식이 아님: {commit_msg}"
        log_message(f"[형식 오류] {file}: {commit_msg}")
        return result

    try:
        subprocess.run(["git", "add", file], cwd=str(REPO_PATH), check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(REPO_PATH), check=True)
        result["status"] = "committed"
        result["message"] = commit_msg
        log_message(f"✅ {file} 커밋됨: {commit_msg}")
    except subprocess.CalledProcessError as e:
        result["status"] = "error"
        result["message"] = str(e)
        log_message(f"❌ Git 명령 실패({file}): {e}")
    return result

# 오늘 GitHub 커밋 확인
def check_commit_activity() -> Dict[str, str]:
    """오늘 GitHub에 커밋이 있었는지 확인합니다."""
    today = datetime.datetime.now(timezone.utc).date()
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/events"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        events = response.json()
        for event in events:
            if event["type"] == "PushEvent":
                pushed_date = datetime.datetime.strptime(event["created_at"], "%Y-%m-%dT%H:%M:%SZ").date()
                if pushed_date == today:
                    return {"status": "committed", "message": "오늘 GitHub에 커밋이 존재합니다."}
        return {"status": "no_commit", "message": "오늘 GitHub에 커밋 기록이 없습니다."}
    except Exception as e:
        return {"status": "error", "message": f"GitHub API 오류: {e}"}

@app.get("/github/check_commit")
def check_commit_endpoint():
    """웹 API: 오늘 GitHub에 커밋이 있었는지 확인합니다."""
    return check_commit_activity()

# 배치 커밋
def batch_commit() -> Dict[str, Any]:
    """변경된 파일을 커밋하고 push 합니다."""
    results = []
    files = get_modified_files()
    if not files:
        return {"status": "no_changes", "message": "변경된 파일이 없습니다."}
    for file in files:
        res = commit_file(file)
        results.append(res)
    try:
        subprocess.run(["git", "push"], cwd=str(REPO_PATH), check=True)
        push_status = "pushed"
        log_message("🌐 모든 커밋 후 push 완료")
    except subprocess.CalledProcessError as e:
        push_status = f"push error: {e}"
        log_message(f"❌ push 실패: {e}")
    return {"status": "done", "push_status": push_status, "details": results}

@app.post("/commit/batch")
def batch_commit_endpoint():
    """웹 API: 변경된 파일을 커밋하고 push 합니다."""
    return batch_commit()

# 일일 자동 커밋
def commit_if_needed() -> Dict[str, Any]:
    """오늘 커밋이 없으면 자동 커밋 및 push 수행합니다."""
    status = check_commit_activity()
    if status["status"] == "committed":
        return {"status": "skipped", "message": "이미 커밋이 존재합니다."}
    return batch_commit()

@app.post("/commit/daily")
def commit_if_needed_endpoint():
    """웹 API: 오늘 커밋이 없으면 자동 커밋 및 push 수행합니다."""
    return commit_if_needed()

# MCP 마운트
mcp.mount()
mcp.setup_server()

for tool in mcp.tools:
    print(f" - {tool.name}: {tool.description}")

if __name__ == "__main__":
    try:
        log_message("🔌 MCP 서버 시작 준비")
        log_message(f"🌐 MCP 서버 주소: http://{HOST}:{PORT}")
        uvicorn.run(app, host=HOST, port=int(PORT))
    except Exception as e:
        log_message(f"❌ MCP 서버 실행 중 예외 발생: {e}")
