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
    page_title="Sniper Bot V30", 
    page_icon="💀", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- 2. CSS (TOP MENU & DARK THEME) ---
st.markdown("""
    <style>
    /* Globální reset */
    .stApp { background-color: #050505; font-family: 'Helvetica Neue', sans-serif; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    
    /* Skrýt Sidebar úplně */
    [data-testid="stSidebar"] { display: none; }
    
    /* === TOP NAVIGACE === */
    .nav-container {
        display: flex;
        justify-content: center;
        background: #111;
        border-bottom: 1px solid #333;
        padding: 10px;
        margin-bottom: 20px;
        border-radius: 10px;
    }
    
    /* Styl tlačítek v navigaci */
    div.stButton > button {
        background-color: #111;
        color: #888;
        border: 1px solid #333;
        font-weight: bold;
        text-transform: uppercase;
        border-radius: 5px;
        transition: 0.3s;
        width: 100%;
    }
    div.stButton > button:hover {
        border-color: #00e676;
        color: #00e676;
    }
    div.stButton > button:focus {
        background-color: #00e676 !important;
        color: black !important;
        border-color: #00e676 !important;
    }

    /* === DASHBOARD KARTY === */
    .symbol-title { font-size: 24px; font-weight: 900; color: #fff; margin: 0; }
    .symbol-desc { font-size: 12px; color: #666; font-weight: bold; text-transform: uppercase; }
    .price-main { font-size: 32px; font-weight: 700; color: #fff; font-family: monospace; text-align: right; }
    .price-change { font-size: 14px; font-weight: bold; text-align: right; }
    .change-up { color: #00e676; }
    .change-down { color: #ff4444; }
    
    .signal-box { text-align: center; padding: 10px; border-radius: 5px; font-weight: 900; font-size: 16px; text-transform: uppercase; margin: 10px 0; color: #000; letter-spacing: 1px; }
    
    .risk-wrapper { display: flex; justify-content: space-between; background-color: #151515; border: 1px solid #333; border-radius: 5px; padding: 10px; margin-top: 10px; width: 100%; box-sizing: border-box !important; }
    .risk-label { font-size: 10px; color: #666; font-weight: 800; text-transform: uppercase; margin-bottom: 2px; }
    .risk-val { font-size: 18px; font-weight: bold; font-family: monospace; }
    
    .ai-container { margin-top: 10px; text-align: center; padding-top: 10px; border-top: 1px solid #222; }
    .ai-label { font-size: 10px; color: #888; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; }
    .ai-score { font-size: 14px; font-weight: 900; color: #fff; }
    .ai-bar-bg { width: 100%; height: 4px; background-color: #222; border-radius: 2px; margin-top: 5px; overflow: hidden; }
    .ai-bar-fill { height: 100%; border-radius: 2px; }

    /* DETAIL PAGE */
    .metric-box { background: #111; padding: 15px; border-radius: 8px; border: 1px solid #333; text-align: center; height: 100%; box-sizing: border-box; }
    .metric-title { color: #666; font-size: 12px; font-weight: 900; letter-spacing: 1px; margin-bottom: 5px; text-transform: uppercase; }
    .metric-value { color: #fff; font-size: 28px; font-weight: 900; font-family: monospace; }

    /* Sleep Mode */
    .sleep-overlay {
        height: 350px; display: flex; flex-direction: column; justify-content: center; align-items: center;
        background: rgba(20, 20, 20, 0.6); border-radius: 10px; border: 1px dashed #333;
        backdrop-filter: blur(4px); margin-top: 20px; box-sizing: border-box;
    }
    .header-dimmed { opacity: 0.3; filter: grayscale(100%); }
    
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE ---
if 'view' not in st.session_state:
    st.session_state.view = 'dashboard'
if 'selected_asset' not in st.session_state:
    st.session_state.selected_asset = 'BTC-USD'

# --- 4. FUNKCE ---
def hex_to_rgba(hex_color, alpha=0.2):
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})"

@st.cache_data(ttl=30, show_spinner=False)
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        if df.empty or len(df) < 50: return None
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')
        
        # Calculations
        pct_change = ((df['Close'].iloc[-1] - df['Close'].iloc[-96]) / df['Close'].iloc[-96]) * 100
        df['Pct_Change'] = pct_change
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # BB
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['STD_20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)
        
        # ATR
        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
        return df
    except: return None

def analyze_market_balanced(df, symbol):
    row = df.iloc[-1]
    now = pd.Timestamp.now(tz='Europe/Prague')
    is_weekend = now.weekday() >= 5 
    is_crypto = "BTC" in symbol
    
    if is_weekend and not is_crypto: is_live = False
    else:
        diff = (now - row.name).total_seconds() / 60
        is_live = diff < 120

    score = 50.0
    # Logic
    if row['Close'] > row['EMA_200']: score += 10
    else: score -= 10
    
    if row['MACD'] > row['Signal_Line']: score += 10
    else: score -= 10
    
    if row['Close'] > row['EMA_200']:
        if row['RSI'] < 50: score += 15
        elif row['RSI'] > 70: score -= 15
    else:
        if row['RSI'] > 50: score -= 15
        elif row['RSI'] < 30: score += 15
        
    if row['Close'] <= row['BB_Lower']: score += 10
    if row['Close'] >= row['BB_Upper']: score -= 10
    
    score = int(max(0, min(100, score)))
    
    if score >= 60: action, color = "LONG / KOUPIT 🚀", "#00e676"
    elif score <= 40: action, color = "SHORT / PRODAT 📉", "#ff4444" 
    else: action, color = "WAIT / ČEKAT ✋", "#CCCCCC"
    
    sl = row['Close'] - (2*row['ATR']) if score > 50 else row['Close'] + (2*row['ATR'])
    tp = row['Close'] + (3*row['ATR']) if score > 50 else row['Close'] - (3*row['ATR'])
    
    return score, action, color, sl, tp, is_live

def create_chart(df, color, height=200, type='line'):
    subset = df.tail(60 if type == 'line' else 100)
    y_min, y_max = subset['Close'].min(), subset['Close'].max()
    padding = (y_max - y_min) * 0.1 if y_max != y_min else y_max*0.01
    
    chart_color = "#ffffff" if color == "#CCCCCC" else color
    fig = go.Figure()
    
    if type == 'line':
        fig.add_trace(go.Scatter(x=subset.index, y=subset['Close'], mode='lines', line=dict(color=chart_color, width=3), fill='tozeroy', fillcolor=hex_to_rgba(chart_color, 0.15)))
    else:
        fig.add_trace(go.Candlestick(x=subset.index, open=subset['Open'], high=subset['High'], low=subset['Low'], close=subset['Close'], name='Cena'))
        
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))
    
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=10), height=height, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True), yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True, range=[y_min - padding, y_max + padding]), showlegend=False, hovermode="x unified")
    return fig

# --- 5. DATA & ASSETS ---
assets = [
    {"sym": "BTC-USD", "name": "BITCOIN"},
    {"sym": "EURUSD=X", "name": "EUR/USD"},
    {"sym": "GBPUSD=X", "name": "GBP/USD"},
    {"sym": "JPY=X", "name": "USD/JPY"},
    {"sym": "GC=F", "name": "GOLD"},
    {"sym": "ES=F", "name": "S&P 500"},
]

# --- 6. TOP NAVIGATION (JEDNODUCHÁ A NEPRŮSTŘELNÁ) ---
st.markdown("### 🔫 SNIPER BOT V30")

# Navigace pomocí sloupců nahoře
cols = st.columns(len(assets) + 1)
if cols[0].button("🏠", key="nav_dash", help="Dashboard"):
    st.session_state.view = 'dashboard'

# Vygenerujeme tlačítka pro aktiva
for i, asset in enumerate(assets):
    # Pokud je aktivum vybrané, zvýrazníme ho (vizuálně jen tím, že je to button)
    if cols[i+1].button(asset['name'], key=f"nav_{asset['sym']}"):
        st.session_state.view = 'detail'
        st.session_state.selected_asset = asset['sym']

st.markdown("---")

# --- 7. MAIN VIEW ---
if st.session_state.view == 'dashboard':
    # DASHBOARD GRID
    grid_cols = st.columns(2)
    for i, asset in enumerate(assets):
        with grid_cols[i % 2]:
            with st.container(border=True):
                df = get_data(asset['sym'])
                if df is not None:
                    score, action, color, sl, tp, is_live = analyze_market_balanced(df, asset['sym'])
                    price = df.iloc[-1]['Close']
                    change = df.iloc[-1]['Pct_Change']
                    c_class = "change-up" if change >= 0 else "change-down"
                    arrow = "▲" if change >= 0 else "▼"
                    
                    if not is_live:
                        st.markdown(f"""
                            <div class="header-flex header-dimmed">
                                <div><div class="symbol-title">{asset['name']}</div><div class="symbol-desc">{asset['sym']}</div></div>
                                <div class="price-box"><div class="price-main">{price:.2f}</div><div class="price-change {c_class}">{arrow} {abs(change):.2f}%</div></div>
                            </div>
                            <div class="sleep-overlay"><div style="font-size:50px">😴</div><div style="font-weight:900;color:#666">TRH ZAVŘENÝ</div></div>
                        """, unsafe_allow_html=True)
                    else:
                        sl_c = "#666" if "WAIT" in action else "#ff4444"
                        tp_c = "#666" if "WAIT" in action else "#00e676"
                        
                        st.markdown(f"""
                            <div class="header-flex">
                                <div><div class="symbol-title">{asset['name']}</div><div class="symbol-desc">{asset['sym']}</div></div>
                                <div class="price-box"><div class="price-main">{price:.2f}</div><div class="price-change {c_class}">{arrow} {abs(change):.2f}%</div></div>
                            </div>
                            <div class="signal-box" style="background-color: {color}; box-shadow: 0 0 20px {hex_to_rgba(color, 0.4)};">{action}</div>
                        """, unsafe_allow_html=True)
                        
                        st.plotly_chart(create_chart(df, color), config={'displayModeBar': False}, use_container_width=True, key=f"d_ch_{asset['sym']}")
                        
                        st.markdown(f"""
                            <div class="risk-wrapper">
                                <div><div class="risk-label">STOP LOSS</div><div class="risk-val" style="color:{sl_c}">{sl:.2f}</div></div>
                                <div style="text-align:right"><div class="risk-label">TAKE PROFIT</div><div class="risk-val" style="color:{tp_c}">{tp:.2f}</div></div>
                            </div>
                            <div class="ai-container">
                                <div class="ai-label">AI PŘESNOST</div><div class="ai-score">{score}%</div>
                                <div class="ai-bar-bg"><div class="ai-bar-fill" style="width: {score}%; background-color: {color}; box-shadow: 0 0 10px {color}"></div></div>
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("Načítám...")

elif st.session_state.view == 'detail':
    # DETAIL PAGE
    sym = st.session_state.selected_asset
    asset = next((a for a in assets if a['sym'] == sym), None)
    
    if asset:
        st.title(f"🔎 {asset['name']} ({sym})")
        df = get_data(sym)
        if df is not None:
            score, action, color, sl, tp, is_live = analyze_market_balanced(df, sym)
            row = df.iloc[-1]
            
            if not is_live:
                st.info("Trh je momentálně zavřený. Zobrazuji poslední známá data.")
            
            # Big Chart
            st.plotly_chart(create_chart(df, color, height=500, type='candle'), use_container_width=True, key="det_chart")
            
            # Metrics Grid (NO FRAMES, CLEAN)
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f'<div class="metric-box"><div class="metric-title">RSI HODNOTA</div><div class="metric-value">{row["RSI"]:.1f}</div></div>', unsafe_allow_html=True)
            with m2:
                st.markdown(f'<div class="metric-box"><div class="metric-title">MACD SÍLA</div><div class="metric-value">{row["MACD"]:.4f}</div></div>', unsafe_allow_html=True)
            with m3:
                sl_c = "#666" if "WAIT" in action else "#ff4444"
                st.markdown(f'<div class="metric-box"><div class="metric-title">STOP LOSS</div><div class="metric-value" style="color:{sl_c}">{sl:.2f}</div></div>', unsafe_allow_html=True)
            with m4:
                tp_c = "#666" if "WAIT" in action else "#00e676"
                st.markdown(f'<div class="metric-box"><div class="metric-title">TAKE PROFIT</div><div class="metric-value" style="color:{tp_c}">{tp:.2f}</div></div>', unsafe_allow_html=True)
                
            # Signal Big Box
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
                <div class="signal-box" style="background-color: {color}; font-size: 24px; padding: 20px; box-shadow: 0 0 30px {hex_to_rgba(color, 0.5)};">
                    {action}
                </div>
            """, unsafe_allow_html=True)

# --- AUTO REFRESH LOOP ---
# Toto je klíč k odstranění chyb. Místo while True používáme rerun.
time.sleep(15) 
st.rerun()