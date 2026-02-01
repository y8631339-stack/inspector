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
    setup_cookies() # 쿠키 생성
    
    ydl_opts = {
        # [핵심] 합치기 시도하되, 없으면 단일파일 사용 (로컬 코드 로직 유지)
        'format': 'bestvideo+bestaudio/best', 
        'outtmpl': 'temp_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        
        # [로컬 코드의 장점] 안드로이드 위장
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
        'merge_output_format': 'mp4',
    }
    
    # 쿠키가 있으면 적용 (클라우드 환경 필수)
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # [로컬 코드의 장점] 파일 찾기 로직 (확장자 유연 대응)
            final_filename = None
            if os.path.exists(filename):
                final_filename = filename
            else:
                # 파일명이 다를 경우를 대비한 탐색
                base_name = os.path.splitext('temp_video')[0]
                for ext in ['.mp4', '.mkv', '.webm', '.3gp']:
                    if os.path.exists(base_name + ext):
                        final_filename = base_name + ext
                        break
            
            if not final_filename or os.path.getsize(final_filename) == 0:
                 raise Exception("다운로드 실패 (파일 없음)")

            meta_data = {
                'filename': final_filename,
                'title': info.get('title', 'Unknown'),
                'channel': info.get('uploader', 'Unknown'),
                'views': info.get('view_count', 0),
                'date': info.get('upload_date', 'Unknown'),
                'desc': info.get('description', '')[:500]
            }
            return meta_data
            
    except Exception as e:
        # 클라우드에서 자주 발생하는 403 에러 안내 추가
        if "403" in str(e):
             return {'error': "🚫 403 차단됨: Secrets에 최신 쿠키값을 업데이트해주세요."}
        return {'error': str(e)}

def upload_to_gemini(path):
    video_file = genai.upload_file(path=path)
    while video_file.state.name == "PROCESSING":
        time.sleep(1)
        video_file = genai.get_file(video_file.name)
    if video_file.state.name == "FAILED": raise ValueError("Gemini 처리 실패")
    return video_file

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
