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

st.set_page_config(page_title="High Leverage Sniper v8", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS STYLING (Agresivní vzhled) ---
st.markdown("""
    <style>
    .stApp { background-color: #000000; }
    .no-select { -webkit-user-select: none; -ms-user-select: none; user-select: none; cursor: default; }
    
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
    .symbol-name { font-size: 20px; font-weight: 800; color: #fff; letter-spacing: 1px; }

    .badge-leverage { background-color: #ff9900; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }

    .price-tag { font-size: 32px; font-weight: 900; color: #fff; font-family: 'Courier New', monospace; text-shadow: 0 0 10px rgba(255,255,255,0.2); }
    
    .action-box { 
        text-align: center; padding: 10px; border-radius: 6px; margin: 10px 0;
        font-weight: 900; font-size: 24px; text-transform: uppercase; 
    }
    .buy { background: #00ff41; color: black; box-shadow: 0 0 20px rgba(0,255,65,0.4); }
    .sell { background: #ff2b2b; color: white; box-shadow: 0 0 20px rgba(255,43,43,0.4); }
    .wait { background: #222; color: #555; border: 1px solid #444; }

    .risk-row { display: flex; justify-content: space-between; font-family: monospace; font-size: 14px; margin-top: 5px; }
    .sl-val { color: #ff2b2b; }
    .tp-val { color: #00ff41; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATA ENGINE (YFINANCE FUTURES) ---
@st.cache_data(ttl=15, show_spinner=False)
def get_futures_data(symbol):
    try:
        # Použijeme čisté stažení bez session (nejspolehlivější metoda teď)
        ticker = yf.Ticker(symbol)
        # Stáhneme data - period 5d pro výpočet EMA 200
        df = ticker.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 50: return None, None
            
        # Timezone fix
        if df.index.tzinfo is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Europe/Prague')

        # --- INDIKÁTORY PRO PÁKU ---
        # 1. Trend (EMA 200) - Páka se obchoduje jen po trendu!
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # 2. RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. Bollinger Bands (20, 2) - Pro odrazy
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['STD_20'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['STD_20'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['STD_20'] * 2)

        # 4. ATR (14) - Pro výpočet Stop Lossu
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df['ATR'] = ranges.max(axis=1).rolling(14).mean()

        return df.iloc[-1], df
    except:
        return None, None

def sniper_logic(row):
    score = 50
    reasons = []
    
    # Check stáří dat (Futures mají pauzu 23:00-00:00)
    last_time = row.name
    now = pd.Timestamp.now(tz='Europe/Prague')
    diff = (now - last_time).total_seconds() / 60
    
    # Forex stojí o víkendu, Futures taky
    is_weekend = now.weekday() >= 5
    is_open = diff < 60 or is_weekend # Tolerance pro zpoždění

    price = row['Close']
    ema = row['EMA_200']
    rsi = row['RSI']
    bb_low = row['BB_Lower']
    bb_high = row['BB_Upper']
    atr = row['ATR']

    # 1. URČENÍ TRENDU
    trend = "UP" if price > ema else "DOWN"
    
    # 2. VSTUPNÍ LOGIKA (Mean Reversion v Trendu)
    if trend == "UP":
        if price <= bb_low * 1.0005: # Cena na spodním pásmu
            score += 25; reasons.append("Touch BB Low")
        if rsi < 40: 
            score += 15; reasons.append("RSI Oversold")
    else: # DOWN
        if price >= bb_high * 0.9995: # Cena na horním pásmu
            score -= 25; reasons.append("Touch BB High")
        if rsi > 60:
            score -= 15; reasons.append("RSI Overbought")

    # 3. FILTR SILNÉHO POHYBU (Breakout)
    # Pokud svíčka proráží pásmo a RSI je extrémní, jdeme proti (Reversal)
    if rsi > 75: score -= 10; reasons.append("RSI Extreme High")
    if rsi < 25: score += 10; reasons.append("RSI Extreme Low")

    final_score = max(0, min(100, score))
    
    # 4. RISK MANAGEMENT (Klíčové pro páku)
    # Pro páku chceme těsnější SL (1.5x ATR) a větší TP (3x ATR)
    sl = price - (1.5 * atr) if final_score > 50 else price + (1.5 * atr)
    tp = price + (3.0 * atr) if final_score > 50 else price - (3.0 * atr)

    return final_score, is_open, trend, reasons, sl, tp

# --- 4. MAIN APP ---
st.title("⚡ Futures & Forex Sniper")
st.markdown("Optimalizováno pro vysokou volatilitu a páku (S&P 500, Gold, Oil)")

placeholder = st.empty()

while True:
    with placeholder.container():
        st.caption(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
        
        cols = st.columns(4)
        
        # ZDE JSOU SYMBOLY PRO VYSOKOU PÁKU (FUTURES)
        # =F znamená Futures kontrakt (často lepší data než indexy)
        assets = [
            {"sym": "ES=F", "name": "S&P 500", "lev": "1:500", "col": cols[0]},  # Futures S&P
            {"sym": "NQ=F", "name": "NASDAQ", "lev": "1:500", "col": cols[1]},   # Futures Nasdaq
            {"sym": "GC=F", "name": "GOLD (XAU)", "lev": "1:100", "col": cols[2]}, # Zlato
            {"sym": "EURUSD=X", "name": "EUR/USD", "lev": "1:30", "col": cols[3]}  # Forex
        ]

        for asset in assets:
            with asset["col"]:
                with st.container(border=True):
                    # Header
                    st.markdown(f"""
                        <div class="card-header">
                            <span class="symbol-name">{asset['name']}</span>
                            <span class="badge-leverage">{asset['lev']}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    row, df = get_futures_data(asset['sym'])
                    
                    if row is not None:
                        score, is_open, trend, reasons, sl, tp = sniper_logic(row)
                        
                        # Price
                        st.markdown(f'<div class="price-tag">{row["Close"]:.2f}</div>', unsafe_allow_html=True)
                        
                        # Action Logic
                        if not is_open:
                            st.markdown('<div class="action-box wait" style="font-size:16px">ZAVŘENO 💤</div>', unsafe_allow_html=True)
                        elif score >= 65:
                            st.markdown('<div class="action-box buy">LONG (BUY) 🚀</div>', unsafe_allow_html=True)
                        elif score <= 35:
                            st.markdown('<div class="action-box sell">SHORT (SELL) 📉</div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="action-box wait">WAIT ✋</div>', unsafe_allow_html=True)
                            
                        # Risk Management (SL/TP)
                        if is_open and (score >= 65 or score <= 35):
                            st.markdown(f"""
                            <div class="risk-row">
                                <span class="sl-val">STOP: {sl:.2f}</span>
                                <span class="tp-val">TARGET: {tp:.2f}</span>
                            </div>
                            """, unsafe_allow_html=True)

                        # Trend Bar
                        color = "#00ff41" if score > 50 else "#ff2b2b"
                        st.progress(score)
                        
                        # Reasons
                        if reasons:
                            st.caption(f"Signál: {', '.join(reasons)}")

                        # Chart (BB)
                        if is_open:
                            subset = df.tail(30)
                            fig = go.Figure()
                            
                            # Svíčky (nebo linka)
                            fig.add_trace(go.Scatter(x=subset.index, y=subset['Close'], mode='lines', line=dict(color=color, width=2)))
                            
                            # Bollinger Bands
                            fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Upper'], line=dict(color='rgba(255,255,255,0.2)', width=1), hoverinfo='skip'))
                            fig.add_trace(go.Scatter(x=subset.index, y=subset['BB_Lower'], line=dict(color='rgba(255,255,255,0.2)', width=1), fill='tonexty', fillcolor='rgba(255,255,255,0.05)', hoverinfo='skip'))

                            fig.update_layout(
                                margin=dict(l=0, r=0, t=0, b=0),
                                height=50,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(visible=False),
                                yaxis=dict(visible=False),
                                showlegend=False
                            )
                            st.plotly_chart(fig, config={'displayModeBar': False}, key=f"chart_{asset['sym']}_{time.time()}")
                            
                    else:
                        st.warning("Data načítám...")

    time.sleep(15)