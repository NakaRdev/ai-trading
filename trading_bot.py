import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import warnings
import os
from datetime import datetime, timedelta

# --- PRO OPRAVU YFINANCE (Session & Caching) ---
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter

# --- 1. CONFIG & SESSION SETUP ---
warnings.filterwarnings("ignore")
os.environ["STREAMLIT_SILENCE_DEPRECATION_WARNINGS"] = "1"

st.set_page_config(page_title="Trading Sniper PRO v6", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

# Nastavení "Smart Session" pro Yahoo Finance
# Toto zabrání blokování IP adresy tím, že omezí rychlost dotazů a ukládá data do cache
class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

# Limit: Max 2 dotazy za 5 sekund (Yahoo je citlivé)
session = CachedLimiterSession(
    limiter=Limiter(RequestRate(2, Duration.SECOND*5)),
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache("yfinance.cache", expire_after=60), # Cache platí 60 sekund
)

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
        height: 70px; border-radius: 8px; margin-bottom: 10px; 
        font-weight: 900; font-size: 20px; text-transform: uppercase; letter-spacing: 1px;
        line-height: 1.2;
    }
    
    .act-buy { background-color: #00ff41; color: #000; border: 2px solid #00ff41; box-shadow: 0 0 15px rgba(0, 255, 65, 0.3); }
    .act-sell { background-color: #ff2b2b; color: #fff; border: 2px solid #ff2b2b; box-shadow: 0 0 15px rgba(255, 43, 43, 0.3); }
    .act-wait { background-color: #262730; border: 2px solid #555; color: #aaa; }
    .act-offline { background-color: #111; border: 2px dashed #333; color: #444; }
    
    .risk-box { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; font-family: monospace; background: #1c1e24; padding: 5px; border-radius: 4px; }
    .risk-sl { color: #ff2b2b; font-weight: bold; }
    .risk-tp { color: #00ff41; font-weight: bold; }
    
    .stProgress > div > div > div > div { background-color: #00ff41; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATA ENGINE (VYLEPŠENÝ) ---
@st.cache_data(ttl=15, show_spinner=False)
def get_market_data(symbol):
    try:
        # Používáme naši smart session
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 50: return None, None
            
        # TIMEZONE FIX
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        # --- VÝPOČET INDIKÁTORŮ ---
        
        # 1. EMA 200 (Trend)
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # 2. RSI (Síla)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. MACD (Momentum)
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # 4. BOLLINGER BANDS (Volatilita)
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['STD_20'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)

        # 5. ATR (Pro výpočet Stop Loss)
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()

        return df.iloc[-1], df
    except Exception as e:
        # st.error(f"Chyba dat: {e}") 
        return None, None

def analyze_logic_smart(row):
    """
    Pokročilá logika "Sniper"
    """
    score = 50.0 
    reasons = []
    
    # Časová kontrola (tolerance 60 min kvůli zpoždění Yahoo)
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    is_open = diff < 65 

    if not is_open:
        return 50, False, "NEZNÁMÝ", [], 0.0, 0.0

    # Načtení hodnot
    price = float(row['Close'])
    ema = float(row['EMA_200'])
    rsi = float(row['RSI'])
    macd = float(row['MACD'])
    signal = float(row['Signal_Line'])
    bb_upper = float(row['BB_Upper'])
    bb_lower = float(row['BB_Lower'])
    atr = float(row['ATR'])

    # 1. URČENÍ HLAVNÍHO TRENDU (EMA 200)
    if price > ema:
        main_trend = "UP"
        score += 5
    else:
        main_trend = "DOWN"
        score -= 5

    # 2. RSI + BOLLINGER BANDS KOMBO (Sniper Vstupy)
    # Hledáme odrazy od pásem ve směru trendu
    
    if main_trend == "UP":
        # Cena je dole (sleva) v rostoucím trendu
        if price <= bb_lower * 1.001: 
            score += 20
            reasons.append("Cena na BB Low (Buy Zone)")
        if rsi < 45: 
            score += 15
            reasons.append("RSI pod 45 (Pullback)")
        # Pokud je cena nahoře, opatrně
        if price >= bb_upper:
            score -= 10
            reasons.append("Cena nahoře (Resistance)")

    elif main_trend == "DOWN":
        # Cena je nahoře (drahé) v klesajícím trendu
        if price >= bb_upper * 0.999:
            score -= 20
            reasons.append("Cena na BB High (Sell Zone)")
        if rsi > 55:
            score -= 15
            reasons.append("RSI nad 55 (Pullback)")
        # Pokud je cena dole, opatrně
        if price <= bb_lower:
            score += 10
            reasons.append("Cena dole (Support)")

    # 3. MACD (Momentum)
    if macd > signal: score += 10
    else: score -= 10

    # 4. SQUEEZE FILTR (Nízká volatilita)
    bb_width = (bb_upper - bb_lower) / price
    if bb_width < 0.0015: # Extrémně úzké pásmo (trh spí)
        score = 50 + (score - 50) * 0.5 # Snížíme sílu signálu
        reasons.append("Squeeze (Nízká volatilita)")

    final_score = int(max(0, min(100, score)))
    
    # 5. RISK MANAGEMENT (SL / TP)
    sl = 0.0
    tp = 0.0
    
    # Buy signál
    if final_score >= 55:
        sl = price - (2.0 * atr) # Stop pod volatilitou
        tp = price + (3.0 * atr) # Target 1.5x risk
        
    # Sell signál
    elif final_score <= 45:
        sl = price + (2.0 * atr)
        tp = price - (3.0 * atr)

    return final_score, is_open, main_trend, reasons, sl, tp

# --- 4. MAIN APP ---
st.title("🎯 Trading Sniper PRO v6.0")
st.markdown("#### ⚡ Data Engine: YFinance Smart-Session")

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
                        score, is_open, main_trend, reasons, sl, tp = analyze_logic_smart(row)
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
                                trend_html = "<span class='trend-down'>📉 HLAVNÍ TREND: DOLŮ</span>"
                            else:
                                trend_html = "<span class='trend-up'>🚀 HLAVNÍ TREND: NAHORU</span>"

                            # Akce podle skóre
                            if score >= 75: action_text = "STRONG BUY 🚀"; action_class = "act-buy"; bar_color="#00ff41"
                            elif score >= 55: action_text = "BUY ↗"; action_class = "act-buy"; bar_color="#00ff41"
                            elif score <= 25: action_text = "STRONG SELL 📉"; action_class = "act-sell"; bar_color="#ff2b2b"
                            elif score <= 45: action_text = "SELL ↘"; action_class = "act-sell"; bar_color="#ff2b2b"
                            else: action_text = "WAIT ✋"; action_class = "act-wait"; bar_color="#ffcc00"

                        # Karta HTML
                        st.markdown(f"""
                        <div class="no-select">
                            <div class="card-header"><span class="symbol-name">{item['name']}</span>{badge_html}</div>
                            <div class="price-tag">{price:.2f}</div>
                            <div class="trend-indicator">{trend_html}</div>
                            <div class="action-container {action_class}">{action_text}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Progress Bar + AI Přesnost
                        st.markdown(f"""
                        <div style="background-color: #333; border-radius: 5px; height: 8px; width: 100%; margin-bottom: 5px;">
                            <div style="background-color: {bar_color}; width: {score}%; height: 100%; border-radius: 5px; transition: width 0.5s;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:12px; color:#aaa;">
                            <span>AI SKÓRE</span>
                            <span><b>{score}/100</b></span>
                        </div>
                        """, unsafe_allow_html=True)

                        # SL / TP Box (Jen když je trh aktivní a skóre není neutrál)
                        if is_open and score != 50:
                            st.markdown(f"""
                            <div class="risk-box">
                                <span class="risk-sl">🛑 SL: {sl:.4f}</span>
                                <span class="risk-tp">🎯 TP: {tp:.4f}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown("<div style='height: 33px;'></div>", unsafe_allow_html=True) # Spacer

                        # Důvody (Reasons)
                        if reasons:
                            reason_str = ", ".join(reasons)
                            st.caption(f"💡 {reason_str}")
                        else:
                            st.caption("🔍 Analyzuji...")

                        # GRAF
                        line_col = '#555'
                        fill_col = 'rgba(0,0,0,0)'
                        subset_data = df.tail(40)
                        
                        if is_open:
                            line_col = bar_color
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
                            fillcolor=fill_col
                        ))
                        
                        # Přidání Bollinger Bands do grafu (tenké čáry)
                        fig.add_trace(go.Scatter(x=subset_data.index, y=subset_data['BB_Upper'], line=dict(color='rgba(255,255,255,0.1)', width=1), hoverinfo='skip'))
                        fig.add_trace(go.Scatter(x=subset_data.index, y=subset_data['BB_Lower'], line=dict(color='rgba(255,255,255,0.1)', width=1), hoverinfo='skip'))
                        
                        fig.update_layout(
                            margin=dict(l=0, r=0, t=10, b=0),
                            height=50,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(showgrid=False, showticklabels=False),
                            yaxis=dict(showgrid=False, showticklabels=False, range=[y_min - padding, y_max + padding]),
                            showlegend=False,
                            hovermode="x unified"
                        )
                        st.plotly_chart(fig, config={'displayModeBar': False}, key=f"g_{item['sym']}_{refresh_id}")

                    else:
                        st.warning("Načítám nebo chyba dat...")

        st.divider()
        st.caption("Auto-refresh 15s. Používá Smart-Session pro Yahoo Finance.")

    time.sleep(15)