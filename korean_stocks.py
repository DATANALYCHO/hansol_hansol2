import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from openai import OpenAI

st.set_page_config(
    page_title="국내 주식 대시보드",
    page_icon="📈",
    layout="wide"
)

STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "현대자동차": "005380.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "셀트리온": "068270.KS",
    "KB금융": "105560.KS",
    "POSCO홀딩스": "005490.KS",
}

st.title("📈 국내 주식 대시보드")
st.markdown("**KOSPI 대표 종목 10개** 실시간 데이터 (yfinance 기반)")

# 사이드바 설정
st.sidebar.header("⚙️ 설정")

# API 키 입력
st.sidebar.subheader("🤖 AI 챗봇 설정")
api_key = st.sidebar.text_input(
    "OpenAI API Key",
    type="password",
    placeholder="sk-...",
    help="GPT-4o-mini 챗봇 사용을 위해 API 키를 입력하세요."
)

selected_stocks = st.sidebar.multiselect(
    "종목 선택",
    options=list(STOCKS.keys()),
    default=list(STOCKS.keys())
)

period_options = {"1개월": "1mo", "3개월": "3mo", "6개월": "6mo", "1년": "1y", "2년": "2y"}
selected_period_label = st.sidebar.selectbox("기간 선택", list(period_options.keys()), index=2)
selected_period = period_options[selected_period_label]

# 데이터 로드
@st.cache_data(ttl=300)
def load_stock_data(tickers: list, period: str):
    data = {}
    info_data = []
    for name, ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            if not hist.empty:
                data[name] = hist
                current_price = hist["Close"].iloc[-1]
                prev_price = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                high_52w = hist["High"].max()
                low_52w = hist["Low"].min()
                avg_volume = hist["Volume"].mean()
                info_data.append({
                    "종목명": name,
                    "티커": ticker,
                    "현재가": f"₩{current_price:,.0f}",
                    "전일대비": f"{'+' if change >= 0 else ''}{change:,.0f}",
                    "등락률": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
                    "거래량": f"{hist['Volume'].iloc[-1]:,.0f}",
                    "_change_pct": change_pct,
                    "_current_price": current_price,
                    "_high": high_52w,
                    "_low": low_52w,
                    "_avg_volume": avg_volume,
                })
        except Exception as e:
            st.warning(f"{name} 데이터 로드 실패: {e}")
    return data, pd.DataFrame(info_data)

def build_stock_context(summary_df: pd.DataFrame, hist_data: dict, period_label: str) -> str:
    """챗봇에게 전달할 주식 데이터 컨텍스트 생성"""
    lines = [f"[현재 대시보드 주식 데이터 - 기간: {period_label}]\n"]
    for _, row in summary_df.iterrows():
        name = row["종목명"]
        lines.append(
            f"- {name}: 현재가 {row['현재가']}, 전일대비 {row['전일대비']} ({row['등락률']}), "
            f"거래량 {row['거래량']}, "
            f"기간 최고 ₩{row['_high']:,.0f}, 기간 최저 ₩{row['_low']:,.0f}, "
            f"평균거래량 {row['_avg_volume']:,.0f}"
        )
        if name in hist_data:
            df = hist_data[name]
            first = df["Close"].iloc[0]
            last = df["Close"].iloc[-1]
            total_return = (last - first) / first * 100
            lines.append(f"  기간 수익률: {total_return:+.2f}%")
    return "\n".join(lines)

def chat_with_gpt(api_key: str, messages: list) -> str:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=1000,
    )
    return response.choices[0].message.content

if not selected_stocks:
    st.warning("종목을 하나 이상 선택해주세요.")
    st.stop()

with st.spinner("데이터 불러오는 중..."):
    tickers_to_load = [(name, STOCKS[name]) for name in selected_stocks]
    hist_data, summary_df = load_stock_data(tickers_to_load, selected_period)

# 요약 카드
st.subheader("📊 종목 요약")
if not summary_df.empty:
    cols = st.columns(min(5, len(summary_df)))
    for i, row in summary_df.iterrows():
        col = cols[i % len(cols)]
        with col:
            color = "🟢" if row["_change_pct"] >= 0 else "🔴"
            st.metric(
                label=f"{color} {row['종목명']}",
                value=row["현재가"],
                delta=f"{row['등락률']} ({row['전일대비']})"
            )

