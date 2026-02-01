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

st.set_page_config(layout="wide", page_title="Viral Shorts Master Final", page_icon="🍪")

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
# 3. [최종 수정] 쿠키 파일 생성 (Raw Text 방식)
# ==========================================

def setup_cookies():
    """
    Secrets에 있는 텍스트를 그대로 cookies.txt 파일로 저장합니다.
    """
    cookie_filename = 'cookies.txt'
    
    # Secrets에서 텍스트 가져오기 (YOUTUBE_COOKIES)
    raw_cookie = st.secrets.get('YOUTUBE_COOKIES')
    
    if raw_cookie:
        try:
            # 양옆 공백만 제거하고 그대로 저장 (UTF-8)
            with open(cookie_filename, 'w', encoding='utf-8') as f:
                f.write(raw_cookie.strip())
            return True
        except Exception as e:
            st.error(f"쿠키 파일 생성 실패: {e}")
            return False
    else:
        st.warning("⚠️ Secrets에 'YOUTUBE_COOKIES'가 없습니다.")
        return False

# ==========================================
# 4. 영상 다운로드
# ==========================================

def get_video_data(url):
    # 1. 쿠키 설정 확인
    setup_cookies()
    
    # 2. 헤더 설정 (사람인 척 위장)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    # 3. 다운로드 옵션 (가장 안전한 설정)
    ydl_opts = {
        # 화질/확장자 따지지 않고 '다운로드 가능한 최고 파일' 선택
        'format': 'best/bestvideo+bestaudio',
        
        # 임시 파일명 고정
        'outtmpl': 'temp_video.%(ext)s',
        
        # 자질구레한 경고 무시
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        
        # 위장 헤더 적용
        'http_headers': headers,
    }

    # 쿠키 파일이 물리적으로 존재하면 적용
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 메타데이터 추출 및 다운로드
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # 4. 파일 찾기 (어떤 확장자로 받아졌든 찾아냄)
            final_filename = None
            
            # (1) yt-dlp가 알려준 파일명이 진짜 있는지 확인
            if os.path.exists(filename):
                final_filename = filename
            else:
                # (2) 없다면 temp_video 이름으로 된 모든 파일 뒤지기
                for ext in ['.mp4', '.webm', '.mkv', '.3gp', '.m4a']:
                    if os.path.exists(f"temp_video{ext}"):
                        final_filename = f"temp_video{ext}"
                        break
            
            # 끝까지 못 찾으면 에러 처리
            if not final_filename:
                 raise Exception(f"파일 다운로드 실패 (경로 못 찾음: {filename})")

            # 성공 데이터 반환
            return {
                'filename': final_filename,
                'title': info.get('title', '제목 없음'),
                'channel': info.get('uploader', '채널명 없음'),
                'views': info.get('view_count', 0),
                'date': info.get('upload_date', '날짜 모름'),
                'desc': info.get('description', '')[:300]
            }

    except Exception as e:
        # 에러 메시지를 문자열로 변환
        err_msg = str(e)
        
        # 403 에러가 또 뜨면 사용자에게 알림
        if "403" in err_msg or "Sign in" in err_msg:
             return {'error': "🚫 유튜브가 차단했습니다. (403 Forbidden)\n[해결] PC에서 다시 쿠키를 추출해야 합니다."}
        
        # 기타 에러 반환
        return {'error': f"⚠️ 다운로드 에러 발생: {err_msg}"}
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
    default_key = st.secrets.get("GEMINI_API_KEY", "")
    api_key_input = st.text_input("Gemini API Key", value=default_key, type="password")
    
    if st.button("쿠키 상태 확인"):
        if 'YOUTUBE_COOKIES' in st.secrets:
            st.success("Secrets에서 쿠키를 찾았습니다!")
            # 내용 미리보기 (첫 줄 확인)
            first_line = st.secrets['YOUTUBE_COOKIES'].strip().split('\n')[0]
            st.info(f"첫 줄: {first_line}")
            if "# Netscape" not in first_line:
                st.error("첫 줄이 # Netscape로 시작하지 않습니다. 복사를 다시 해주세요.")
        else:
            st.error("Secrets에 YOUTUBE_COOKIES가 없습니다.")

    st.divider()
    menu = st.radio("메뉴", ["🆕 영상 분석", "🗄️ 아카이브", "📈 인사이트"])

# --- 메인 ---
if menu == "🆕 영상 분석":
    st.title("🎬 영상 심층 분석기 (Final)")
    url = st.text_input("쇼츠 URL 입력")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url or not api_key_input:
            st.error("URL과 API 키 확인 필요")
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

# (나머지 탭 코드는 동일하므로 생략하지 않고 포함)
elif menu == "🗄️ 아카이브":
    st.header("🗄️ 기록")
    df = pd.read_sql_query("SELECT id, title, views, created_at FROM analyses ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    sel_id = st.number_input("ID", min_value=0)
    if st.button("열기", use_container_width=True):
        res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (sel_id,)).fetchone()
        if res: st.markdown(res[0])

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








