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
# 1. 설정 및 데이터베이스 초기화
# ==========================================

st.set_page_config(layout="wide", page_title="Viral Shorts Master V4", page_icon="📱")

# 모바일 친화적 스타일링
st.markdown("""
<style>
    .report-box { border: 1px solid #ddd; padding: 15px; border-radius: 10px; background-color: #f8f9fa; margin-bottom: 10px;}
    .mobile-font { font-size: 1.1em; }
    /* 모바일에서 버튼 터치 영역 확보 */
    .stButton > button { min-height: 45px; }
</style>
""", unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('viral_shorts.db', check_same_thread=False)
    c = conn.cursor()
    
    # 1) 영상 분석 테이블
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
    
    # 2) [New] 인사이트 저장 테이블
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

# API 키 관리
CONFIG_FILE = 'secrets.json'

def load_api_key():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f).get('api_key', '')
        except:
            return ''
    return ''

def save_api_key(key):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'api_key': key}, f)

# ==========================================
# 2. 영상 다운로드 및 처리 (모바일 클라이언트 위장)
# ==========================================

def get_video_data(url):
    """
    yt-dlp 개선판: 쿠키 지원 및 강력한 차단 우회 기능 포함
    """
    # 1. 기본 설정
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'temp_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        # 중요: 403 에러 방지를 위한 클라이언트 위장 (iOS가 현재 가장 안정적)
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'player_skip': ['webpage', 'configs', 'js'],
            }
        },
        'nocheckcertificate': True,
    }

    # 2. 쿠키 파일이 폴더에 있다면 자동으로 적용 (치트키)
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # 파일명 보정 (확장자 매칭)
            if not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                for ext in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base + ext):
                        filename = base + ext
                        break
            
            # 파일 크기 체크 (0바이트면 차단된 것)
            if os.path.exists(filename) and os.path.getsize(filename) == 0:
                 raise Exception("다운로드된 파일이 빕니다. (403 차단됨 -> cookies.txt 필요)")

            meta_data = {
                'filename': filename,
                'title': info.get('title', 'Unknown'),
                'channel': info.get('uploader', 'Unknown'),
                'views': info.get('view_count', 0),
                'date': info.get('upload_date', ''),
                'desc': info.get('description', '')[:300]
            }
            return meta_data

    except Exception as e:
        # 에러 메시지에 힌트 추가
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            return {'error': "🚫 유튜브가 접속을 차단했습니다. (해결책: 폴더에 cookies.txt 파일을 넣어주세요)"}
        return {'error': f"다운로드 실패: {error_msg}"}

# ==========================================
# 3. AI 분석 엔진
# ==========================================

