import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import os
import time
import json
import yt_dlp

# ==========================================
# 1. 설정 및 UI 초기화
# ==========================================

st.set_page_config(layout="wide", page_title="Viral Shorts Master Cloud", page_icon="☁️")

st.markdown("""
<style>
    .report-box { border: 1px solid #ddd; padding: 15px; border-radius: 10px; background-color: #f8f9fa; margin-bottom: 15px; }
    .stButton > button { min-height: 48px; font-weight: bold; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 데이터베이스 및 설정 관리
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
# 3. [핵심] Streamlit Secrets에서 쿠키 생성
# ==========================================

def setup_cookies():
    """
    Streamlit Secrets에 저장된 쿠키 텍스트를 읽어
    임시 cookies.txt 파일을 생성합니다.
    """
    cookie_file = 'cookies.txt'
    
    # 이미 파일이 있으면 패스
    if os.path.exists(cookie_file):
        return cookie_file
        
    # Secrets에 쿠키 데이터가 있는지 확인
    if 'YOUTUBE_COOKIES' in st.secrets:
        try:
            with open(cookie_file, 'w', encoding='utf-8') as f:
                f.write(st.secrets['YOUTUBE_COOKIES'])
            return cookie_file
        except Exception as e:
            st.error(f"쿠키 파일 생성 중 오류: {e}")
            return None
    return None

# ==========================================
# 4. 영상 다운로드 (Cloud 환경 최적화)
# ==========================================

def get_video_data(url):
    # 1. 쿠키 파일 셋팅
    setup_cookies()
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'temp_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
            }
        }
    }

    # 쿠키 파일이 생성되었다면 적용
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        print("⚠️ Warning: 쿠키 파일이 없습니다. (Secrets 설정을 확인하세요)")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # 확장자 유연하게 찾기
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
                 raise Exception("다운로드 실패 (파일 없음)")

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
            return {'error': "🚫 403 Forbidden: Streamlit Secrets에 쿠키를 등록해주세요."}
        return {'error': f"다운로드 오류: {err_msg}"}

def upload_to_gemini(path):
    try:
        video_file = genai.upload_file(path=path)
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)
        if video_file.state.name == "FAILED":
             raise ValueError("Gemini 처리 실패")
        return video_file
    except Exception as e:
        raise e

# ==========================================
# 5. AI 분석 엔진
# ==========================================

def analyze_video_with_meta(api_key, video_path, meta_data):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    video_file = upload_to_gemini(video_path)
    
    prompt = f"""
    이 유튜브 쇼츠 영상을 분석해줘.
    [메타정보] 제목: {meta_data['title']}, 채널: {meta_data['channel']}, 조회수: {meta_data['views']}
    
    아래 양식으로 작성:
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

# ==========================================
# 6. UI 구성
# ==========================================

with st.sidebar:
    st.header("⚙️ 설정")
    # API 키도 Secrets에서 가져오거나 직접 입력
    default_key = st.secrets.get("GEMINI_API_KEY", "")
    api_key_input = st.text_input("Gemini API Key", value=default_key, type="password")
    
    st.divider()
    menu = st.radio("메뉴", ["🆕 영상 분석", "🗄️ 아카이브", "📈 인사이트"])

# [탭 1] 영상 분석
if menu == "🆕 영상 분석":
    st.title("🎬 클라우드 영상 분석기")
    
    # 쿠키 상태 확인 (디버깅용)
    if 'YOUTUBE_COOKIES' in st.secrets:
        st.success("✅ 쿠키 설정이 감지되었습니다. (보안 접속 가능)")
    else:
        st.warning("⚠️ 쿠키 설정이 없습니다. Streamlit Secrets에 'YOUTUBE_COOKIES'를 등록해주세요.")
        
    url = st.text_input("쇼츠 URL 입력")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url or not api_key_input:
            st.error("URL과 API 키 필요")
        else:
            status = st.status("🕵️‍♂️ 작업 진행 중...", expanded=True)
            try:
                status.write("📥 다운로드 중... (쿠키 적용)")
                data = get_video_data(url)
                
                if 'error' in data:
                    st.error(data['error'])
                    status.update(label="실패", state="error")
                else:
                    status.write("👀 AI 분석 중...")
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
    st.header("🗄️ 분석 기록")
    df = pd.read_sql_query("SELECT id, title, views, created_at FROM analyses ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    sel_id = st.number_input("ID 입력", min_value=0)
    if st.button("보기", use_container_width=True):
        res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (sel_id,)).fetchone()
        if res: st.markdown(res[0])

# [탭 3] 인사이트
elif menu == "📈 인사이트":
    st.header("📈 트렌드 & 대본")
    tab1, tab2 = st.tabs(["트렌드 분석", "대본 생성"])
    
    with tab1:
        df = pd.read_sql_query("SELECT title, full_report FROM analyses ORDER BY id DESC LIMIT 20", conn)
        if st.button("🚀 트렌드 분석", use_container_width=True):
            if len(df) < 2: st.warning("데이터 부족")
            else:
                with st.spinner("분석 중..."):
                    combined = "\n".join([f"[{r['title']}]\n{r['full_report']}" for i, r in df.iterrows()])
                    prompt = f"이 영상들의 성공 법칙을 분석해줘.\n{combined}"
                    genai.configure(api_key=api_key_input)
                    res = genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt)
                    
                    c = conn.cursor()
                    c.execute("INSERT INTO insights (analyzed_count, trend_report, created_at) VALUES (?,?,?)", (len(df), res.text, datetime.now()))
                    conn.commit()
                    st.markdown(res.text)

    with tab2:
        topic = st.text_input("주제")
        req = st.text_area("요청사항")
        if st.button("✍️ 대본 생성", use_container_width=True):
            with st.spinner("작성 중..."):
                genai.configure(api_key=api_key_input)
                # 최신 인사이트 반영
                insight = ""
                last = pd.read_sql_query("SELECT trend_report FROM insights ORDER BY id DESC LIMIT 1", conn)
                if not last.empty: insight = last.iloc[0]['trend_report']
                
                prompt = f"주제: {topic}\n요청: {req}\n트렌드참고:\n{insight}\n쇼츠 대본 써줘."
                res = genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt)
                st.markdown(res.text)
