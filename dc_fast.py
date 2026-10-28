import os
import re
import sys
import time
import shutil
import winsound
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

NUM_WORKERS = 5
SIGNUP_URL = "https://www.dcinside.com"

CODE_SPLIT_REGEX = re.compile(r"^([a-zA-Z]{3,15})(\d{4})$")

# 사용자 설정 전역 변수
TARGET_WORDS = []
TARGET_NUMS = []
REQUIRE_BOTH = True  # y = 둘 다 일치, n = 둘 중 하나만 일치


def is_target_code(code: str) -> bool:
    match = CODE_SPLIT_REGEX.match(code.strip())
    if not match:
        return False

    word = match.group(1).lower()
    num = match.group(2)

    has_word_cond = len(TARGET_WORDS) > 0
    has_num_cond = len(TARGET_NUMS) > 0

    if not has_word_cond and not has_num_cond:
        return False

    word_matched = word in TARGET_WORDS if has_word_cond else True
    num_matched = num in TARGET_NUMS if has_num_cond else True

    # 조건 판별
    if has_word_cond and has_num_cond:
        if REQUIRE_BOTH:
            return word_matched and num_matched  # 둘 다 맞아야 함
        else:
            return word_matched or num_matched   # 둘 중 하나만 맞아도 됨
    elif has_word_cond:
        return word_matched
    elif has_num_cond:
        return num_matched

    return False


lock = threading.Lock()
total_attempts = 0
found_list = []


