"""
Massive Triangular Arbitrage Dashboard on Binance (Production Cloud Ready)
========================================================================================
Run with: streamlit run app.py
"""

import random
import time
from datetime import datetime
import ccxt
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =========================================================
st.set_page_config(
    page_title="Binance Massive Triangular Arbitrage",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Massive Triangular Arbitrage")
st.caption(
    "Real-time massive scanning via Cloud Native Client with slippage, fee mitigation, and Circuit Breaker."
)

# =========================================================
# ESTADO GLOBAL Y SEGURIDAD
# =========================================================
if "balance_usdt" not in st.session_state:
    st.session_state.balance_usdt = 1000.0
if "initial_balance" not in st.session_state:
    st.session_state.initial_balance = 1000.0
if "trade_history" not in st.session_state:
    st.session_state.trade_history = []
if "balance_history" not in st.session_state:
    st.session_state.balance_history = [
        {"Time": datetime.now().strftime("%H:%M:%S"), "USDT": 1000.0}
    ]
if "running" not in st.session_state:
    st.session_state.running = False

# PROTECCIÓN DE PÉRDIDAS (CIRCUIT BREAKER)
if "consecutive_losing_trades" not in st.session_state:
    st.session_state.consecutive_losing_trades = 0
if "circuit_breaker_triggered" not in st.session_state:
    st.session_state.circuit_breaker_triggered = False

# =========================================================
# FUNCIONES OPTIMIZADAS PARA LA NUBE
# =========================================================
@st.cache_resource
def connect_exchange():
    """
    Inicializa CCXT activando el control automático de límite de velocidad.
    """
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

@st.cache_data(ttl=1800)  # Guarda en caché la estructura de mercados por 30 minutos
def get_base_markets(_exchange):
    try:
        markets = _exchange.load_markets()
    except Exception as e:
        st.error(f"Error conectando a Binance: {e}")
        return {}, []

    discarded_fiat = {
        "IDR", "BRL", "TRY", "RUB", "ARS", "UAH", "PLN", 
        "RON", "CZK", "ZAR", "NGN", "MXN", "COP"
    }

    spot_markets = {
        symbol: market
        for symbol, market in markets.items()
        if market.get("spot")
        and market.get("active")
        and market.get("base") not in discarded_fiat
        and market.get("quote") not in discarded_fiat
    }

    currency_count = {}
    for market in spot_markets.values():
        base, quote = market["base"], market["quote"]
        currency_count[base] = currency_count.get(base, 0) + 1
        currency_count[quote] = currency_count.get(quote, 0) + 1

    sorted_currencies = sorted(
        currency_count.keys(), key=lambda x: currency_count[x], reverse=True
    )

    return spot_markets, sorted_currencies

def build_routes(spot_markets, selected_currencies):
    main_currencies = {"USDT", "BTC", "ETH", "BNB", "FDUSD"}
    valid_currencies = set(selected_currencies)

    routes = []
    existing_pairs = {}
    for symbol, market in spot_markets.items():
        base, quote = market["base"], market["quote"]
        if base in valid_currencies and quote in valid_currencies:
            existing_pairs[(base, quote)] = {"symbol": symbol, "action": "sell"}
            existing_pairs[(quote, base)] = {"symbol": symbol, "action": "buy"}

    currency_list = list(valid_currencies)
    for a in main_currencies.intersection(valid_currencies):
        for b in currency_list:
            if a == b or (a, b) not in existing_pairs:
                continue
            for c in currency_list:
                if c == a or c == b:
                    continue
                if (b, c) in existing_pairs and (c, a) in existing_pairs:
                    routes.append(
                        {
                            "nodes": (a, b, c, a),
                            "steps": [
                                existing_pairs[(a, b)],
                                existing_pairs[(b, c)],
                                existing_pairs[(c, a)],
                            ],
                        }
                    )

    return routes

def calculate_arbitrage(tickers, route_info, capital, fee, min_volume=10000.0):
    amount = capital
    for step in route_info["steps"]:
        symbol = step["symbol"]
        action = step["action"]
        ticker = tickers.get(symbol)

        if not ticker or not ticker.get("ask") or not ticker.get("bid"):
            return None

        volume_24h = ticker.get("quoteVolume", 0) or 0
        if volume_24h < min_volume:
            return None

        ask = ticker["ask"]
        bid = ticker["bid"]

        if ask <= 0 or bid <= 0:
            return None

        spread = (ask - bid) / ask
        if spread > 0.01:
            return None

        if action == "buy":
            amount = (amount / ask) * (1 - fee)
        else:
            amount = (amount * bid) * (1 - fee)

    profit_pct = (amount - capital) / capital
    return amount, profit_pct

# =========================================================
# PANEL LATERAL (BARRA DE CONTROL Y RIESGO)
# =========================================================
st.sidebar.header("💰 Capital Management")

new_balance = st.sidebar.number_input(
    "Simulation Starting Balance (USDT):",
    min_value=10.0,
    value=float(st.session_state.initial_balance),
    step=100.0,
)

if new_balance != st.session_state.initial_balance:
    st.session_state.initial_balance = new_balance
    st.session_state.balance_usdt = new_balance
    st.session_state.balance_history = [
        {"Time": datetime.now().strftime("%H:%M:%S"), "USDT": new_balance}
    ]

st.sidebar.divider()
st.sidebar.header("🛡️ Loss Protection Guardrails")

max_consecutive_losses = st.sidebar.number_input(
    "Max Consecutive Losses Limit (Circuit Breaker):",
    min_value=1,
    max_value=10,
    value=2,
    help="Stops the bot immediately if this amount of consecutive losing trades is reached.",
)

simulate_slippage = st.sidebar.checkbox(
    "Simulate Slippage & Network Latency",
    value=True,
    help="Deducts between 0.02% and 0.08% extra per trade to emulate real execution conditions.",
)

st.sidebar.divider()
st.sidebar.header("⚙️ Coverage & Currencies")

exchange = connect_exchange()
spot_markets, sorted_currencies = get_base_markets(exchange)

coverage_mode = st.sidebar.selectbox(
    "Currency Preset:",
    ["Top 15 Currencies", "Top 50 Currencies", "All Available Currencies", "Custom"],
    index=0,  # Recomendado Top 15 para cuidar los Rate Limits en la nube
)

if coverage_mode == "Top 15 Currencies":
    default_currencies = sorted_currencies[:15]
elif coverage_mode == "Top 50 Currencies":
    default_currencies = sorted_currencies[:50]
elif coverage_mode == "All Available Currencies":
    default_currencies = sorted_currencies
else:
    default_currencies = sorted_currencies[:15]

selected_currencies = st.sidebar.multiselect(
    "Active Currencies in Scanner:",
    options=sorted_currencies,
    default=default_currencies,
)

valid_routes = build_routes(spot_markets, selected_currencies)

st.sidebar.divider()

trade_amount = st.sidebar.number_input(
    "Trade Amount per Simulation (USDT):", min_value=10.0, value=100.0, step=10.0
)

fee_pct = (
    st.sidebar.number_input(
        "Fee per Order (%):",
        min_value=0.0,
        max_value=1.0,
        value=0.100,
        step=0.001,
        format="%.3f",
    )
    / 100
)

profit_threshold = (
    st.sidebar.slider(
        "Minimum Required NET Profit (%):",
        min_value=0.0,
        max_value=3.0,
        value=0.15,
        step=0.01,
    )
    / 100
)

refresh_interval = st.sidebar.slider(
    "Refresh Interval (sec):", min_value=1, max_value=30, value=2
)

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    if st.button("▶️ Start", use_container_width=True):
        st.session_state.running = True
with col_btn2:
    if st.button("⏸️ Stop", use_container_width=True):
        st.session_state.running = False

if st.sidebar.button("🔄 Reset Balance & Guardrails", use_container_width=True):
    st.session_state.balance_usdt = st.session_state.initial_balance
    st.session_state.trade_history = []
    st.session_state.balance_history = [
        {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "USDT": st.session_state.initial_balance,
        }
    ]
    st.session_state.consecutive_losing_trades = 0
    st.session_state.circuit_breaker_triggered = False
    st.rerun()

# =========================================================
# CUERPO PRINCIPAL DEL DASHBOARD
# =========================================================
if st.session_state.circuit_breaker_triggered:
    st.error(
        f"🚨 **CIRCUIT BREAKER TRIGGERED:** Reached {st.session_state.consecutive_losing_trades} consecutive losses. "
        "The bot has halted automatic execution to protect remaining capital. Click 'Reset' in the sidebar to unblock."
    )

col1, col2, col3, col4 = st.columns(4)

pnl_abs = st.session_state.balance_usdt - st.session_state.initial_balance
pnl_pct = (
    (pnl_abs / st.session_state.initial_balance) * 100
    if st.session_state.initial_balance > 0
    else 0
)

col1.metric("Virtual Balance", f"{st.session_state.balance_usdt:.2f} USDT")
col2.metric(
    "Realistic Simulated PnL",
    f"{pnl_abs:+.2f} USDT",
    delta=f"{pnl_pct:+.2f}%",
)
col3.metric(
    "Consecutive Losses",
    f"{st.session_state.consecutive_losing_trades} / {max_consecutive_losses}",
)
col4.metric("Triangular Routes", len(valid_routes))

st.divider()

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("📈 Portfolio Growth")
    df_balance = pd.DataFrame(st.session_state.balance_history)
    fig = px.line(df_balance, x="Time", y="USDT", markers=True)
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("🎯 Filtered Opportunities (Post-Fee)")
    opportunities_container = st.empty()

st.subheader("📜 Executed Trades Log")
history_container = st.empty()

# =========================================================
# BUCLE EN TIEMPO REAL DIRECTO DESDE LA NUBE
# =========================================================
if st.session_state.running and not st.session_state.circuit_breaker_triggered:
    if not valid_routes:
        st.error(
            "No valid routes available for the selected currencies. Choose more currencies in the sidebar."
        )
    else:
        # Extraer únicamente los pares activos de las rutas filtradas
        active_symbols = list(
            set([step["symbol"] for route in valid_routes for step in route["steps"]])
        )

        try:
            # Consultar solo los tickers activos para no saturar la API
            tickers = exchange.fetch_tickers(active_symbols)
        except Exception as e:
            st.warning(f"Exceso de peticiones o aviso de Binance: ({e}). Reintentando...")
            tickers = {}

        opportunities = []

        if tickers:
            for route_info in valid_routes:
                res = calculate_arbitrage(
                    tickers, route_info, trade_amount, fee_pct
                )
                if res:
                    final_amount, profit_pct = res
                    if profit_pct >= profit_threshold:
                        route_str = " ➔ ".join(route_info["nodes"])
                        opportunities.append(
                            {
                                "Route": route_str,
                                "Net Profit (%)": round(profit_pct * 100, 3),
                                "Est. Profit (USDT)": round(
                                    final_amount - trade_amount, 3
                                ),
                                "Total Return": round(final_amount, 2),
                                "raw_data": (route_str, profit_pct, final_amount),
                            }
                        )

        if opportunities:
            df_ops = pd.DataFrame(opportunities).sort_values(
                by="Net Profit (%)", ascending=False
            )
            opportunities_container.dataframe(
                df_ops[["Route", "Net Profit (%)", "Est. Profit (USDT)"]],
                hide_index=True,
                use_container_width=True,
            )

            top_op = df_ops.iloc[0]["raw_data"]
            route_top, ben_top, final_top = top_op

            if st.session_state.balance_usdt >= trade_amount:
                theoretical_profit = final_top - trade_amount

                slippage_penalty = (
                    random.uniform(0.0002, 0.0008) if simulate_slippage else 0.0
                )
                real_profit = theoretical_profit - (
                    trade_amount * slippage_penalty
                )

                st.session_state.balance_usdt += real_profit

                if real_profit < 0:
                    st.session_state.consecutive_losing_trades += 1
                    if (
                        st.session_state.consecutive_losing_trades
                        >= max_consecutive_losses
                    ):
                        st.session_state.circuit_breaker_triggered = True
                        st.session_state.running = False
                else:
                    st.session_state.consecutive_losing_trades = 0

                st.session_state.trade_history.append(
                    {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Triangular Route": route_top,
                        "Real Yield": f"{(real_profit / trade_amount) * 100:+.3f}%",
                        "Net Result (USDT)": round(real_profit, 4),
                        "New Balance": round(st.session_state.balance_usdt, 2),
                    }
                )

                st.session_state.balance_history.append(
                    {
                        "Time": datetime.now().strftime("%H:%M:%S"),
                        "USDT": round(st.session_state.balance_usdt, 2),
                    }
                )
        else:
            opportunities_container.info(
                f"Scanning {len(valid_routes)} routes... None exceed threshold ({profit_threshold * 100:.2f}%)."
            )

        if st.session_state.trade_history:
            df_hist = pd.DataFrame(st.session_state.trade_history).iloc[::-1]
            history_container.dataframe(
                df_hist, hide_index=True, use_container_width=True
            )
        else:
            history_container.write("Awaiting first simulated trade...")

        # Intervalo seguro para evitar ser baneado en la nube
        time.sleep(refresh_interval)
        st.rerun()
else:
    if not st.session_state.circuit_breaker_triggered:
        st.info("💡 Click '▶️ Start' in the left sidebar to start scanning.")

    if st.session_state.trade_history:
        df_hist = pd.DataFrame(st.session_state.trade_history).iloc[::-1]
        history_container.dataframe(
            df_hist, hide_index=True, use_container_width=True
        )