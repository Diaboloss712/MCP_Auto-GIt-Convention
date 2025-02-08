import asyncio
import time
import random

# 설정: 테스트할 파일 개수와 LLM 응답 지연 시간
FILE_COUNT = 10
LLM_DELAY = 1.0  # 초 (LLM이 생각하는 시간)
GIT_OP_DELAY = 0.1  # 초 (Git 명령 실행 시간)

print(f"--- 벤치마크 시뮬레이션 시작 ---")
print(f"파일 개수: {FILE_COUNT}개")
print(f"LLM 응답 지연(Mock): {LLM_DELAY}초")
print(f"Git 작업 지연(Mock): {GIT_OP_DELAY}초")
print("-" * 40)

# 1. 동기(Blocking) 방식 시뮬레이션
# 기존 코드가 작동하던 방식: 하나가 끝나야 다음으로 넘어감
def mock_llm_sync(file_name):
    time.sleep(LLM_DELAY)  # 블로킹 대기
    return f"feat: update {file_name}"

def mock_git_commit_sync(file_name):
    time.sleep(GIT_OP_DELAY)
    return True

def run_sync_benchmark():
    start_time = time.time()
    print("\n[Mode 1: 동기식 (Blocking)] 실행 중...")
    
    for i in range(FILE_COUNT):
        file = f"file_{i}.py"
        # 1. Diff 가져오기 (생략, 짧다고 가정)
        # 2. LLM 호출 (오래 걸림)
        msg = mock_llm_sync(file)
        # 3. Git 커밋
        mock_git_commit_sync(file)
        print(f"  - {file} 처리 완료")
        
    duration = time.time() - start_time
    return duration

# 2. 비동기(Non-blocking) 방식 시뮬레이션
# 개선된 방식: LLM 대기 중에 다른 파일 작업을 시작함
async def mock_llm_async(file_name):
    await asyncio.sleep(LLM_DELAY)  # Non-blocking 대기
    return f"feat: update {file_name}"

# Git Lock 시뮬레이션
git_lock = asyncio.Lock()

async def mock_git_commit_async(file_name):
    # Git은 파일 시스템을 쓰므로 동시에 여러 개가 접근하면 안 됨 (Lock 필요)
    async with git_lock:
        await asyncio.sleep(GIT_OP_DELAY)
    return True

async def process_file_async(file_name):
    # LLM 호출은 동시에 진행됨 (병목 해소)
    msg = await mock_llm_async(file_name)
    # Git 커밋은 순차적으로 진행됨 (안전장치)
    await mock_git_commit_async(file_name)
    print(f"  - {file_name} 처리 완료")

async def run_async_benchmark():
    start_time = time.time()
    print("\n[Mode 2: 비동기식 (Non-blocking)] 실행 중...")
    
    tasks = [process_file_async(f"file_{i}.py") for i in range(FILE_COUNT)]
    # 모든 태스크를 동시에 스케줄링
    await asyncio.gather(*tasks)
    
    duration = time.time() - start_time
    return duration

if __name__ == "__main__":
    # 동기 테스트 실행
    sync_time = run_sync_benchmark()
    
    # 비동기 테스트 실행
    async_time = asyncio.run(run_async_benchmark())
    
    print("\n" + "=" * 40)
    print("📊 벤치마크 결과")
    print("=" * 40)
    print(f"1. 동기식 (기존): {sync_time:.2f}초")
    print(f"2. 비동기식 (개선): {async_time:.2f}초")
    
    speedup = sync_time / async_time
    print(f"\n🚀 성능 향상: 약 {speedup:.1f}배")
    print("=" * 40)
    
    if speedup > 4.0:
        print("✅ 검증 성공: 비동기 전환으로 획기적인 성능 향상이 확인되었습니다.")
    else:
        print("⚠️ 참고: 파일 개수가 적거나 Git 작업 비중이 높으면 차이가 줄어들 수 있습니다.")
