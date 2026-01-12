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
os.environ["STREAMLIT_SILENCE_DEPRECATION_WARNINGS"] = "1"

st.set_page_config(page_title="Trading Sniper PRO", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS STYLING ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .no-select { -webkit-user-select: none; -ms-user-select: none; user-select: none; cursor: default; }
    
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
    .symbol-name { font-size: 18px; font-weight: 700; color: #fff; }

    .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
    .badge-open { background-color: #00ff41; color: #000; box-shadow: 0 0 10px rgba(0, 255, 65, 0.4); }
    .badge-closed { background-color: #333; color: #888; border: 1px solid #555; }

    .price-tag { font-size: 28px; font-weight: 800; color: #fff; margin-bottom: 5px; font-family: 'Courier New', monospace; }
    
    /* TREND INDICATOR */
    .trend-indicator { font-size: 13px; font-weight: 600; margin-bottom: 15px; letter-spacing: 0.5px; }
    .trend-down { color: #ff2b2b; }
    .trend-up { color: #00ff41; }

    .action-container { 
        display: flex; justify-content: center; align-items: center; text-align: center;
        height: 70px; border-radius: 8px; margin-bottom: 15px; 
        font-weight: 900; font-size: 20px; text-transform: uppercase; letter-spacing: 1px;
        line-height: 1.2;
    }
    
    .act-buy { background-color: #00ff41; color: #000; border: 2px solid #00ff41; box-shadow: 0 0 15px rgba(0, 255, 65, 0.3); }
    .act-sell { background-color: #ff2b2b; color: #fff; border: 2px solid #ff2b2b; box-shadow: 0 0 15px rgba(255, 43, 43, 0.3); }
    .act-wait { background-color: #262730; border: 2px solid #555; color: #aaa; }
    .act-offline { background-color: #111; border: 2px dashed #333; color: #444; }
    
    .stProgress > div > div > div > div { background-color: #00ff41; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=15)
def get_market_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False, multi_level_index=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        if df.empty or len(df) < 50: return None, None
            
        # TIMEZONE FIX
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        return df.iloc[-1], df
    except: return None, None

def analyze_logic_smart(row):
    """
    Logika, která respektuje hlavní trend (EMA 200).
    """
    score = 50.0 
    reasons = []
    
    # Časová kontrola
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    is_open = diff < 40

    if not is_open:
        return 50, False, "NEZNÁMÝ", [] 

    price = float(row['Close'])
    ema = float(row['EMA_200'])
    rsi = float(row['RSI'])
    macd = float(row['MACD'])
    signal = float(row['Signal_Line'])

    # 1. URČENÍ HLAVNÍHO TRENDU (EMA 200)
    if price > ema:
        main_trend = "UP" # Rostoucí
        score += 10 # Bonus za uptrend
    else:
        main_trend = "DOWN" # Klesající
        score -= 10 # Bonus za downtrend

    # 2. RSI (Síla)
    # RSI > 70 = Drahé (Sell), RSI < 30 = Levné (Buy)
    if rsi > 70: score -= 20
    elif rsi < 30: score += 20
    else: 
        # Pokud je RSI uprostřed (50), táhneme skóre směrem k trendu
        if main_trend == "DOWN" and rsi > 50: score -= 5
        if main_trend == "UP" and rsi < 50: score += 5

    # 3. MACD (Momentum)
    macd_hist = macd - signal
    momentum = macd_hist * 100000 if price < 100 else macd_hist * 10
    momentum = max(-20, min(20, momentum))
    score += momentum

    # 4. PENALIZACE PROTI TRENDU (Smart Filter)
    # Pokud je trend DOLŮ (cena pod EMA), ale indikátory křičí NÁKUP (skóre > 60),
    # tak to skóre uměle snížíme, protože je to riskantní.
    if main_trend == "DOWN" and score > 60:
        score -= 20 # Snížíme nadšení pro nákup
        reasons.append("Risk: Proti trendu")
        
    # Naopak: Pokud je trend DOLŮ a signál je PRODEJ, přidáme plyn.
    if main_trend == "DOWN" and score < 40:
        score -= 10 # Boost pro prodej

    final_score = int(max(0, min(100, score)))
    return final_score, is_open, main_trend, reasons

# --- 4. MAIN APP ---
st.title("🎯 Trading Sniper PRO v6.0")
st.markdown("#### ⚡ Trend Master Edition")

placeholder = st.empty()

while True:
    with placeholder.container():
        refresh_id = datetime.now().strftime('%H%M%S')
        st.write(f"🕒 Aktualizováno: **{datetime.now().strftime('%H:%M:%S')}**")

        cols = st.columns(4)
        
        symbols = [
            {"sym": "EURUSD=X", "name": "EUR / USD", "col": cols[0]},
            {"sym": "GBPUSD=X", "name": "GBP / USD", "col": cols[1]},
            {"sym": "BTC-USD", "name": "BITCOIN", "col": cols[2]},
            {"sym": "GC=F", "name": "GOLD", "col": cols[3]}
        ]

        for item in symbols:
            with item["col"]:
                with st.container(border=True):
                    row, df = get_market_data(item["sym"])
                    
                    if row is not None:
                        score, is_open, main_trend, reasons = analyze_logic_smart(row)
                        price = float(row['Close'])
                        
                        # LOGIKA ZOBRAZENÍ
                        if not is_open:
                            badge_html = "<span class='badge badge-closed'>Zavřeno</span>"
                            action_class = "act-offline"
                            action_text = "OFFLINE 💤"
                            trend_html = "<span style='color:#666'>Trh spí</span>"
                            bar_color = "grey"
                        else:
                            badge_html = "<span class='badge badge-open'>LIVE 🟢</span>"
                            
                            # Vypisujeme Trend
                            if main_trend == "DOWN":
                                trend_html = "<span class='trend-down'>📉 HLAVNÍ TREND: DOLŮ (HLEDEJ POKLES)</span>"
                            else:
                                trend_html = "<span class='trend-up'>🚀 HLAVNÍ TREND: NAHORU (HLEDEJ RŮST)</span>"

                            # Akce podle skóre
                            if score >= 75: action_text = "SÁZET NA<br>RŮST (BUY) 🚀"; action_class = "act-buy"; bar_color="green"
                            elif score >= 55: action_text = "SÁZET NA<br>RŮST (BUY) ↗"; action_class = "act-buy"; bar_color="green"
                            elif score <= 25: action_text = "SÁZET NA<br>POKLES (SELL) 📉"; action_class = "act-sell"; bar_color="red"
                            elif score <= 45: action_text = "SÁZET NA<br>POKLES (SELL) ↘"; action_class = "act-sell"; bar_color="red"
                            else: action_text = "NEUTRAL<br>ČEKAT ✋"; action_class = "act-wait"; bar_color="yellow"

                        st.markdown(f"""
                        <div class="no-select">
                            <div class="card-header"><span class="symbol-name">{item['name']}</span>{badge_html}</div>
                            <div class="price-tag">{price:.2f}</div>
                            <div class="trend-indicator">{trend_html}</div>
                            <div class="action-container {action_class}">{action_text}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        st.markdown(f"""
                        <div style="background-color: #333; border-radius: 5px; height: 10px; width: 100%;">
                            <div style="background-color: {bar_color}; width: {score}%; height: 100%; border-radius: 5px; transition: width 0.5s;"></div>
                        </div>
                        <div style="text-align: right; font-size: 12px; margin-top: 5px; color: #aaa;">AI PŘESNOST: <b>{score}%</b></div>
                        """, unsafe_allow_html=True)

                        line_col = '#555'
                        fill_col = 'rgba(0,0,0,0)'
                        subset_data = df.tail(40)
                        
                        if is_open:
                            line_col = '#00ff41' if score > 50 else '#ff2b2b'
                            fill_col = f"rgba({0 if score>50 else 255}, {255 if score>50 else 0}, 0, 0.1)"

                        y_min = subset_data['Close'].min()
                        y_max = subset_data['Close'].max()
                        padding = (y_max - y_min) * 0.1 if y_max != y_min else y_max * 0.001
                        
                        fig = go.Figure(data=go.Scatter(
                            x=subset_data.index, 
                            y=subset_data['Close'], 
                            mode='lines',
                            line=dict(color=line_col, width=2),
                            fill='tozeroy',
                            fillcolor=fill_col,
                            hovertemplate='<b>Čas:</b> %{x|%H:%M}<br><b>Cena:</b> %{y:.2f}<extra></extra>'
                        ))
                        
                        fig.update_layout(
                            margin=dict(l=0, r=0, t=10, b=0),
                            height=40,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(showgrid=False, showticklabels=False),
                            yaxis=dict(showgrid=False, showticklabels=False, range=[y_min - padding, y_max + padding]),
                            hovermode="x unified"
                        )
                        st.plotly_chart(fig, config={'displayModeBar': False}, key=f"g_{item['sym']}_{refresh_id}")

                    else:
                        st.warning("Načítám...")

        st.divider()
        st.caption("Auto-refresh 15s. Powered by Python.")

    time.sleep(15)