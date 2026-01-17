import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import warnings
from datetime import datetime

# --- 1. CONFIG ---
warnings.filterwarnings("ignore")
st.set_page_config(
    page_title="Sniper Bot V25", 
    page_icon="💸", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- 2. SESSION STATE ---
if 'view' not in st.session_state:
    st.session_state.view = 'dashboard'
if 'selected_asset' not in st.session_state:
    st.session_state.selected_asset = 'BTC-USD'

# --- 3. CSS (FIXED FRAMES & METRICS) ---
st.markdown("""
    <style>
    /* Globální */
    .stApp { background-color: #050505; font-family: 'Helvetica Neue', sans-serif; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    
    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #0a0a0a; border-right: 1px solid #333; }
    header[data-testid="stHeader"] { background-color: transparent; }

    /* DASHBOARD STYLES */
    .header-flex { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
    .symbol-title { font-size: 28px; font-weight: 900; color: #fff; line-height: 1; }
    .symbol-desc { font-size: 14px; color: #888; font-weight: bold; text-transform: uppercase; margin-top: 5px; }
    .price-box { text-align: right; }
    .price-main { font-size: 38px; font-weight: 700; color: #fff; font-family: monospace; line-height: 1; text-shadow: 0 0 10px rgba(255,255,255,0.1); }
    .price-change { font-size: 16px; font-weight: bold; margin-top: 5px; text-align: right; }
    .change-up { color: #00e676; }
    .change-down { color: #ff4444; }
    
    .signal-box { text-align: center; padding: 12px; border-radius: 8px; font-weight: 900; font-size: 18px; text-transform: uppercase; margin: 15px 0; color: #000; letter-spacing: 1px; }
    
    .risk-wrapper { display: flex; justify-content: space-between; background-color: #151515; border: 1px solid #333; border-radius: 8px; padding: 15px; margin-top: 15px; width: 100%; box-sizing: border-box !important; }
    .risk-col { display: flex; flex-direction: column; }
    .risk-label { font-size: 11px; color: #666; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .risk-val { font-size: 22px; font-weight: bold; font-family: monospace; }
    
    .ai-container { margin-top: 15px; text-align: center; padding-top: 15px; padding-bottom: 15px; border-top: 1px solid #222; }
    .ai-label { font-size: 11px; color: #888; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 5px; }
    .ai-score { font-size: 16px; font-weight: 900; color: #fff; }
    .ai-bar-bg { width: 100%; height: 6px; background-color: #222; border-radius: 3px; margin-top: 5px; overflow: hidden; }
    .ai-bar-fill { height: 100%; border-radius: 3px; transition: width 1s ease-in-out; }

    /* === DETAIL PAGE FIX === */
    /* Roztáhne boxy na plnou šířku a vycentruje obsah */
    .detail-metric-box { 
        background: #111; 
        padding: 20px; 
        border-radius: 10px; 
        border: 1px solid #333; 
        text-align: center; 
        width: 100%; 
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 140px; /* Fixní minimální výška pro sjednocení */
    }
    .metric-label { color: #888; font-size: 14px; font-weight: bold; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px; }
    .metric-val { color: #fff; font-size: 32px; font-weight: 900; font-family: monospace; }

    /* Sleep Mode */
    .sleep-overlay {
        height: 470px; display: flex; flex-direction: column; justify-content: center; align-items: center;
        background: rgba(20, 20, 20, 0.6); border-radius: 10px; border: 1px dashed #333;
        backdrop-filter: blur(4px); margin-top: 20px; margin-bottom: 20px; box-sizing: border-box;
    }
    .sleep-emoji { font-size: 80px; opacity: 0.8; animation: pulse 3s infinite; margin-bottom: 20px; }
    .sleep-text { font-size: 24px; font-weight: 900; color: #444; text-transform: uppercase; letter-spacing: 4px; }
    .header-dimmed { opacity: 0.4; filter: grayscale(100%); transition: opacity 0.5s; }
    
    @keyframes pulse { 0% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.1); opacity: 0.5; } 100% { transform: scale(1); opacity: 0.8; } }
    
    /* Tlačítka */
    .stButton button { width: 100%; border-radius: 5px; font-weight: bold; border: 1px solid #333; background: #151515; color: white; transition: 0.3s; }
    .stButton button:hover { border-color: #00e676; color: #00e676; background: #1a1a1a; }
    </style>
""", unsafe_allow_html=True)

# --- 4. POMOCNÉ FUNKCE ---
def hex_to_rgba(hex_color, alpha=0.2):
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})"

