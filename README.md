# MCP Auto-Git-Convention

GitHub 커밋을 자동으로 생성하고 관리하는 MCP(Model Context Protocol) 서버입니다. Local LLM(Ollama)을 사용하여 Conventional Commit 형식의 커밋 메시지를 자동으로 생성합니다.

## 주요 기능

- ✅ **자동 커밋 메시지 생성**: Ollama(mistral)를 사용하여 변경사항을 분석하고 Conventional Commit 형식의 메시지 생성
- 📅 **일일 커밋 체크**: GitHub API를 통해 오늘의 커밋 여부 확인
- 🔄 **배치 커밋**: 변경된 모든 파일을 자동으로 커밋하고 push
- 📝 **Untracked 파일 지원**: 새로운 파일도 자동으로 처리

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 생성하고 다음 내용을 입력하세요:

```env
GITHUB_USERNAME=your_github_username
GITHUB_TOKEN=your_github_token
TARGET_PATH=C:/path/to/your/repository
OLLAMA_URL=http://localhost:11434
LOG_FILE=mcp_commit_log.txt
```

**필수 환경변수:**
- `GITHUB_USERNAME`: GitHub 사용자 이름
- `GITHUB_TOKEN`: GitHub Personal Access Token (repo 권한 필요)

**선택 환경변수:**
- `TARGET_PATH`: 작업할 Git 저장소 경로 (미설정시 현재 프로젝트 디렉토리 사용)
- `OLLAMA_URL`: Ollama 서버 주소 (기본값: http://localhost:11434)
- `LOG_FILE`: 로그 파일 경로 (기본값: mcp_commit_log.txt)

### 3. Ollama 설치 및 실행

```bash
# Ollama 설치 후
ollama pull mistral
ollama serve
```

## 사용법

### 서버 실행

```bash
python mcp_server.py
```

서버는 `http://0.0.0.0:8000`에서 실행됩니다.

### 자동 커밋 설정 (선택사항)

매일 자동으로 커밋을 확인하고 필요 시 커밋을 생성하려면:

#### 수동 실행

서버가 실행 중일 때 언제든지:

```bash
python auto_commit.py
```

### API 엔드포인트

#### 1. 오늘의 커밋 확인
```bash
GET /github/check_commit
```

#### 2. 배치 커밋 실행
```bash
POST /commit/batch
```
변경된 모든 파일을 커밋하고 push합니다.

#### 3. 일일 커밋 (조건부)
```bash
POST /commit/daily
```
오늘 커밋이 없을 경우에만 배치 커밋을 실행합니다.

## 지원하는 Conventional Commit 타입

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `docs`: 문서 변경
- `style`: 코드 포맷팅, 세미콜론 누락 등 (기능 변경 없음)
- `refactor`: 코드 리팩토링
- `test`: 테스트 코드 추가/수정
- `chore`: 빌드 프로세스, 라이브러리 업데이트 등
- `perf`: 성능 개선
- `ci`: CI/CD 설정 변경
- `build`: 빌드 시스템 변경

## 최근 개선사항 (2025-10-31)

### 🔧 버그 수정
1. **Untracked 파일 처리 개선**: `git diff`로 감지되지 않던 새 파일도 자동으로 처리
2. **환경변수 검증**: 필수 환경변수(`GITHUB_USERNAME`, `GITHUB_TOKEN`) 누락 시 명확한 에러 메시지 표시
3. **함수 반환값 수정**: `list_untracked_files()` 함수가 예외 발생 시에도 빈 리스트 반환하도록 수정

### ✨ 기능 개선
4. **Conventional Commit 타입 확장**: `style`, `ci`, `build` 타입 추가
5. **HTTP 에러 처리**: Ollama API 호출 시 HTTP 상태 코드 검증 추가
6. **경로 설정 개선**: `TIL_ROOT` 미설정 시 현재 디렉토리 사용하도록 개선

### 🧹 코드 정리
7. **사용하지 않는 임포트 제거**: `traceback` 임포트 제거
8. **타입 힌트 개선**: `Optional` 추가 및 타입 힌트 일관성 개선

## 로그 확인

로그는 `mcp_commit_log.txt` 파일에 저장됩니다:

```bash
cat mcp_commit_log.txt
```

## 문제 해결

### Ollama 연결 실패
- Ollama가 실행 중인지 확인: `ollama list`
- 포트 확인: 기본 포트는 11434

### GitHub API 오류
- GitHub Token의 권한 확인 (repo 권한 필요)
- Token이 만료되지 않았는지 확인

### Git 명령 오류
- 해당 디렉토리가 Git 저장소인지 확인
- Git이 설치되어 있는지 확인

## 라이센스

MIT License
