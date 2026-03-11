import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import os
import ast
import json

# 페이지 설정
st.set_page_config(page_title="Nemostore 상가 분석 프로", layout="wide", initial_sidebar_state="expanded")

# --- 스타일 설정 ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stCard {
        border-radius: 10px;
        padding: 10px;
        background-color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .stCard:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    .metric-container {
        background: white;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #007bff;
    }
</style>
""", unsafe_allow_html=True)

# --- 데이터 로드 및 전처리 ---
@st.cache_data
def load_data():
    conn = sqlite3.connect('nemostore.db')
    df = pd.read_sql_query("SELECT * FROM items", conn)
    conn.close()
    
    # 데이터 필드 정제
    df['deposit'] = df['deposit'].fillna(0)
    df['monthlyRent'] = df['monthlyRent'].fillna(0)
    df['premium'] = df['premium'].fillna(0)
    df['maintenanceFee'] = df['maintenanceFee'].fillna(0)
    df['size'] = df['size'].fillna(0)
    
    # 사진 URL 파싱 (문자열 -> 리스트)
    def parse_urls(url_str):
        if not url_str or pd.isna(url_str):
            return []
        try:
            return ast.literal_eval(url_str)
        except:
            try:
                return json.loads(url_str)
            except:
                return []

    df['small_images'] = df['smallPhotoUrls'].apply(parse_urls)
    df['large_images'] = df['originPhotoUrls'].apply(parse_urls)
    df['thumbnail'] = df['small_images'].apply(lambda x: x[0] if x else "https://via.placeholder.com/150")
    
    # 가상 좌표 생성 (서울역/후암동 인근: Lat 37.545~37.555, Lng 126.965~126.975)
    np.random.seed(42)
    df['lat'] = np.random.uniform(37.545, 37.555, size=len(df))
    df['lng'] = np.random.uniform(126.965, 126.975, size=len(df))
    
    # 층수 범주화 개선
    def categorize_floor(floor):
        if floor == 1: return '1층'
        elif floor < 0: return '지하'
        elif floor > 1: return '고층(2층이상)'
        else: return '기타/미지정'
    df['floor_type'] = df['floor'].apply(categorize_floor)
    
    # ㎡당 가격 계산 (단위 면적당 월세)
    df['rent_per_size'] = df.apply(lambda row: row['monthlyRent'] / row['size'] if row['size'] > 0 else 0, axis=1)
    
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# --- 사이드바 필터링 ---
with st.sidebar:
    st.title("🏙️ Nemostore Pro")
    st.header("🔍 검색 및 필터")
    
    # 검색어 필터
    search_query = st.text_input("매물명/내용 검색", "")
    
    # 보기 모드 선택
    view_mode = st.radio("보기 모드", ["🖼️ 갤러리 뷰", "📍 지도 뷰", "📋 상세 리스트"])
    
    st.divider()
    
    # 기존 필터 유지 및 개선
    price_types = df_raw['priceTypeName'].dropna().unique().tolist()
    selected_price_types = st.multiselect("거래 형태", price_types, default=price_types)
    
    biz_types = df_raw['businessMiddleCodeName'].dropna().unique().tolist()
    selected_biz_types = st.multiselect("업종", biz_types, default=biz_types)
    
    rent_range = st.slider("월세 (만원)", 0, int(df_raw['monthlyRent'].max()), (0, int(df_raw['monthlyRent'].max())), step=50)
    size_range = st.slider("전용면적 (㎡)", 0, int(df_raw['size'].max()), (0, int(df_raw['size'].max())))

# 필터링 적용
filtered_df = df_raw[
    (df_raw['priceTypeName'].isin(selected_price_types)) &
    (df_raw['businessMiddleCodeName'].isin(selected_biz_types)) &
    (df_raw['monthlyRent'].between(rent_range[0], rent_range[1])) &
    (df_raw['size'].between(size_range[0], size_range[1]))
]

if search_query:
    filtered_df = filtered_df[filtered_df['title'].str.contains(search_query, case=False, na=False)]

# --- 세션 상태 관리 (상세 페이지 이동용) ---
if 'selected_item_id' not in st.session_state:
    st.session_state.selected_item_id = None

# 상세 페이지 닫기 버튼
if st.session_state.selected_item_id:
    if st.button("⬅️ 목록으로 돌아가기"):
        st.session_state.selected_item_id = None
        st.rerun()

# --- 메인 본문 ---
if st.session_state.selected_item_id:
    # --- 상세 페이지 구현 ---
    item = df_raw[df_raw['id'] == st.session_state.selected_item_id].iloc[0]
    
    st.title(item['title'])
    
    # 상단 이미지 캐러셀 (Streamlit 기본 컬럼 활용)
    img_cols = st.columns(3)
    for i, img_url in enumerate(item['large_images'][:3]):
        with img_cols[i]:
            st.image(img_url, use_container_width=True)
    
    col_info1, col_info2 = st.columns([2, 1])
    
    with col_info1:
        st.subheader("📋 매물 상세 정보")
        info_df = pd.DataFrame({
            "항목": ["업종", "거래형태", "보증금", "월세", "권리금", "관리비", "층수", "전용면적", "인근 주역"],
            "내용": [
                item['businessMiddleCodeName'],
                item['priceTypeName'],
                f"{item['deposit']:,} 만원",
                f"{item['monthlyRent']:,} 만원",
                f"{item['premium']:,} 만원",
                f"{item['maintenanceFee']:,} 만원",
                f"{item['floor']}층 (총 {item['groundFloor']}층)",
                f"{item['size']:.1f} ㎡",
                item['nearSubwayStation']
            ]
        })
        st.table(info_df)
        
    with col_info2:
        st.subheader("⚖️ 밸류에이션 리포트")
        # 벤치마킹 계산: 동일 업종 평균 월세 비교
        avg_rent_biz = df_raw[df_raw['businessMiddleCodeName'] == item['businessMiddleCodeName']]['monthlyRent'].mean()
        diff_pct = ((item['monthlyRent'] - avg_rent_biz) / avg_rent_biz * 100) if avg_rent_biz > 0 else 0
        
        color = "red" if diff_pct > 0 else "blue"
        sign = "+" if diff_pct > 0 else ""
        
        st.markdown(f"""
        <div style="background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
            <p style="margin-bottom: 5px;">동일 업종 평균 대비 월세</p>
            <h2 style="color: {color}; margin-top: 0;">{sign}{diff_pct:.1f}%</h2>
            <p style="font-size: 0.9em; color: #666;">업종 평균: {avg_rent_biz:,.0f} 만원</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.info(f"💡 이 매물은 **{item['businessMiddleCodeName']}** 업종 평균 가격 대비 {'높은' if diff_pct > 0 else '저렴한'} 편입니다.")

