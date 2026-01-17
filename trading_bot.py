import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import warnings
import os
from datetime import datetime

# --- 1. CONFIG ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="Sniper Bot V10", page_icon="💀", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS - CLEAN & BIG UI ---
st.markdown("""
    <style>
    /* Reset */
    .stApp { background-color: #000000; font-family: 'Helvetica Neue', sans-serif; }
    
    /* Odstranění mezer ve Streamlitu */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    div[data-testid="stVerticalBlock"] { gap: 1rem; }
    
    /* KARTA PÁRU (Bez rámečků Streamlitu) */
    .crypto-card {
        background-color: #111;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 20px;
        border-left: 5px solid #333; /* Default border */
    }
    
    /* Hlavní Info: Název a Cena */
    .card-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 10px; }
    .symbol-text { font-size: 24px; font-weight: 900; color: #fff; margin: 0; line-height: 1; }
    .desc-text { font-size: 14px; color: #666; font-weight: 500; text-transform: uppercase; }
    .price-text { font-size: 36px; font-weight: 700; color: #fff; font-family: monospace; line-height: 1; }

    /* Signál - Velký a jasný */
    .signal-badge {
        display: block;
        text-align: center;
        font-size: 22px;
        font-weight: 900;
        padding: 12px;
        border-radius: 8px;
        margin: 15px 0;
        text-transform: uppercase;
        color: #000; /* Černý text pro kontrast */
    }
    
    /* Risk Management - Velké písmo */
    .risk-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        margin-top: 15px;
        background: #1a1a1a;
        padding: 10px;
        border-radius: 8px;
    }
    .risk-item { display: flex; flex-direction: column; }
    .risk-label { font-size: 12px; color: #888; text-transform: uppercase; font-weight: bold; }
    .risk-value { font-size: 18px; font-family: monospace; font-weight: bold; }
    
    .sl-color { color: #ff4444; }
    .tp-color { color: #00e676; }

    </style>
""", unsafe_allow_html=True)

# --- 3. POMOCNÉ FUNKCE ---
def hex_to_rgba(hex_color, alpha=0.2):
    """Převede HEX barvu na RGBA pro Plotly"""
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})"

# --- 4. DATA ENGINE ---
@st.cache_data(ttl=30, show_spinner=False)
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 50: return None
        
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        # Indikátory
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
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
    except:
        return None

# --- 5. LOGIKA ---
def analyze_market(df):
    row = df.iloc[-1]
    price = row['Close']
    atr = row['ATR']
    
    # Čas
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    is_live = diff < 120 or now.weekday() >= 5 # Větší tolerance

    score = 50
    
    # Trend
    trend_up = price > row['EMA_200']
    score += 10 if trend_up else -10

    # Logika
    if trend_up:
        if row['RSI'] < 45: score += 15
        if price <= row['BB_Lower']: score += 20
    else:
        if row['RSI'] > 55: score -= 15
        if price >= row['BB_Upper']: score -= 20

    score = max(0, min(100, score))

    if score >= 60: 
        action = "LONG / KOUPIT 🚀"
        color = "#00e676" # Zelená
        bg_color = "#00e676"
    elif score <= 40: 
        action = "SHORT / PRODAT 📉"
        color = "#ff4444" # Červená
        bg_color = "#ff4444"
    else: 
        action = "WAIT / ČEKAT ✋"
        color = "#888888" # Šedá
        bg_color = "#333333"

    sl = price - (2*atr) if score > 50 else price + (2*atr)
    tp = price + (3*atr) if score > 50 else price - (3*atr)

    return score, action, color, bg_color, sl, tp, is_live

# --- 6. GRAF (PLOTLY) ---
def create_chart(df, color):
    subset = df.tail(50) # Více svíček
    
    fig = go.Figure()

    # Linka
    fig.add_trace(go.Scatter(
        x=subset.index, y=subset['Close'],
        mode='lines',
        line=dict(color=color, width=3),
        fill='tozeroy',
        fillcolor=hex_to_rgba(color, 0.1), # Správná průhlednost
    ))

    # Bollinger Bands
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.1)', width=1), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.1)', width=1), hoverinfo='skip'))

    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=180, # VĚTŠÍ VÝŠKA GRAFU
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
        hovermode="x unified"
    )
    return fig

# --- 7. APP ---
st.title("🎯 SNIPER TRADING V10")
placeholder = st.empty()

while True:
    with placeholder.container():
        
        # Změna: 2 Sloupce pro více místa
        cols = st.columns(2)
        
        assets = [
            {"sym": "EURUSD=X", "name": "EUR/USD", "desc": "Forex"},
            {"sym": "GBPUSD=X", "name": "GBP/USD", "desc": "Forex"},
            {"sym": "JPY=X", "name": "USD/JPY", "desc": "Forex"},
            {"sym": "GC=F", "name": "GOLD", "desc": "Zlato"},
            {"sym": "CL=F", "name": "OIL", "desc": "Ropa"},
            {"sym": "ES=F", "name": "S&P 500", "desc": "Futures"},
        ]

        for i, asset in enumerate(assets):
            with cols[i % 2]: # Střídání sloupců
                df = get_data(asset['sym'])
                
                if df is not None:
                    score, action, color, bg_color, sl, tp, is_live = analyze_market(df)
                    price = df.iloc[-1]['Close']
                    
                    # --- HTML CARD ---
                    # Vykreslujeme celý box pomocí HTML, aby to vypadalo celistvě
                    st.markdown(f"""
                    <div class="crypto-card" style="border-left: 5px solid {color};">
                        <div class="card-header">
                            <div>
                                <div class="symbol-text">{asset['name']}</div>
                                <div class="desc-text">{asset['desc']}</div>
                            </div>
                            <div class="price-text">{price:.2f}</div>
                        </div>
                        
                        <div class="signal-badge" style="background-color: {bg_color}; box-shadow: 0 0 20px {hex_to_rgba(color, 0.4)};">
                            {action}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # --- PLOTLY GRAF (Větší) ---
                    fig = create_chart(df, color)
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                    
                    # --- RISK MANAGEMENT (HTML) ---
                    if is_live and score != 50:
                        st.markdown(f"""
                        <div class="risk-grid">
                            <div class="risk-item">
                                <span class="risk-label">STOP LOSS 🛑</span>
                                <span class="risk-value sl-color">{sl:.2f}</span>
                            </div>
                            <div class="risk-item" style="text-align: right;">
                                <span class="risk-label">TAKE PROFIT 🎯</span>
                                <span class="risk-value tp-color">{tp:.2f}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Uzavření divu karty
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.warning(f"Načítám {asset['name']}...")

        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    
    time.sleep(15)