# --- 5. DATA ENGINE ---
@st.cache_data(ttl=30, show_spinner=False)
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        if df.empty or len(df) < 50: return None
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        lookback = 96 if len(df) > 96 else len(df) - 1
        open_price_24h = df['Close'].iloc[-lookback]
        current_price = df['Close'].iloc[-1]
        pct_change = ((current_price - open_price_24h) / open_price_24h) * 100
        df['Pct_Change'] = pct_change

        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['STD_20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)
        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
        return df
    except: return None

# --- 6. LOGIKA ---
def analyze_market_balanced(df, symbol):
    row = df.iloc[-1]
    price = row['Close']
    atr = row['ATR']
    now = pd.Timestamp.now(tz='Europe/Prague')
    is_weekend = now.weekday() >= 5 
    is_crypto = "BTC" in symbol
    
    if is_weekend and not is_crypto: is_live = False
    else:
        last_time = row.name
        diff = (now - last_time).total_seconds() / 60
        is_live = diff < 120

    score = 50.0
    trend_up = price > row['EMA_200']
    if trend_up: score += 10
    else: score -= 10
    if row['MACD'] > row['Signal_Line']: score += 10
    else: score -= 10
    rsi = row['RSI']
    if trend_up:
        if rsi < 50: score += 15    
        elif rsi > 70: score -= 15  
    else:
        if rsi > 50: score -= 15    
        elif rsi < 30: score += 15  
    if price <= row['BB_Lower']: score += 10
    if price >= row['BB_Upper']: score -= 10
    score = int(max(0, min(100, score)))

    if score >= 60: action, color = "LONG / KOUPIT 🚀", "#00e676"
    elif score <= 40: action, color = "SHORT / PRODAT 📉", "#ff4444" 
    else: action, color = "WAIT / ČEKAT ✋", "#CCCCCC"

    sl = price - (2*atr) if score > 50 else price + (2*atr)
    tp = price + (3*atr) if score > 50 else price - (3*atr)
    return score, action, color, sl, tp, is_live

# --- 7. GRAFY ---
def create_chart_mini(df, color):
    subset = df.tail(50)
    y_min, y_max = subset['Close'].min(), subset['Close'].max()
    padding = (y_max - y_min) * 0.1 if y_max != y_min else y_max*0.01
    chart_color = "#ffffff" if color == "#CCCCCC" else color
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=subset.index, y=subset['Close'], mode='lines', line=dict(color=chart_color, width=3), fill='tozeroy', fillcolor=hex_to_rgba(chart_color, 0.15)))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=10), height=200, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True), yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True, range=[y_min - padding, y_max + padding]), showlegend=False, hovermode="x unified")
    return fig