def analyze_video_with_meta(api_key, video_path, meta_data):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    video_file = upload_to_gemini(video_path)
    
    prompt = f"""
    이 쇼츠 영상을 분석해줘.
    [메타정보] 제목: {meta_data['title']}, 채널: {meta_data['channel']}, 조회수: {meta_data['views']}
    
    아래 양식으로 작성:
    ## 🕵️‍♂️ [{meta_data['title']}] 분석
    ### 1. 📍 핵심 및 출처
    * 내용: (요약)
    * 데이터 추론: (메타데이터 기반 분석)
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
    genai.delete_file(video_file.name)
    return response.text

# ==========================================
# 4. UI 구성 (모바일 최적화)
# ==========================================

# 사이드바 (API 키 설정)
with st.sidebar:
    st.title("⚙️ 설정")
    saved_key = load_api_key()
    api_key_input = st.text_input("Gemini API Key", value=saved_key, type="password")
    if st.button("💾 키 저장", use_container_width=True):
        save_api_key(api_key_input)
        st.success("저장됨")
        st.rerun()
    
    st.divider()
    menu = st.radio("메뉴", ["🆕 영상 분석", "🗄️ 아카이브", "📈 인사이트 (DB)"])

# [탭 1] 영상 분석
if menu == "🆕 영상 분석":
    st.subheader("🎬 영상 분석")
    url = st.text_input("쇼츠 URL 입력")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url or not api_key_input:
            st.error("URL과 API 키 필요")
        else:
            status = st.status("🕵️‍♂️ 작업 진행 중...", expanded=True)
            try:
                status.write("📥 다운로드 중...")
                data = get_video_data(url)
                
                if 'error' in data:
                    st.error(data['error'])
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
    st.subheader("🗄️ 분석 기록")
    df = pd.read_sql_query("SELECT id, title, views, created_at FROM analyses ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    sel_id = st.number_input("ID 입력", min_value=0)
    if st.button("리포트 보기", use_container_width=True):
        res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (sel_id,)).fetchone()
        if res: st.markdown(res[0])

# [탭 3] 인사이트 (기능 추가됨)
elif menu == "📈 인사이트 (DB)":
    st.subheader("📈 AI 트렌드 인사이트")
    
    # 1. 과거 인사이트 기록 불러오기 (New)
    with st.expander("🗂️ 저장된 인사이트 기록 보기"):
        insight_df = pd.read_sql_query("SELECT id, analyzed_count, created_at, trend_report FROM insights ORDER BY id DESC", conn)
        if not insight_df.empty:
            st.dataframe(insight_df[['id', 'analyzed_count', 'created_at']], use_container_width=True)
            i_id = st.number_input("조회할 인사이트 ID", min_value=0)
            if st.button("기록 열기", use_container_width=True):
                rec = insight_df[insight_df['id'] == i_id]
                if not rec.empty:
                    st.markdown(rec.iloc[0]['trend_report'])
        else:
            st.info("저장된 인사이트가 없습니다.")

    st.divider()

    # 2. 새로운 인사이트 생성
    st.write("📊 **새로운 트렌드 분석**")
    df = pd.read_sql_query("SELECT title, full_report FROM analyses ORDER BY id DESC LIMIT 20", conn)
    
    if st.button(f"🚀 분석된 영상 {len(df)}개로 트렌드 추출", use_container_width=True):
        if len(df) < 2:
            st.warning("데이터가 너무 적습니다 (최소 2개 이상)")
        else:
            with st.spinner("AI가 공통 성공 법칙을 도출 중입니다..."):
                combined = "\n".join([f"[{row['title']}]\n{row['full_report']}" for i, row in df.iterrows()])
                prompt = f"""
                최근 분석한 {len(df)}개 영상들의 공통된 성공 법칙을 분석해줘.
                1. 🔑 공통 키워드/소재
                2. 🎣 초반 3초 훅(Hook) 패턴
                3. 😂 시청자 감정 코드
                4. 🚀 벤치마킹 액션 플랜 3가지
                
                [데이터]
                {combined}
                """
                genai.configure(api_key=api_key_input)
                res = genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt)
                
                # DB 저장 (New)
                c = conn.cursor()
                c.execute("INSERT INTO insights (analyzed_count, trend_report, created_at) VALUES (?, ?, ?)",
                         (len(df), res.text, datetime.now()))
                conn.commit()
                
                st.success("분석 완료 및 저장됨!")
                st.markdown(res.text)

    st.divider()

    # 3. 대본 생성 (추가 요청사항 기능 New)
    st.subheader("✍️ 트렌드 반영 대본 생성")
    topic = st.text_input("주제 (예: 편의점 진상)")
    
    # 추가 요청사항 입력 필드 (New)
    add_req = st.text_area("추가 요청사항 (예: 반말 모드, B급 감성, 마지막에 반전 넣어줘)", height=80)
    
    if st.button("✨ 대본 생성", use_container_width=True):
        if not topic: st.warning("주제를 입력하세요")
        else:
            with st.spinner("대본 작성 중..."):
                script_prompt = f"""
                분석된 성공 법칙을 적용해 쇼츠 대본을 써줘.
                주제: {topic}
                
                [사용자 추가 요청사항]
                {add_req if add_req else "없음 (알아서 잘 써줘)"}
                
                구조:
                1. [0~3초] 훅 (지시문 포함)
                2. [본론] 빠른 전개
                3. [결말] 반전/질문
                """
                genai.configure(api_key=api_key_input)
                res = genai.GenerativeModel('gemini-2.5-flash').generate_content(script_prompt)
                st.markdown(res.text)