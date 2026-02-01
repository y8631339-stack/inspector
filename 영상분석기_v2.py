import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import os
import time
import json
import yt_dlp
import base64  # [추가됨] 암호문 해독용

# ==========================================
# 1. 설정 및 UI 초기화
# ==========================================

st.set_page_config(layout="wide", page_title="Viral Shorts Master V6", page_icon="🍪")

st.markdown("""
<style>
    .report-box { border: 1px solid #ddd; padding: 15px; border-radius: 10px; background-color: #f8f9fa; margin-bottom: 15px; }
    .stButton > button { min-height: 48px; font-weight: bold; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 데이터베이스 설정
# ==========================================

def init_db():
    conn = sqlite3.connect('viral_shorts.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            channel TEXT,
            views INTEGER,
            publish_date TEXT,
            full_report TEXT,
            created_at TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analyzed_count INTEGER,
            trend_report TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

conn = init_db()

# ==========================================
# 3. [핵심] Base64 쿠키 복원 시스템
# ==========================================

정말 고생이 많으십니다. 이 오류(does not look like a Netscape format cookies file)가 계속 뜨는 이유는 딱 하나입니다.

**"서버가 받은 파일의 '첫 번째 줄'이 # Netscape HTTP Cookie File이라는 문장으로 시작하지 않기 때문"**입니다.

Base64로 변환하고 복호화하는 과정에서 **이 헤더(Header) 부분이 누락되었거나, 숨겨진 공백 문자가 들어갔을 확률이 100%**입니다.

제가 코드로 강제로 헤더를 심어주고, **파일 상태를 눈으로 확인할 수 있는 '진단 기능'**을 넣어서 해결해 드리겠습니다.

✅ 해결책: app.py의 setup_cookies 함수 교체
app.py 파일의 setup_cookies 함수를 아래 코드로 완벽하게 교체해주세요.

이 코드는 쿠키 파일이 어떻게 생겼는지 화면에 직접 보여주고(디버깅), 헤더가 없으면 **강제로 주입(Fix)**합니다.

Python
def setup_cookies():
    """
    [강력한 수정 버전]
    1. Base64 디코딩
    2. 헤더(# Netscape...) 강제 주입
    3. 파일 상태를 화면에 출력하여 진단
    """
    cookie_filename = 'cookies.txt'
    
    # Secrets에서 가져오기
    b64_cookie = st.secrets.get('YOUTUBE_COOKIES_B64')
    
    if not b64_cookie:
        st.error("❌ Secrets에 'YOUTUBE_COOKIES_B64' 키가 없습니다.")
        return

    try:
        # 1. 디코딩 (공백 제거 후 시도)
        decoded_bytes = base64.b64decode(b64_cookie.strip())
        content = decoded_bytes.decode('utf-8', errors='ignore')

        # 2. [핵심] 헤더 검사 및 강제 주입
        # yt-dlp는 첫 줄이 # Netscape HTTP Cookie File 로 시작하지 않으면 에러를 냅니다.
        if "# Netscape HTTP Cookie File" not in content:
            # 기존 내용 앞에 강제로 헤더를 붙입니다.
            content = "# Netscape HTTP Cookie File\n# http://curl.haxx.se/rfc/cookie_file.html\n" + content
            st.warning("⚠️ 쿠키 파일에 헤더가 없어서 강제로 추가했습니다.")

        # 3. 빈 줄 정리 (상단 공백 제거)
        lines = content.split('\n')
        # 첫 줄이 헤더가 되도록 공백 라인 제거
        cleaned_lines = [line for line in lines if line.strip()]
        
        # 다시 합치기
        final_content = '\n'.join(cleaned_lines)
        
        # 4. 파일 저장
        with open(cookie_filename, 'w', encoding='utf-8') as f:
            f.write(final_content)
            
        # ====================================================
        # 🔍 [진단용] 화면에 쿠키 파일 앞부분 출력 (디버깅)
        # 문제가 해결되면 이 부분은 주석 처리하셔도 됩니다.
        st.toast("쿠키 파일 생성 완료!", icon="🍪")
        with st.expander("🔍 생성된 쿠키 파일 미리보기 (상위 5줄)"):
            st.code("\n".join(cleaned_lines[:5]), language='text')
            if not final_content.startswith("# Netscape"):
                 st.error("🚨 여전히 헤더가 잘못되었습니다. 위 미리보기를 확인하세요.")
        # ====================================================

    except Exception as e:
        st.error(f"🍪 쿠키 복원 실패: {e}")
        st.error("Base64 문자열이 올바르게 복사되지 않았을 수 있습니다.")

# ==========================================
# 4. 영상 다운로드 (쿠키 적용)
# ==========================================

def get_video_data(url):
    # 1. 쿠키 파일 복원 시도
    setup_cookies()
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'temp_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['web', 'android', 'ios']}}
    }

    # 복원된 쿠키 파일이 있으면 적용
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        st.toast("⚠️ 쿠키 파일 없이 시도합니다 (403 위험)", icon="⚠️")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # 확장자 유연 찾기
            if not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                for ext in ['.mp4', '.mkv', '.webm', '.3gp']:
                    if os.path.exists(base + ext):
                        filename = base + ext
                        break
                    if os.path.exists("temp_video" + ext):
                        filename = "temp_video" + ext
                        break

            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                 raise Exception("파일 없음 (다운로드 실패)")

            meta_data = {
                'filename': filename,
                'title': info.get('title', 'Unknown Title'),
                'channel': info.get('uploader', 'Unknown Channel'),
                'views': info.get('view_count', 0),
                'date': info.get('upload_date', 'Unknown'),
                'desc': info.get('description', '')[:300]
            }
            return meta_data

    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "Sign in" in err_msg:
            return {'error': "🚫 403 Forbidden: 쿠키 파일 형식이 잘못되었거나 만료되었습니다."}
        return {'error': f"다운로드 오류: {err_msg}"}

def upload_to_gemini(path):
    try:
        video_file = genai.upload_file(path=path)
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)
        if video_file.state.name == "FAILED": raise ValueError("Gemini 처리 실패")
        return video_file
    except Exception as e: raise e

# ==========================================
# 5. AI 분석 및 UI
# ==========================================

def analyze_video_with_meta(api_key, video_path, meta_data):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    video_file = upload_to_gemini(video_path)
    
    prompt = f"""
    이 쇼츠 영상을 분석해줘.
    [메타정보] 제목: {meta_data['title']}, 채널: {meta_data['channel']}, 조회수: {meta_data['views']}
    
    ## 🕵️‍♂️ [{meta_data['title']}] 분석
    ### 1. 📍 핵심 및 데이터
    * 내용: (요약)
    * 데이터 추론: (메타데이터 기반 인기 요인)
    ### 2. 🛠️ 제작 방식
    * 구성: [도입]~[결말]
    * 편집: (자막/컷/사운드)
    ### 3. 🔥 흥행 요인
    * Hook: (초반 요소)
    * Viral Point: (댓글 유도)
    ### 4. 🚀 벤치마킹
    * 적용 포인트: (내 채널 적용법)
    """
    response = model.generate_content([video_file, prompt])
    try: genai.delete_file(video_file.name)
    except: pass
    return response.text

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    # Secrets에서 키 가져오거나 직접 입력
    default_key = st.secrets.get("GEMINI_API_KEY", "")
    api_key_input = st.text_input("Gemini API Key", value=default_key, type="password")
    
    # 쿠키 상태 표시
    if 'YOUTUBE_COOKIES_B64' in st.secrets:
        st.success("🍪 보안 쿠키 설정됨")
    else:
        st.error("⚠️ Secrets에 쿠키 설정 필요")

    st.divider()
    menu = st.radio("메뉴", ["🆕 영상 분석", "🗄️ 아카이브", "📈 인사이트"])

# --- 메인 탭 ---
if menu == "🆕 영상 분석":
    st.title("🎬 영상 심층 분석기 (Cloud)")
    url = st.text_input("쇼츠 URL 입력")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url or not api_key_input:
            st.error("URL과 API 키 확인 필요")
        else:
            status = st.status("🕵️‍♂️ 분석 중...", expanded=True)
            try:
                status.write("📥 다운로드 (보안 접속)...")
                data = get_video_data(url)
                
                if 'error' in data:
                    st.error(data['error'])
                    status.update(label="실패", state="error")
                else:
                    status.write("👀 AI 시청 중...")
                    report = analyze_video_with_meta(api_key_input, data['filename'], data)
                    
                    c = conn.cursor()
                    c.execute("INSERT INTO analyses (url, title, channel, views, publish_date, full_report, created_at) VALUES (?,?,?,?,?,?,?)",
                             (url, data['title'], data['channel'], data['views'], data['date'], report, datetime.now()))
                    conn.commit()
                    
                    if os.path.exists(data['filename']): os.remove(data['filename'])
                    status.update(label="완료!", state="complete", expanded=False)
                    st.markdown(report)
            except Exception as e:
                st.error(str(e))

# [탭 2] 아카이브
elif menu == "🗄️ 아카이브":
    st.header("🗄️ 기록")
    df = pd.read_sql_query("SELECT id, title, views, created_at FROM analyses ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    sel_id = st.number_input("ID", min_value=0)
    if st.button("열기", use_container_width=True):
        res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (sel_id,)).fetchone()
        if res: st.markdown(res[0])

# [탭 3] 인사이트
elif menu == "📈 인사이트":
    st.header("📈 트렌드 & 대본")
    tab1, tab2 = st.tabs(["트렌드", "대본"])
    
    with tab1:
        df = pd.read_sql_query("SELECT title, full_report FROM analyses ORDER BY id DESC LIMIT 20", conn)
        if st.button("🚀 트렌드 분석", use_container_width=True):
            if len(df)<2: st.warning("데이터 부족")
            else:
                with st.spinner("분석 중..."):
                    txt = "\n".join([f"[{r['title']}]\n{r['full_report']}" for i,r in df.iterrows()])
                    genai.configure(api_key=api_key_input)
                    res = genai.GenerativeModel('gemini-2.5-flash').generate_content(f"성공 법칙 분석:\n{txt}")
                    c = conn.cursor()
                    c.execute("INSERT INTO insights (analyzed_count, trend_report, created_at) VALUES (?,?,?)", (len(df), res.text, datetime.now()))
                    conn.commit()
                    st.markdown(res.text)

    with tab2:
        topic = st.text_input("주제")
        req = st.text_area("요청사항")
        if st.button("✍️ 대본 생성", use_container_width=True):
            with st.spinner("작성 중..."):
                last = pd.read_sql_query("SELECT trend_report FROM insights ORDER BY id DESC LIMIT 1", conn)
                ref = last.iloc[0]['trend_report'] if not last.empty else ""
                genai.configure(api_key=api_key_input)
                res = genai.GenerativeModel('gemini-2.5-flash').generate_content(f"주제:{topic}\n요청:{req}\n참고:{ref}\n쇼츠 대본 작성.")
                st.markdown(res.text)