def create_chart_detail(df, color):
    subset = df.tail(100)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=subset.index, open=subset['Open'], high=subset['High'], low=subset['Low'], close=subset['Close'], name='Cena'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='BB High'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='BB Low'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['EMA_200'], line=dict(color='#ffeb3b', width=2), name='EMA 200'))
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=30), height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,10,10,1)', xaxis=dict(gridcolor='#333'), yaxis=dict(gridcolor='#333'), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def create_gauge(score, color):
    fig = go.Figure(go.Indicator(mode="gauge+number", value=score, title={'text': "SÍLA SIGNÁLU"}, gauge={'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"}, 'bar': {'color': color}, 'bgcolor': "#222", 'borderwidth': 2, 'bordercolor': "#333", 'steps': [{'range': [0, 40], 'color': 'rgba(255, 68, 68, 0.2)'}, {'range': [40, 60], 'color': 'rgba(255, 255, 255, 0.1)'}, {'range': [60, 100], 'color': 'rgba(0, 230, 118, 0.2)'}]}))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=50, b=10), paper_bgcolor='rgba(0,0,0,0)')
    return fig

# --- 8. MAIN UI LOGIC ---

assets = [
    {"sym": "EURUSD=X", "name": "EUR/USD", "desc": "Forex"},
    {"sym": "GBPUSD=X", "name": "GBP/USD", "desc": "Forex"},
    {"sym": "JPY=X", "name": "USD/JPY", "desc": "Forex"},
    {"sym": "GC=F", "name": "GOLD", "desc": "Zlato"},
    {"sym": "BTC-USD", "name": "BITCOIN", "desc": "Krypto"},
    {"sym": "ES=F", "name": "S&P 500", "desc": "Futures"},
]

# --- SIDEBAR ---
with st.sidebar:
    st.title("👽 MENU")
    
    def set_view(v, s=None):
        st.session_state.view = v
        if s: st.session_state.selected_asset = s

    if st.button("🏠 PŘEHLED (DASHBOARD)"):
        set_view('dashboard')
    
    st.markdown("---")
    st.caption("DETAIL AKTIVA")
    
    for asset in assets:
        if st.button(f"{asset['name']}"):
            set_view('detail', asset['sym'])

    st.markdown("---")
    st.info("Status: V25 Stable")

# --- HLAVNÍ OBSAH ---
placeholder = st.empty()

while True:
    with placeholder.container():
        
        # === DASHBOARD ===
        if st.session_state.view == 'dashboard':
            st.title("💸 DASHBOARD (PŘEHLED)")
            cols = st.columns(2)
            
            for i, asset in enumerate(assets):
                with cols[i % 2]: 
                    with st.container(border=True):
                        df = get_data(asset['sym'])
                        
                        if df is not None:
                            score, action, color, sl, tp, is_live = analyze_market_balanced(df, asset['sym'])
                            price = df.iloc[-1]['Close']
                            pct_change = df.iloc[-1]['Pct_Change']
                            
                            change_class = "change-up" if pct_change >= 0 else "change-down"
                            arrow = "▲" if pct_change >= 0 else "▼"
                            change_str = f"{arrow} {abs(pct_change):.2f}%"

                            if not is_live:
                                st.markdown(f"""
                                    <div class="header-flex header-dimmed">
                                        <div><div class="symbol-title">{asset['name']}</div><div class="symbol-desc">{asset['desc']}</div></div>
                                        <div class="price-box"><div class="price-main">{price:.2f}</div><div class="price-change {change_class}">{change_str}</div></div>
                                    </div>
                                    <div class="sleep-overlay"><div class="sleep-emoji">😴</div><div class="sleep-text">TRH ZAVŘENÝ</div></div>
                                """, unsafe_allow_html=True)
                            else:
                                if "WAIT" in action: sl_color, tp_color = "#666", "#666"
                                else: sl_color, tp_color = "#ff4444", "#00e676"

                                st.markdown(f"""
                                    <div class="header-flex">
                                        <div><div class="symbol-title">{asset['name']}</div><div class="symbol-desc">{asset['desc']}</div></div>
                                        <div class="price-box"><div class="price-main">{price:.2f}</div><div class="price-change {change_class}">{change_str}</div></div>
                                    </div>
                                    <div class="signal-box" style="background-color: {color}; box-shadow: 0 0 25px {hex_to_rgba(color, 0.4)};">{action}</div>
                                """, unsafe_allow_html=True)

                                chart_key = f"dash_{asset['sym']}_{int(time.time())}"
                                fig = create_chart_mini(df, color)
                                st.plotly_chart(fig, config={'displayModeBar': False}, key=chart_key, use_container_width=True)

                                st.markdown(f"""
                                    <div class="risk-wrapper">
                                        <div class="risk-col"><span class="risk-label">STOP LOSS</span><span class="risk-val" style="color: {sl_color}">{sl:.2f}</span></div>
                                        <div class="risk-col" style="text-align: right;"><span class="risk-label">TAKE PROFIT</span><span class="risk-val" style="color: {tp_color}">{tp:.2f}</span></div>
                                    </div>
                                    <div class="ai-container">
                                        <div class="ai-label">AI PŘESNOST</div><div class="ai-score">{score}%</div>
                                        <div class="ai-bar-bg"><div class="ai-bar-fill" style="width: {score}%; background-color: {color}; box-shadow: 0 0 10px {color};"></div></div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.warning(f"Načítám {asset['name']}...")

        # === DETAIL ===
        elif st.session_state.view == 'detail':
            sym = st.session_state.selected_asset
            asset_info = next((a for a in assets if a['sym'] == sym), None)
            
            if asset_info:
                st.title(f"🔎 DETAIL: {asset_info['name']}")
                
                # OPRAVA: Unikátní key pro tlačítko v loopu
                if st.button("⬅️ ZPĚT NA PŘEHLED", key="back_btn"):
                    set_view('dashboard')
                    st.rerun()

                df = get_data(sym)
                if df is not None:
                    score, action, color, sl, tp, is_live = analyze_market_balanced(df, sym)
                    row = df.iloc[-1]
                    price = row['Close']
                    pct_change = row['Pct_Change']
                    
                    change_class = "change-up" if pct_change >= 0 else "change-down"
                    arrow = "▲" if pct_change >= 0 else "▼"
                    change_str = f"{arrow} {abs(pct_change):.2f}%"

                    # Detail Header
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"""<div style="margin-bottom: 20px;"><div class="symbol-title" style="font-size: 50px;">{asset_info['name']}</div><div class="symbol-desc">{asset_info['desc']} | {sym}</div></div>""", unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"""<div style="text-align: right;"><div class="price-main" style="font-size: 60px;">{price:.2f}</div><div class="price-change {change_class}" style="font-size: 24px;">{change_str}</div></div>""", unsafe_allow_html=True)

                    if not is_live:
                         st.markdown(f"""<div class="sleep-overlay" style="height: 300px;"><div class="sleep-emoji">😴</div><div class="sleep-text">TRH ZAVŘENÝ</div></div>""", unsafe_allow_html=True)
                    else:
                        st.markdown(f"""<div class="signal-box" style="background-color: {color}; font-size: 24px; padding: 20px; box-shadow: 0 0 30px {hex_to_rgba(color, 0.5)};">{action}</div>""", unsafe_allow_html=True)
                        
                        st.markdown("### 📊 SVÍČKOVÝ GRAF")
                        fig = create_chart_detail(df, color)
                        st.plotly_chart(fig, use_container_width=True)
                        
                        c_metrics, c_risk, c_gauge = st.columns(3)
                        with c_metrics:
                            st.markdown('<div class="detail-metric-box">', unsafe_allow_html=True)
                            st.markdown(f'<div class="metric-label">RSI HODNOTA</div><div class="metric-val">{row["RSI"]:.1f}</div>', unsafe_allow_html=True)
                            st.markdown("<hr style='border-color: #333; margin: 10px 0;'>", unsafe_allow_html=True)
                            st.markdown(f'<div class="metric-label">MACD SÍLA</div><div class="metric-val">{row["MACD"]:.4f}</div>', unsafe_allow_html=True)
                            st.markdown('</div>', unsafe_allow_html=True)
                        with c_risk:
                            if "WAIT" in action: sl_c, tp_c = "#666", "#666"
                            else: sl_c, tp_c = "#ff4444", "#00e676"
                            st.markdown('<div class="detail-metric-box">', unsafe_allow_html=True)
                            st.markdown(f'<div class="metric-label">STOP LOSS</div><div class="metric-val" style="color:{sl_c}">{sl:.2f}</div>', unsafe_allow_html=True)
                            st.markdown("<hr style='border-color: #333; margin: 10px 0;'>", unsafe_allow_html=True)
                            st.markdown(f'<div class="metric-label">TAKE PROFIT</div><div class="metric-val" style="color:{tp_c}">{tp:.2f}</div>', unsafe_allow_html=True)
                            st.markdown('</div>', unsafe_allow_html=True)
                        with c_gauge:
                            fig_g = create_gauge(score, color)
                            st.plotly_chart(fig_g, use_container_width=True, config={'displayModeBar': False})

        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    
    if st.session_state.view == 'dashboard':
        time.sleep(15)
    else:
        time.sleep(5)