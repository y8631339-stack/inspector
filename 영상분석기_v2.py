import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import os
import time
import yt_dlp

# ==========================================
# 1. 설정 및 초기화
# ==========================================

st.set_page_config(layout="wide", page_title="YouTube Viral Analyzer V3", page_icon="🕵️‍♂️")

st.markdown("""
<style>
    .report-box { border: 1px solid #ddd; padding: 20px; border-radius: 10px; background-color: #f9f9f9; }
</style>
""", unsafe_allow_html=True)

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
    conn.commit()
    return conn

conn = init_db()

# [수정] Secrets.json 대신 st.secrets 사용 (클라우드 호환)
def load_api_key():
    return st.secrets.get("GEMINI_API_KEY", "")

# [수정] 쿠키 파일 생성 (클라우드 차단 방지 필수)
def setup_cookies():
    raw_cookie = st.secrets.get('YOUTUBE_COOKIES')
    if raw_cookie:
        with open('cookies.txt', 'w', encoding='utf-8') as f:
            f.write(raw_cookie.strip())

# ==========================================
# 2. 영상 다운로드 (로컬 코드 + 쿠키 기능 병합)
# ==========================================

def get_video_data(url):
    # 1. 쿠키 파일 생성 (헤더 깨짐 방지 처리 포함)
    raw_cookie = st.secrets.get('YOUTUBE_COOKIES')
    if raw_cookie:
        # 공백 제거 후 Netscape 헤더 확인/추가
        content = raw_cookie.strip()
        if not content.startswith("# Netscape"):
            content = "# Netscape HTTP Cookie File\n" + content
        with open('cookies.txt', 'w', encoding='utf-8') as f:
            f.write(content)

    # 2. 헤더 설정 (차단 방지)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # 3. [최종 수정] 가장 단순하고 강력한 다운로드 옵션
    ydl_opts = {
        # [핵심] 'best'는 합체 과정 없이 존재하는 단일 파일 중 최고 화질을 가져옵니다.
        # 화질이 720p/360p 일 수 있지만, 에러가 날 확률이 0%에 가깝습니다.
        'format': 'best', 
        
        'outtmpl': 'temp_video.%(ext)s', # 확장자 알아서 결정
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'http_headers': headers,
    }

    # 쿠키 적용
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 다운로드 실행
            info = ydl.extract_info(url, download=True)
            
            # 정보가 없으면 에러
            if not info:
                 raise Exception("영상 정보를 가져올 수 없습니다.")

            # 저장된 파일명 확인
            filename = ydl.prepare_filename(info)
            
            # 4. 파일 찾기 (확장자가 webm, mkv 등으로 바뀔 수 있음)
            final_filename = None
            if os.path.exists(filename):
                final_filename = filename
            else:
                # 파일명이 다를 경우 temp_video.* 패턴으로 검색
                for ext in ['.mp4', '.webm', '.mkv', '.3gp']:
                    candidate = f"temp_video{ext}"
                    if os.path.exists(candidate):
                        final_filename = candidate
                        break
            
            if not final_filename:
                 raise Exception(f"파일은 받았는데 찾을 수가 없습니다. (경로: {filename})")

            return {
                'filename': final_filename,
                'title': info.get('title', '제목 없음'),
                'channel': info.get('uploader', '채널명 없음'),
                'views': info.get('view_count', 0),
                'date': info.get('upload_date', '날짜 모름'),
                'desc': info.get('description', '')[:300]
            }

    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg:
             return {'error': "🚫 403 차단: 쿠키가 만료되었습니다. (PC 시크릿모드에서 재추출 필요)"}
        return {'error': f"다운로드 오류: {err_msg}"}

# ==========================================
# 3. AI 및 UI
# ==========================================

def analyze_video_with_meta(api_key, video_path, meta_data):
    genai.configure(api_key=api_key)
    # [수정] 모델명 확인 (2.5가 아직 정식 출시 전이면 1.5로 에러 날 수 있음)
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
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

# --- UI 부분 ---
with st.sidebar:
    st.header("⚙️ 설정")
    # Secrets에서 가져오기
    default_key = load_api_key()
    api_key_input = st.text_input("Gemini API Key", value=default_key, type="password")
    
    st.divider()
    menu = st.radio("메뉴", ["🆕 영상 분석", "🗄️ 아카이브"])

if menu == "🆕 영상 분석":
    st.title("🎬 영상 심층 분석기 (Cloud Ver.)")
    url = st.text_input("쇼츠 URL 입력")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url:
            st.error("URL을 입력하세요.")
        else:
            status = st.status("🕵️‍♂️ 분석 중...", expanded=True)
            try:
                status.write("📥 다운로드 (쿠키 적용)...")
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

elif menu == "🗄️ 아카이브":
    st.header("🗄️ 기록")
    df = pd.read_sql_query("SELECT id, title, views, created_at FROM analyses ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    sel_id = st.number_input("ID", min_value=0)
    if st.button("열기", use_container_width=True):
        res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (sel_id,)).fetchone()
        if res: st.markdown(res[0])

