import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import warnings
from datetime import datetime

# --- 1. CONFIG ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="Sniper Bot V14", page_icon="🧠", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS (FIXED MARGINS & LAYOUT) ---
st.markdown("""
    <style>
    /* Globální reset */
    .stApp { background-color: #050505; font-family: 'Helvetica Neue', sans-serif; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    
    /* === HLAVIČKA KARTY === */
    .header-flex {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 10px;
    }
    
    .symbol-title { font-size: 28px; font-weight: 900; color: #fff; line-height: 1; }
    .symbol-desc { font-size: 14px; color: #888; font-weight: bold; text-transform: uppercase; margin-top: 5px; }
    
    .price-box { text-align: right; }
    .price-main { font-size: 38px; font-weight: 700; color: #fff; font-family: monospace; line-height: 1; text-shadow: 0 0 10px rgba(255,255,255,0.1); }
    .price-change { font-size: 16px; font-weight: bold; margin-top: 5px; }
    .change-up { color: #00e676; }
    .change-down { color: #ff4444; }
    
    /* === SIGNÁL === */
    .signal-box {
        text-align: center;
        padding: 15px;
        border-radius: 8px;
        font-weight: 900;
        font-size: 20px;
        text-transform: uppercase;
        margin: 15px 0;
        color: #000;
        letter-spacing: 1px;
    }
    
    /* === RISK MANAGEMENT === */
    .risk-wrapper {
        display: flex;
        justify-content: space-between;
        background-color: #151515;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 15px;
        margin-top: 15px;
        width: 100%; 
        box-sizing: border-box !important; 
    }
    
    .risk-col { display: flex; flex-direction: column; }
    .risk-label { font-size: 11px; color: #666; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .risk-val { font-size: 22px; font-weight: bold; font-family: monospace; }
    
    .sl-text { color: #ff4444; text-shadow: 0 0 10px rgba(255, 68, 68, 0.2); }
    .tp-text { color: #00e676; text-shadow: 0 0 10px rgba(0, 230, 118, 0.2); }
    
    /* === AI ACCURACY (FIXED MARGIN) === */
    .ai-container {
        margin-top: 15px;
        text-align: center;
        padding-top: 10px;
        padding-bottom: 10px; /* Přidáno místo dole */
        border-top: 1px solid #222;
        margin-bottom: 5px; /* Extra odsazení od okraje karty */
    }
    
    .ai-label {
        font-size: 12px;
        color: #aaa;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 5px;
    }
    
    .ai-score {
        font-size: 18px;
        font-weight: 900;
        color: #fff;
    }
    
    .ai-bar-bg {
        width: 100%;
        height: 6px;
        background-color: #222;
        border-radius: 3px;
        margin-top: 8px;
        overflow: hidden;
    }
    
    .ai-bar-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 1s ease-in-out;
    }

    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 3. POMOCNÉ FUNKCE ---
def hex_to_rgba(hex_color, alpha=0.2):
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})"

# --- 4. DATA ENGINE (S MACD) ---
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

        # EMA 200 (Trend)
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # MACD (Novinka - Hybnost)
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

        # Bollinger Bands
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['STD_20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)

        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()

        return df
    except:
        return None

# --- 5. LOGIKA ANALÝZY (CHYTŘEJŠÍ) ---
def analyze_market(df):
    row = df.iloc[-1]
    price = row['Close']
    atr = row['ATR']
    
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    is_live = diff < 120 or now.weekday() >= 5 

    score = 50
    
    # 1. TREND (EMA 200)
    trend_up = price > row['EMA_200']
    if trend_up: score += 10
    else: score -= 10

    # 2. RSI INTELIGENCE (Ochrana proti pozdním vstupům)
    rsi = row['RSI']
    
    if trend_up:
        if rsi < 45: score += 15     # Pullback v trendu (Dobré)
        elif rsi > 70: score -= 10   # Moc vysoko (Nebezpečné koupit)
    else:
        if rsi > 55: score -= 15     # Odraz dolů (Dobré)
        elif rsi < 30: score += 15   # !!! Moc nízko - Pozor na prodej (Nebezpečné prodat)

    # 3. BOLLINGER BANDS (Odrazy)
    if price <= row['BB_Lower']: score += 20  # Cena je levná
    if price >= row['BB_Upper']: score -= 20  # Cena je drahá
    
    # 4. MACD (Potvrzení hybnosti)
    # Pokud MACD roste nad Signálem, podporuje to růst
    if row['MACD'] > row['Signal_Line']: score += 5
    else: score -= 5

    score = max(0, min(100, score))

    # Rozhodování (Zpřísněné limity)
    if score >= 65: # Zvýšeno z 60 na 65 pro méně falešných signálů
        action = "LONG / KOUPIT 🚀"
        color = "#00e676" 
    elif score <= 35: # Sníženo ze 40 na 35
        action = "SHORT / PRODAT 📉"
        color = "#ff4444" 
    else: 
        action = "WAIT / ČEKAT ✋"
        color = "#888888" 

    sl = price - (2*atr) if score > 50 else price + (2*atr)
    tp = price + (3*atr) if score > 50 else price - (3*atr)

    return score, action, color, sl, tp, is_live

# --- 6. GRAF ---
def create_chart(df, color):
    subset = df.tail(50)
    
    y_min = subset['Close'].min()
    y_max = subset['Close'].max()
    padding = (y_max - y_min) * 0.1
    if padding == 0: padding = y_max * 0.01

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=subset.index, y=subset['Close'],
        mode='lines',
        line=dict(color=color, width=3),
        fill='tozeroy', 
        fillcolor=hex_to_rgba(color, 0.15),
    ))

    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.05)', width=1), hoverinfo='skip'))

    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=10),
        height=200,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True, range=[y_min - padding, y_max + padding]),
        showlegend=False,
        hovermode="x unified"
    )
    return fig

# --- 7. MAIN APP ---
st.title("🧠 SNIPER TRADING V14")
placeholder = st.empty()

while True:
    with placeholder.container():
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
            with cols[i % 2]: 
                with st.container(border=True):
                    df = get_data(asset['sym'])
                    
                    if df is not None:
                        score, action, color, sl, tp, is_live = analyze_market(df)
                        price = df.iloc[-1]['Close']
                        pct_change = df.iloc[-1]['Pct_Change']
                        
                        change_class = "change-up" if pct_change >= 0 else "change-down"
                        arrow = "▲" if pct_change >= 0 else "▼"
                        change_str = f"{arrow} {abs(pct_change):.2f}%"

                        # HLAVIČKA
                        st.markdown(f"""
                            <div class="header-flex">
                                <div>
                                    <div class="symbol-title">{asset['name']}</div>
                                    <div class="symbol-desc">{asset['desc']}</div>
                                </div>
                                <div class="price-box">
                                    <div class="price-main">{price:.2f}</div>
                                    <div class="price-change {change_class}">{change_str}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # SIGNÁL
                        st.markdown(f"""
                            <div class="signal-box" style="background-color: {color}; box-shadow: 0 0 25px {hex_to_rgba(color, 0.4)};">
                                {action}
                            </div>
                        """, unsafe_allow_html=True)

                        # GRAF
                        chart_key = f"chart_{asset['sym']}_{int(time.time())}"
                        fig = create_chart(df, color)
                        st.plotly_chart(fig, config={'displayModeBar': False}, key=chart_key, use_container_width=True)

                        # RISK MANAGEMENT
                        if is_live and score != 50 and "WAIT" not in action:
                            st.markdown(f"""
                                <div class="risk-wrapper">
                                    <div class="risk-col">
                                        <span class="risk-label">STOP LOSS 🛑</span>
                                        <span class="risk-val sl-text">{sl:.2f}</span>
                                    </div>
                                    <div class="risk-col" style="text-align: right;">
                                        <span class="risk-label">TAKE PROFIT 🎯</span>
                                        <span class="risk-val tp-text">{tp:.2f}</span>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            # AI ACCURACY (S odsazením)
                            st.markdown(f"""
                                <div class="ai-container">
                                    <div class="ai-label">🤖 AI PŘESNOST</div>
                                    <div class="ai-score">{score}%</div>
                                    <div class="ai-bar-bg">
                                        <div class="ai-bar-fill" style="width: {score}%; background-color: {color}; box-shadow: 0 0 10px {color};"></div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                        else:
                             # Spacer pro zarovnání, když není signál
                             st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

                    else:
                        st.warning(f"Načítám {asset['name']}...")

        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    
    time.sleep(15)