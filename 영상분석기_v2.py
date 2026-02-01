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

st.set_page_config(layout="wide", page_title="Viral Shorts Master V5", page_icon="📱")

# 모바일 친화적 CSS 및 스타일링
st.markdown("""
<style>
    .report-box { border: 1px solid #ddd; padding: 15px; border-radius: 10px; background-color: #f8f9fa; margin-bottom: 15px; }
    .stButton > button { min-height: 48px; font-weight: bold; border-radius: 8px; }
    .meta-tag { background-color: #eee; padding: 4px 8px; border-radius: 5px; font-size: 0.85em; margin-right: 5px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 데이터베이스 및 설정 관리
# ==========================================

def init_db():
    conn = sqlite3.connect('viral_shorts.db', check_same_thread=False)
    c = conn.cursor()
    
    # 1) 영상 분석 데이터 테이블
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
    
    # 2) 인사이트(트렌드) 데이터 테이블
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
# 3. 영상 다운로드 및 처리 (403 우회 기능 포함)
# ==========================================

def get_video_data(url):
    """
    yt-dlp를 사용하여 영상 메타데이터 추출 및 다운로드
    cookies.txt가 있으면 자동 적용, 없으면 모바일 클라이언트로 위장
    """
    # 기본 설정: iOS/Android 클라이언트로 위장하여 차단 회피
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'temp_video.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'player_skip': ['webpage', 'configs', 'js'],
            }
        },
        'nocheckcertificate': True,
    }

    # cookies.txt 파일이 존재하면 적용 (가장 확실한 우회법)
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 메타데이터 추출 및 다운로드
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # 실제 생성된 파일명 찾기 (확장자가 다를 수 있음)
            if not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                for ext in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base + ext):
                        filename = base + ext
                        break
            
            # 파일 검증
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                 raise Exception("다운로드 실패: 파일 크기가 0이거나 생성되지 않음 (403 차단 가능성)")

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
        if "403" in err_msg or "Forbidden" in err_msg:
            return {'error': "🚫 유튜브 접근이 차단되었습니다. (cookies.txt 파일을 폴더에 추가해주세요)"}
        return {'error': f"다운로드 오류: {err_msg}"}

def upload_to_gemini(path):
    try:
        video_file = genai.upload_file(path=path)
        # 처리 대기
        while video_file.state.name == "PROCESSING":
            time.sleep(1)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
            raise ValueError("Gemini 서버에서 비디오 처리에 실패했습니다.")
        return video_file
    except Exception as e:
        raise e

# ==========================================
# 4. AI 분석 엔진
# ==========================================

def analyze_video_with_meta(api_key, video_path, meta_data):
    genai.configure(api_key=api_key)
    # 2.5 버전 사용 (사용 불가능 시 'gemini-1.5-flash'로 변경)
    model = genai.GenerativeModel('gemini-2.5-flash') 
    
    video_file = upload_to_gemini(video_path)
    
    prompt = f"""
    이 유튜브 쇼츠 영상을 심층 분석해줘.
    [메타데이터]
    - 제목: {meta_data['title']}
    - 채널: {meta_data['channel']}
    - 조회수: {meta_data['views']}
    
    반드시 아래 포맷으로 작성해줘:
    
    ## 🕵️‍♂️ [{meta_data['title']}] 심층 분석
    
    ### 1. 📍 소스 및 데이터 분석
    * **핵심 내용:** (영상 내용 요약)
    * **데이터 인사이트:** (조회수나 반응을 통해 본 인기 요인)

    ### 2. 🛠️ 제작 및 편집 방식
    * **구성:** [도입] ~ [전개] ~ [결말]
    * **편집:** (자막 스타일, BGM, 컷 전환 속도 등)

    ### 3. 🔥 흥행 성공 요인
    * **Hook (초반 3초):** (시청 이탈을 막은 요소)
    * **Dopamine Hit:** (시청자가 느낀 감정적 보상)
    * **Viral Point:** (댓글 참여 유도 포인트)

    ### 4. 🚀 벤치마킹 실행 가이드
    * **검색 키워드:** (유사 소재 발굴용)
    * **적용 팁:** (내 채널에 적용 시 주의사항)
    """
    
    response = model.generate_content([video_file, prompt])
    
    # 클라우드 파일 삭제 (비용 절감 및 정리)
    try:
        genai.delete_file(video_file.name)
    except:
        pass
        
    return response.text

# ==========================================
# 5. UI 구성 (사이드바 & 메인)
# ==========================================

with st.sidebar:
    st.header("⚙️ 설정 & 메뉴")
    
    # API 키 자동 로드
    saved_key = load_api_key()
    api_key_input = st.text_input("Gemini API Key", value=saved_key, type="password")
    
    if st.button("💾 API 키 저장", use_container_width=True):
        save_api_key(api_key_input)
        st.success("API 키가 저장되었습니다.")
        time.sleep(0.5)
        st.rerun()
    
    st.markdown("---")
    menu = st.radio("메뉴 선택", ["🆕 영상 분석", "🗄️ 분석 아카이브", "📈 인사이트 & 대본"])

# --- [탭 1] 영상 분석 ---
if menu == "🆕 영상 분석":
    st.title("🎬 영상 심층 분석")
    st.caption("URL을 입력하면 다운로드 후 AI가 분석합니다.")
    
    url = st.text_input("유튜브 쇼츠 URL 입력", placeholder="https://youtube.com/shorts/...")
    
    if st.button("🚀 분석 시작", use_container_width=True):
        if not url or not api_key_input:
            st.warning("URL과 API 키를 확인해주세요.")
        else:
            # 진행 상태 표시줄
            status = st.status("🕵️‍♂️ 분석 프로세스 시작...", expanded=True)
            
            try:
                # 1. 다운로드
                status.write("📥 1/3 영상 다운로드 및 메타데이터 수집 중...")
                data = get_video_data(url)
                
                if 'error' in data:
                    status.update(label="❌ 오류 발생", state="error")
                    st.error(data['error'])
                else:
                    # 2. AI 분석
                    status.write("👀 2/3 AI가 영상을 시청하고 보고서를 작성 중...")
                    report = analyze_video_with_meta(api_key_input, data['filename'], data)
                    
                    # 3. DB 저장
                    status.write("💾 3/3 데이터베이스에 저장 중...")
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO analyses (url, title, channel, views, publish_date, full_report, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (url, data['title'], data['channel'], data['views'], data['date'], report, datetime.now()))
                    conn.commit()
                    
                    # 임시 파일 정리
                    if os.path.exists(data['filename']):
                        os.remove(data['filename'])
                        
                    status.update(label="✅ 분석 완료!", state="complete", expanded=False)
                    
                    # 결과 출력
                    st.divider()
                    st.subheader(f"📺 {data['title']}")
                    st.caption(f"채널: {data['channel']} | 조회수: {data['views']:,}회 | 게시일: {data['date']}")
                    st.markdown(report)
                    
            except Exception as e:
                status.update(label="❌ 시스템 오류", state="error")
                st.error(f"예기치 못한 오류: {str(e)}")
                # 파일 정리 시도
                if 'data' in locals() and 'filename' in data and os.path.exists(data['filename']):
                    os.remove(data['filename'])

# --- [탭 2] 아카이브 ---
elif menu == "🗄️ 분석 아카이브":
    st.title("🗄️ 분석 기록 보관소")
    
    # DB 조회
    try:
        df = pd.read_sql_query("SELECT id, title, channel, views, created_at FROM analyses ORDER BY id DESC", conn)
        
        if df.empty:
            st.info("저장된 데이터가 없습니다.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            col1, col2 = st.columns([1, 3])
            with col1:
                selected_id = st.number_input("조회할 ID 입력", min_value=0, step=1)
            with col2:
                if st.button("📄 리포트 열기", use_container_width=True):
                    res = conn.execute("SELECT full_report FROM analyses WHERE id=?", (selected_id,)).fetchone()
                    if res:
                        st.markdown("---")
                        st.markdown(res[0])
                    else:
                        st.warning("해당 ID의 리포트가 없습니다.")
    except Exception as e:
        st.error(f"DB 오류: {e}")

# --- [탭 3] 인사이트 & 대본 ---
elif menu == "📈 인사이트 & 대본":
    st.title("📈 AI 트렌드 인사이트 & 대본")
    
    tab1, tab2 = st.tabs(["📊 트렌드 분석", "✍️ 대본 생성"])
    
    # [서브탭 1] 트렌드 분석
    with tab1:
        st.subheader("저장된 인사이트 불러오기")
        insight_df = pd.read_sql_query("SELECT id, analyzed_count, created_at, trend_report FROM insights ORDER BY id DESC", conn)
        
        if not insight_df.empty:
            st.dataframe(insight_df[['id', 'analyzed_count', 'created_at']], use_container_width=True)
            i_id = st.number_input("인사이트 ID 조회", min_value=0)
            if st.button("📂 인사이트 기록 열기", use_container_width=True):
                rec = insight_df[insight_df['id'] == i_id]
                if not rec.empty:
                    st.markdown(rec.iloc[0]['trend_report'])
        else:
            st.info("저장된 트렌드 분석 기록이 없습니다.")
            
        st.divider()
        st.subheader("🔥 새로운 트렌드 추출하기")
        
        # 분석 대상 데이터 로드
        recent_df = pd.read_sql_query("SELECT title, full_report FROM analyses ORDER BY id DESC LIMIT 20", conn)
        
        if len(recent_df) < 2:
            st.warning("분석할 데이터가 부족합니다. 최소 2개 이상의 영상을 먼저 분석해주세요.")
        else:
            if st.button(f"🚀 최근 {len(recent_df)}개 영상으로 트렌드 분석 시작", use_container_width=True):
                with st.spinner("AI가 성공 패턴을 도출하고 있습니다..."):
                    try:
                        combined_text = "\n".join([f"[{row['title']}]\n{row['full_report']}" for i, row in recent_df.iterrows()])
                        
                        trend_prompt = f"""
                        최근 분석한 {len(recent_df)}개의 바이럴 영상 리포트들을 종합하여 '현재의 성공 법칙'을 도출해줘.
                        
                        [분석 요청 사항]
                        1. 🔑 **공통적으로 사용된 소재/키워드**
                        2. 🎣 **초반 3초 훅(Hook)의 공통 패턴**
                        3. 😂 **시청자 감정 코드 (Dopamine Point)**
                        4. 🚀 **실행 가능한 액션 플랜 3가지**
                        
                        [데이터]
                        {combined_text}
                        """
                        
                        genai.configure(api_key=api_key_input)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        res = model.generate_content(trend_prompt)
                        
                        # DB 저장
                        c = conn.cursor()
                        c.execute("INSERT INTO insights (analyzed_count, trend_report, created_at) VALUES (?, ?, ?)",
                                 (len(recent_df), res.text, datetime.now()))
                        conn.commit()
                        
                        st.success("분석 완료! DB에 저장되었습니다.")
                        st.markdown(res.text)
                        
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

    # [서브탭 2] 대본 생성
    with tab2:
        st.subheader("✨ 트렌드 반영 대본 작가")
        
        col1, col2 = st.columns(2)
        with col1:
            topic = st.text_input("주제 (예: 자취생 요리, 헬스장 공감)")
        with col2:
            tone = st.selectbox("톤앤매너", ["유머러스/B급", "감동/진지", "정보전달/깔끔", "반말/친구처럼"])
            
        add_req = st.text_area("추가 요청사항 (디테일한 요구를 적어주세요)", placeholder="예: 마지막에 반전을 넣어줘, 유행어를 섞어줘", height=100)
        
        if st.button("✍️ 대본 생성하기", use_container_width=True):
            if not topic:
                st.warning("주제를 입력해주세요.")
            else:
                with st.spinner("천만 작가가 대본을 쓰고 있습니다..."):
                    try:
                        # DB에서 최신 인사이트 가져오기 (없으면 생략)
                        insight_context = ""
                        last_insight = pd.read_sql_query("SELECT trend_report FROM insights ORDER BY id DESC LIMIT 1", conn)
                        if not last_insight.empty:
                            insight_context = f"[참고할 최신 트렌드 분석]\n{last_insight.iloc[0]['trend_report']}\n"
                        
                        script_prompt = f"""
                        너는 천만 유튜브 채널의 메인 작가야.
                        아래의 최신 트렌드와 요청사항을 반영하여 40초~50초 분량의 쇼츠 대본을 작성해줘.
                        
                        {insight_context}
                        
                        [요청사항]
                        - 주제: {topic}
                        - 톤앤매너: {tone}
                        - 추가요청: {add_req}
                        
                        [필수 구조]
                        1. **제목 & 썸네일 카피 추천**
                        2. **[0~3초] 도입부 (Hook):** 시각적 지시문과 대사 필수 (이탈 방지)
                        3. **[본론] 전개:** 빠른 템포, 컷 전환 지시 포함
                        4. **[결말] 마무리:** 반전 요소 또는 댓글 유도 질문
                        """
                        
                        genai.configure(api_key=api_key_input)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        script_res = model.generate_content(script_prompt)
                        
                        st.markdown(script_res.text)
                        
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
