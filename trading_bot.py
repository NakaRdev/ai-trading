import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import warnings
import os
from datetime import datetime

# --- 1. NASTAVENÍ APLIKACE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="Sniper Bot CZ Pro", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS STYLING (Neonový vzhled) ---
st.markdown("""
    <style>
    /* Pozadí a fonty */
    .stApp { background-color: #080808; color: #e0e0e0; font-family: 'Roboto', sans-serif; }
    
    /* Karty pro páry */
    div[data-testid="stVerticalBlock"] > div > div {
        background-color: #121212; 
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Nadpisy */
    .pair-name { font-size: 22px; font-weight: 900; color: #fff; margin-bottom: 0; letter-spacing: 1px; }
    .pair-desc { font-size: 12px; color: #888; margin-bottom: 10px; text-transform: uppercase; }
    
    /* Cena */
    .price-big { font-size: 32px; font-weight: 700; color: #fff; font-family: 'Courier New', monospace; letter-spacing: -1px; }
    
    /* Signály - Neonové efekty */
    .signal-box {
        text-align: center; padding: 8px; border-radius: 6px; margin: 10px 0;
        font-weight: 800; font-size: 18px; text-transform: uppercase; letter-spacing: 1px;
    }
    .sig-buy { background: rgba(0, 255, 65, 0.1); color: #00ff41; border: 1px solid #00ff41; box-shadow: 0 0 10px rgba(0, 255, 65, 0.2); }
    .sig-sell { background: rgba(255, 43, 43, 0.1); color: #ff2b2b; border: 1px solid #ff2b2b; box-shadow: 0 0 10px rgba(255, 43, 43, 0.2); }
    .sig-wait { background: #222; color: #666; border: 1px dashed #444; }
    
    /* Risk Management Texty */
    .risk-row { display: flex; justify-content: space-between; font-size: 12px; margin-top: 5px; font-family: monospace; }
    .sl-val { color: #ff5252; }
    .tp-val { color: #69f0ae; }
    
    /* Skrytí defaultních Streamlit elementů */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=45, show_spinner=False) # Cache 45 sekund
def get_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 50: return None
            
        # Timezone fix pro Prahu
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        # Výpočet indikátorů
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['STD_20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)

        # ATR (Risk)
        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()

        return df
    except:
        return None

# --- 4. LOGIKA ANALÝZY ---
def analyze_market(df):
    row = df.iloc[-1]
    price = row['Close']
    atr = row['ATR']
    
    # 1. Časová kontrola
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    is_weekend = now.weekday() >= 5
    # Tolerance 90 minut (kvůli zpoždění Yahoo) nebo víkend
    is_live = diff < 90 or is_weekend 

    if not is_live:
        return 50, "OFFLINE", "Trh zavřený", 0, 0, False

    # 2. Bodování (0-100)
    score = 50
    reasons = []
    
    # Trend
    trend = "UP" if price > row['EMA_200'] else "DOWN"
    score += 10 if trend == "UP" else -10

    # RSI & BB
    if trend == "UP":
        if row['RSI'] < 45: score += 15 # Pullback
        if price <= row['BB_Lower'] * 1.001: score += 20 # Dotek spodního pásma
    else:
        if row['RSI'] > 55: score -= 15
        if price >= row['BB_Upper'] * 0.999: score -= 20

    score = max(0, min(100, score))

    # 3. Akce
    if score >= 60: action = "LONG (Koupit)"
    elif score <= 40: action = "SHORT (Prodat)"
    else: action = "WAIT (Čekat)"

    # 4. SL / TP
    sl = price - (2*atr) if score > 50 else price + (2*atr)
    tp = price + (3*atr) if score > 50 else price - (3*atr)

    return score, action, reasons, sl, tp, is_live

# --- 5. VYKRESLENÍ GRAFU (Plotly) ---
def create_chart(df, score):
    # Barva grafu podle signálu
    if score >= 55: main_color = '#00ff41' # Zelená
    elif score <= 45: main_color = '#ff2b2b' # Červená
    else: main_color = '#888888' # Šedá

    subset = df.tail(40) # Posledních 40 svíček
    
    fig = go.Figure()

    # Hlavní cena (Line s výplní)
    fig.add_trace(go.Scatter(
        x=subset.index, y=subset['Close'],
        mode='lines',
        line=dict(color=main_color, width=2),
        fill='tozeroy', # Vyplní oblast pod grafem
        fillcolor=f"rgba{main_color[1:] if main_color.startswith('#') else '(100,100,100'}, 0.1)", # Průhledná výplň
        name='Cena'
    ))

    # Bollinger Bands (jemné linky)
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.15)', width=1), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.15)', width=1), hoverinfo='skip'))

    # Design grafu (Minimalistický "Sniper" styl)
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=80, # Výška grafu
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
        hovermode="x unified"
    )
    return fig

# --- 6. MAIN LOOP ---
st.title("🎯 SNIPER TRADING CZ")
st.caption("AI Analýza trhu v reálném čase")

placeholder = st.empty()

while True:
    with placeholder.container():
        st.write(f"⏱️ Aktualizováno: **{datetime.now().strftime('%H:%M:%S')}**")
        
        # Grid 3 sloupce
        cols = st.columns(3)
        
        assets = [
            {"sym": "EURUSD=X", "name": "EUR / USD", "desc": "Forex"},
            {"sym": "GBPUSD=X", "name": "GBP / USD", "desc": "Forex"},
            {"sym": "JPY=X", "name": "USD / JPY", "desc": "Forex"},
            {"sym": "GC=F", "name": "ZLATO (Gold)", "desc": "Komodity"},
            {"sym": "CL=F", "name": "ROPA (Oil)", "desc": "Komodity"},
            {"sym": "ES=F", "name": "S&P 500", "desc": "Indexy Futures"},
            {"sym": "BTC-USD", "name": "BITCOIN", "desc": "Krypto"},
            {"sym": "ETH-USD", "name": "ETHEREUM", "desc": "Krypto"},
        ]

        # Rozdělení do sloupců
        for i, asset in enumerate(assets):
            col_idx = i % 3
            with cols[col_idx]:
                df = get_data(asset['sym'])
                
                if df is not None:
                    score, action, reasons, sl, tp, is_live = analyze_market(df)
                    price = df.iloc[-1]['Close']
                    
                    with st.container():
                        # Hlavička karty
                        st.markdown(f"""
                        <div>
                            <div class="pair-name">{asset['name']}</div>
                            <div class="pair-desc">{asset['desc']}</div>
                            <div class="price-big">{price:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Signál Box
                        if not is_live:
                            st.markdown('<div class="signal-box sig-wait">TRH SPÍ 💤</div>', unsafe_allow_html=True)
                        elif "LONG" in action:
                            st.markdown(f'<div class="signal-box sig-buy">{action} 🚀</div>', unsafe_allow_html=True)
                        elif "SHORT" in action:
                            st.markdown(f'<div class="signal-box sig-sell">{action} 📉</div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="signal-box sig-wait">{action} ✋</div>', unsafe_allow_html=True)

                        # Progress Bar (Síla signálu)
                        color = "#00ff41" if score > 50 else "#ff2b2b"
                        st.progress(score)
                        st.caption(f"🔮 Síla signálu: {score}%")

                        # Risk Management (jen pokud je akce)
                        if is_live and "WAIT" not in action:
                            st.markdown(f"""
                            <div class="risk-row">
                                <span class="sl-val">🛑 SL: {sl:.2f}</span>
                                <span class="tp-val">🎯 TP: {tp:.2f}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                             st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

                        # --- GRAF ZPĚT ZDE ---
                        fig = create_chart(df, score)
                        st.plotly_chart(fig, config={'displayModeBar': False}, key=f"g_{asset['sym']}_{time.time()}")
                        
                        st.divider()

                else:
                    st.warning(f"Načítám {asset['name']}...")

    time.sleep(15)