else:
    # --- 목록 뷰 구현 ---
    st.title("🏙️ Nemostore 매물 분석")
    st.markdown(f"**현재 조건에 맞는 매물**: `{len(filtered_df)}`건")
    
    # 상단 요약 지표 (KPI) - 단위 면적당 가격 포함
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1: st.metric("평균 보증금", f"{filtered_df['deposit'].mean():,.0f}만")
    with kpi2: st.metric("평균 월세", f"{filtered_df['monthlyRent'].mean():,.0f}만")
    with kpi3: st.metric("㎡당 평균 월세", f"{filtered_df['rent_per_size'].mean():.1f}만")
    with kpi4: st.metric("평균 권리금", f"{filtered_df['premium'].mean():,.0f}만")

    st.divider()

    if view_mode == "🖼️ 갤러리 뷰":
        # 갤러리 구현 (3열 그리드)
        cols = st.columns(3)
        for idx, row in filtered_df.reset_index().iterrows():
            with cols[idx % 3]:
                st.markdown(f"""
                <div class="stCard">
                    <img src="{row['thumbnail']}" style="width:100%; border-radius:10px; height:180px; object-fit:cover;">
                    <h4 style="margin: 10px 0 5px 0; font-size: 1.1em;">{row['title'][:20]}...</h4>
                    <p style="color: #007bff; font-weight: bold; margin-bottom: 5px;">{row['priceTypeName']} {row['deposit']:,}/{row['monthlyRent']:,}</p>
                    <p style="font-size: 0.8em; color: #666;">{row['businessMiddleCodeName']} | {row['size']:.1f}㎡</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"상세 보기 #{row['id'][:8]}", key=row['id']):
                    st.session_state.selected_item_id = row['id']
                    st.rerun()

    elif view_mode == "📍 지도 뷰":
        st.subheader("매물 위치 및 밀집도 분석")
        fig_map = px.scatter_mapbox(filtered_df, lat="lat", lon="lng", 
                                    hover_name="title", hover_data=["monthlyRent", "size"],
                                    color="monthlyRent", size="size",
                                    color_continuous_scale=px.colors.cyclical.IceFire, size_max=15, zoom=14,
                                    mapbox_style="carto-positron", height=600)
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption("※ 좌표 데이터 부재로 해당 법정동 내 가상 좌표로 시뮬레이션되었습니다.")

    else:
        # 컬럼 이름 한글화 (상세 리스트)
        display_df = filtered_df[['title', 'businessMiddleCodeName', 'priceTypeName', 'deposit', 'monthlyRent', 'premium', 'maintenanceFee', 'size', 'nearSubwayStation', 'floor']].copy()
        display_df.columns = ['매물명', '업종', '거래형태', '보증금(만)', '월세(만)', '권리금(만)', '관리비(만)', '면적(㎡)', '인근역', '층']
        st.dataframe(display_df, use_container_width=True, height=600)

    st.divider()
    
    # --- 추가 분석 차트: 층별 임대료 비교 ---
    st.header("📊 심층 분석 리포트")
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("층층별 면적당 월세 (만/㎡)")
        floor_analysis = filtered_df.groupby('floor_type')['rent_per_size'].mean().sort_values().reset_index()
        fig_floor = px.bar(floor_analysis, x='floor_type', y='rent_per_size', 
                           color='floor_type', title="층 유형별 임대 효율성",
                           labels={'rent_per_size': '평균 ㎡당 월세', 'floor_type': '층 구분'})
        st.plotly_chart(fig_floor, use_container_width=True)
        st.info("💡 **해석**: 일반적으로 1층의 임대료가 가장 높으며, 지하 및 고층은 상대적으로 저렴한 경향을 보입니다.")

    with c2:
        st.subheader("면적 vs 월세 산점도 (업종별)")
        fig_scatter = px.scatter(filtered_df, x='size', y='monthlyRent', color='businessMiddleCodeName',
                                 size='deposit', hover_name='title', title="매물 규모별 가격 분포")
        st.plotly_chart(fig_scatter, use_container_width=True)

st.markdown("---")
st.caption("Nemostore Data Analysis Dashboard v2.0 - Generated by Antigravity")
