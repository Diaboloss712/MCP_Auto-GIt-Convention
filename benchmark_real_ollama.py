import asyncio
import time
import httpx
import os

# 설정
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = "mistral"  # 사용 중인 모델 이름 (없으면 에러 날 수 있음)
REQUEST_COUNT = 5  # 테스트할 요청 횟수 (너무 많으면 로컬 GPU 부하 걸릴 수 있음)

# 테스트용 프롬프트 (짧은 응답 유도)
PROMPT = "Generate a very short git commit message for updating a README file."

print(f"--- 실제 Ollama 성능 벤치마크 ---")
print(f"대상 URL: {OLLAMA_URL}")
print(f"사용 모델: {MODEL}")
print(f"요청 횟수: {REQUEST_COUNT}회")
print("-" * 40)

# 1. 동기(Sync) 방식 테스트
def run_sync_benchmark():
    print("\n[Mode 1: 동기식 (Blocking)] 실행 중...")
    start_time = time.time()
    
    with httpx.Client(timeout=60.0) as client:
        for i in range(REQUEST_COUNT):
            try:
                # 순차적으로 요청하고 응답을 받을 때까지 대기
                resp = client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": MODEL, "prompt": PROMPT, "stream": False}
                )
                resp.raise_for_status()
                content = resp.json().get("response", "").strip().replace("\n", " ")
                print(f"  - 요청 {i+1} 완료: {content[:50]}...")
            except Exception as e:
                print(f"  - 요청 {i+1} 실패: {e}")
                
    return time.time() - start_time

# 2. 비동기(Async) 방식 테스트
async def send_request(client, i):
    try:
        # 비동기 요청 전송
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODEL, "prompt": PROMPT, "stream": False}
        )
        resp.raise_for_status()
        content = resp.json().get("response", "").strip().replace("\n", " ")
        print(f"  - 요청 {i+1} 완료: {content[:50]}...")
    except Exception as e:
        print(f"  - 요청 {i+1} 실패: {e}")

async def run_async_benchmark():
    print("\n[Mode 2: 비동기식 (Non-blocking)] 실행 중...")
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 모든 요청을 동시에 생성하여 스케줄링
        tasks = [send_request(client, i) for i in range(REQUEST_COUNT)]
        await asyncio.gather(*tasks)
        
    return time.time() - start_time

if __name__ == "__main__":
    # Ollama 서버 상태 체크
    try:
        print("🔍 Ollama 서버 연결 확인 중...")
        httpx.get(OLLAMA_URL, timeout=2.0)
        print("✅ 연결 성공")
    except Exception:
        print(f"❌ 오류: Ollama 서버({OLLAMA_URL})에 연결할 수 없습니다.")
        print("   'ollama serve'가 실행 중인지 확인해주세요.")
        exit(1)

    # 동기 테스트
    sync_duration = run_sync_benchmark()
    
    # 비동기 테스트
    async_duration = asyncio.run(run_async_benchmark())
    
    print("\n" + "=" * 40)
    print("📊 실제 LLM 응답 벤치마크 결과")
    print("=" * 40)
    print(f"요청 횟수: {REQUEST_COUNT}회")
    print(f"1. 동기식 (Blocking): {sync_duration:.2f}초 (평균 {sync_duration/REQUEST_COUNT:.2f}초/건)")
    print(f"2. 비동기식 (Concurrent): {async_duration:.2f}초 (전체 소요)")
    
    if async_duration > 0:
        speedup = sync_duration / async_duration
        print(f"\n🚀 성능 향상: 약 {speedup:.1f}배")
    else:
        print("\n🚀 너무 빨라서 측정 불가")
        
    print("=" * 40)
    print("참고: 로컬 LLM의 경우 GPU 처리 한계로 인해 요청이 쌓이면")
    print("개별 응답 속도는 느려질 수 있으나, 전체 처리량(Throughput)은 향상됩니다.")
