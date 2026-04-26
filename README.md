# Cheers AI Agent

Lightyear에서 영수증을 자동으로 검색하고 PC에 저장해주는 도구입니다.

---

## 처음 설치하기 (최초 1회만)

### 1단계 — Python 설치 확인

먼저 Python이 설치되어 있는지 확인합니다.  
시작 메뉴에서 **PowerShell** 또는 **명령 프롬프트**를 열고 아래를 입력하세요:

```
python --version
```

`Python 3.10` 이상이 표시되면 다음 단계로 넘어가세요.  
없으면 [python.org](https://www.python.org/downloads/) 에서 설치하세요. 설치 시 **"Add Python to PATH"** 체크박스를 반드시 체크해야 합니다.

---

### 2단계 — 코드 다운로드

[이 링크](https://github.com/seongwoo15/cheers-ai-agent/archive/refs/heads/main.zip)를 눌러 ZIP 파일을 다운로드하고 원하는 폴더에 압축을 풀어주세요.

---

### 3단계 — 가상환경 만들기

PowerShell을 열고, 압축을 푼 폴더로 이동합니다.  
예를 들어 바탕화면에 폴더가 있다면:

```
cd C:\Users\내이름\Desktop\cheers-ai-agent-main
```

그 다음 아래 명령어를 순서대로 실행하세요:

```
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

> 설치에 몇 분 걸릴 수 있습니다. 기다려 주세요.

---

## 매일 사용하기

### 1단계 — 서버 시작

PowerShell을 열고 프로그램 폴더로 이동한 뒤:

```
.\venv\Scripts\activate
python mcp_server.py
```

아래와 같은 메시지가 뜨면 정상입니다:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> PowerShell 창을 닫으면 서버가 꺼집니다. 사용하는 동안 창을 열어두세요.

---

### 2단계 — 브라우저에서 접속

크롬/엣지 브라우저를 열고 주소창에 입력:

```
http://localhost:8000
```

---

### 3단계 — 영수증 검색 및 다운로드

1. **Supplier** — 거래처 이름 입력 (비워두면 전체 검색)
2. **Classes** — 분류 입력 (예: `Products - Beverages`)
3. **날짜** — 시작일과 종료일 입력 (형식: `01/10/2025`)
4. **영수증 검색 및 분석** 버튼 클릭
   - 자동으로 크롬 창이 열리고 Lightyear에 접속합니다
   - 처음 실행 시 Lightyear 로그인이 필요합니다 (이후 자동 유지)
5. 검색 완료 후 **모든 영수증 PC에 저장하기** 버튼 클릭
6. 다운로드된 파일은 프로그램 폴더 안의 `downloads` 폴더에 저장됩니다

---

## 자주 묻는 질문

**Q. "python은 내부 또는 외부 명령이 아닙니다" 라고 뜨면?**  
Python 설치 시 "Add Python to PATH"를 체크하지 않은 경우입니다. Python을 다시 설치하면서 체크해주세요.

**Q. 크롬 창이 안 열리면?**  
`playwright install chromium` 명령어를 다시 실행해보세요.

**Q. 검색은 됐는데 다운로드가 안 되면?**  
Lightyear 로그인이 되어 있는지 크롬 창에서 확인하세요.

**Q. 서버를 종료하려면?**  
PowerShell 창에서 `Ctrl + C` 를 누르세요.