st.divider()

# 요약 테이블
st.subheader("📋 상세 현황")
display_df = summary_df[["종목명", "티커", "현재가", "전일대비", "등락률", "거래량"]].copy()
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()

# 주가 차트
st.subheader("📉 주가 추이 비교 (정규화)")
if hist_data:
    fig = go.Figure()
    for name, df in hist_data.items():
        normalized = df["Close"] / df["Close"].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=df.index,
            y=normalized,
            name=name,
            mode="lines",
            hovertemplate=f"<b>{name}</b><br>날짜: %{{x|%Y-%m-%d}}<br>정규화 지수: %{{y:.1f}}<extra></extra>"
        ))
    fig.update_layout(
        title=f"주가 정규화 비교 (기준: 100, 기간: {selected_period_label})",
        xaxis_title="날짜",
        yaxis_title="정규화 지수",
        hovermode="x unified",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# 개별 종목 캔들 차트
st.subheader("🕯️ 개별 종목 캔들 차트")
selected_candle = st.selectbox("종목 선택", list(hist_data.keys()))
if selected_candle and selected_candle in hist_data:
    df = hist_data[selected_candle]
    fig_candle = go.Figure(data=[
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=selected_candle,
            increasing_line_color="#ff4b4b",
            decreasing_line_color="#1f77b4"
        )
    ])
    fig_candle.add_trace(go.Bar(
        x=df.index,
        y=df["Volume"],
        name="거래량",
        yaxis="y2",
        marker_color="rgba(128,128,128,0.3)"
    ))
    fig_candle.update_layout(
        title=f"{selected_candle} 캔들 차트",
        xaxis_title="날짜",
        yaxis_title="주가 (₩)",
        yaxis2=dict(title="거래량", overlaying="y", side="right"),
        height=550,
        xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig_candle, use_container_width=True)

st.divider()

# 등락률 막대 차트
st.subheader("📊 등락률 비교")
if not summary_df.empty:
    bar_df = summary_df[["종목명", "_change_pct"]].copy()
    bar_df.columns = ["종목명", "등락률(%)"]
    bar_df = bar_df.sort_values("등락률(%)", ascending=True)
    colors = ["#ff4b4b" if v >= 0 else "#1f77b4" for v in bar_df["등락률(%)"]]
    fig_bar = go.Figure(go.Bar(
        x=bar_df["등락률(%)"],
        y=bar_df["종목명"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in bar_df["등락률(%)"]],
        textposition="outside"
    ))
    fig_bar.update_layout(
        title="전일 대비 등락률",
        xaxis_title="등락률 (%)",
        height=400,
        margin=dict(l=120)
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── AI 챗봇 ──────────────────────────────────────────────
st.subheader("🤖 AI 주식 분석 챗봇")

if not api_key:
    st.info("사이드바에 OpenAI API Key를 입력하면 챗봇을 사용할 수 있습니다.")
else:
    # 세션 상태 초기화
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    stock_context = build_stock_context(summary_df, hist_data, selected_period_label)
    system_prompt = (
        "당신은 한국 주식 전문 AI 분석가입니다. "
        "아래 실시간 주식 데이터를 바탕으로 사용자 질문에 한국어로 답변하세요. "
        "데이터에 없는 내용은 모른다고 솔직히 말하고, 투자 권유는 하지 마세요.\n\n"
        + stock_context
    )

    # 대화 기록 출력
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 사용자 입력
    if user_input := st.chat_input("주식에 대해 질문하세요. 예) 오늘 가장 많이 오른 종목은?"):
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                try:
                    messages_to_send = [{"role": "system", "content": system_prompt}] + [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.chat_messages
                    ]
                    answer = chat_with_gpt(api_key, messages_to_send)
                    st.markdown(answer)
                    st.session_state.chat_messages.append({"role": "assistant", "content": answer})
                except Exception as e:
                    err_msg = f"오류가 발생했습니다: {e}"
                    st.error(err_msg)

    if st.session_state.get("chat_messages"):
        if st.button("대화 초기화"):
            st.session_state.chat_messages = []
            st.rerun()

st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 데이터 출처: Yahoo Finance")