def create_driver(worker_id):
    profile_dir = os.path.abspath(f"./chrome_server_profiles/worker_{worker_id}")
    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    options.page_load_strategy = "none"

    prefs = {
        "profile.managed_default_content_settings.images": 1,
        "profile.default_content_setting_values.images": 1,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    width = 380
    height = 680
    x_pos = worker_id * 370
    y_pos = 40
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument(f"--window-position={x_pos},{y_pos}")

    driver = webdriver.Chrome(options=options)
    return driver, profile_dir


def extract_code(driver):
    try:
        code = driver.execute_script("""
            const inputs = document.querySelectorAll('input[type="text"], input:not([type]), input[readonly]');
            for (const el of inputs) {
                if (el.value && /^[a-zA-Z]{3,15}\\d{4}$/.test(el.value.trim())) {
                    return el.value.trim();
                }
            }
            if (document.body) {
                const match = document.body.innerText.match(/\\b[a-zA-Z]{3,15}\\d{4}\\b/);
                if (match) return match[0];
            }
            return '';
        """)
        return code if code else None
    except Exception:
        return None


def worker_loop(worker_id, driver):
    global total_attempts
    last_code = None
    stuck_count = 0

    while True:
        try:
            code = extract_code(driver)

            if code and code != last_code:
                last_code = code
                stuck_count = 0

                with lock:
                    total_attempts += 1
                    current_attempt = total_attempts

                    if current_attempt % 50 == 0:
                        found_status = f" | 🏆 확보: {len(found_list)}개 {found_list}" if found_list else ""
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [창 {worker_id+1:02d} | 시도 {current_attempt:06d}회] 현재 코드: {code}{found_status}")

                # 🎉 타겟 조건 검사
                if is_target_code(code):
                    with lock:
                        found_list.append(f"창{worker_id+1:02d}:{code}")
                        print("\n" + "=" * 70)
                        print(f"🎊🎊🎊 [대박!!] 창 {worker_id+1:02d} 에서 목표 코드 포착 완료!! 🎊🎊🎊")
                        print(f"👉 당첨 식별코드 : {code}")
                        print(f"👉 누적 시도 횟수: {current_attempt}회")
                        print(f"👉 발견 시각     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"👉 현재 확보 목록: {found_list}")
                        print(f"🔒 [창 {worker_id+1:02d}]은 코드 보호를 위해 새로고침을 멈추고 대기합니다!")
                        print("=" * 70 + "\n")

                    screenshot_name = f"found_win{worker_id+1}_{code}_{int(time.time())}.png"
                    try:
                        driver.save_screenshot(screenshot_name)
                        print(f"📸 [창 {worker_id+1:02d}] 화면 캡처 저장 완료: {screenshot_name}")
                    except Exception:
                        pass

                    try:
                        for _ in range(6):
                            winsound.Beep(1400, 180)
                            winsound.Beep(1800, 180)
                            time.sleep(0.05)
                    except Exception:
                        pass

                    break

                driver.execute_script("location.reload();")
                time.sleep(0.05)

            else:
                stuck_count += 1
                time.sleep(0.03)

                if stuck_count >= 100:
                    driver.execute_script("location.reload();")
                    stuck_count = 0
                    time.sleep(0.2)

        except Exception:
            time.sleep(0.2)


def main():
    global TARGET_WORDS, TARGET_NUMS, REQUIRE_BOTH

    print("=" * 70)
    print("🖥️  디시 식별코드 커스텀 저격기 (단어/숫자 개별 입력 버전)")
    print("=" * 70)

    # 1. 단어 입력 받기 (쉼표로 구분)
    words_input = input("🎯 단어 입력 (쉼표로 구분, 예: live, with, leave / 없으면 엔터): ").strip()
    if words_input:
        TARGET_WORDS = [w.strip().lower() for w in words_input.split(",") if w.strip()]

    # 2. 숫자 입력 받기 (쉼표로 구분)
    nums_input = input("🎯 숫자 입력 (쉼표로 구분, 예: 1011, 0326 / 없으면 엔터): ").strip()
    if nums_input:
        TARGET_NUMS = [n.strip() for n in nums_input.split(",") if n.strip()]

    # 3. 둘 다 일치해야 하는지 여부 물어보기 (단어와 숫자가 모두 입력된 경우에만 질문)
    if TARGET_WORDS and TARGET_NUMS:
        ans = input("❓ 단어와 숫자 둘 다 맞아여야 하나요? (y = 둘 다, n = 둘 중 하나만 / 기본값 y): ").strip().lower()
        if ans == 'n':
            REQUIRE_BOTH = False
            print(f"👉 설정완료: 단어({TARGET_WORDS}) 또는 숫자({TARGET_NUMS}) **둘 중 하나만** 맞아도 잡습니다.")
        else:
            print(f"👉 설정완료: 단어({TARGET_WORDS})와 숫자({TARGET_NUMS})가 **모두 일치**해야 잡습니다.")
    elif TARGET_WORDS:
        print(f"👉 설정완료: 입력한 단어({TARGET_WORDS}) 중 하나가 포함되면 잡습니다.")
    elif TARGET_NUMS:
        print(f"👉 설정완료: 입력한 숫자({TARGET_NUMS}) 중 하나가 일치하면 잡습니다.")
    else:
        print("⚠️ 경고: 입력된 조건이 없습니다! 아무 코드도 잡히지 않습니다.")

    print("=" * 70)

    # 이전 잔류 프로필 정리
    if os.path.exists("./chrome_server_profiles"):
        try:
            shutil.rmtree("./chrome_server_profiles", ignore_errors=True)
        except Exception:
            pass

    print(f"\n[1/3] 독립 세션 브라우저 {NUM_WORKERS}개 실행 중...")
    drivers = []
    profile_dirs = []

    for i in range(NUM_WORKERS):
        d, p = create_driver(i)
        d.get(SIGNUP_URL)
        drivers.append(d)
        profile_dirs.append(p)

    print("\n" + "#" * 70)
    print(f"⚠️  [2/3] {NUM_WORKERS}개 창에서 각각 가입 단계(식별코드 확인 창)까지 진입하세요.")
    input("👉 모든 준비가 끝났으면 [Enter]를 눌러 레이스를 시작하세요: ")
    print("#" * 70 + "\n")

    print("[3/3] 탐색 가동 중... (로그는 50회 간격으로 갱신됩니다)")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        for idx, d in enumerate(drivers):
            executor.submit(worker_loop, idx, d)

    elapsed = time.time() - start_time
    rate = total_attempts / max(elapsed, 1)
    print(f"\n⏱️ 탐색 완료! 총 소요 시간: {elapsed/60:.1f}분")
    print(f"📊 총 시도 횟수: {total_attempts}회 (초당 평균 약 {rate:.1f}회)")
    print(f"🏆 최종 확보된 코드 목록: {found_list}")
    input("\n가입 완료 후 모든 브라우저를 닫으려면 Enter를 누르세요...")

    for d in drivers:
        try:
            d.quit()
        except Exception:
            pass

    try:
        shutil.rmtree("./chrome_server_profiles", ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
