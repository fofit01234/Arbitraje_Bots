"""
Dashboard de Arbitraje Triangular Masivo en Binance (Paper Trading)
===================================================================
Ejecutar con: streamlit run app.py
"""

import time
import ccxt
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime

# =========================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =========================================================
st.set_page_config(
    page_title="Binance Massive Triangular Arbitrage",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Arbitraje Triangular Masivo — Binance")
st.caption("Escanear automáticamente todas las combinaciones operables con volumen real.")

# =========================================================
# ESTADO GLOBAL DE LA APLICACIÓN
# =========================================================
if "balance_usdt" not in st.session_state:
    st.session_state.balance_usdt = 1000.0
if "balance_inicial" not in st.session_state:
    st.session_state.balance_inicial = 1000.0
if "historial_trades" not in st.session_state:
    st.session_state.historial_trades = []
if "historial_balance" not in st.session_state:
    st.session_state.historial_balance = [{"Hora": datetime.now().strftime("%H:%M:%S"), "USDT": 1000.0}]
if "running" not in st.session_state:
    st.session_state.running = False


# =========================================================
# FUNCIONES OPTIMIZADAS DE EXTRACCIÓN Y RUTA
# =========================================================
@st.cache_resource
def conectar_exchange():
    return ccxt.binance({"enableRateLimit": True})

@st.cache_data(ttl=3600)  # Recarga la lista de mercados cada hora
def obtener_mercados_base(_exchange):
    try:
        mercados = _exchange.load_markets()
    except Exception as e:
        st.error(f"Error al conectar con Binance: {e}")
        return {}, []

    # Excluir monedas Fiat de muy baja liquidez para evitar falsos positivos
    fiat_descartadas = {"IDR", "BRL", "TRY", "RUB", "ARS", "UAH", "PLN", "RON", "CZK", "ZAR", "NGN", "MXN", "COP"}

    mercados_spot = {
        symbol: market for symbol, market in mercados.items()
        if market['spot'] and market['active'] 
        and market['base'] not in fiat_descartadas 
        and market['quote'] not in fiat_descartadas
    }

    # Contar frecuencia de pares disponibles
    conteo_monedas = {}
    for market in mercados_spot.values():
        base, quote = market['base'], market['quote']
        conteo_monedas[base] = conteo_monedas.get(base, 0) + 1
        conteo_monedas[quote] = conteo_monedas.get(quote, 0) + 1

    monedas_ordenadas = sorted(conteo_monedas.keys(), key=lambda x: conteo_monedas[x], reverse=True)
    
    return mercados_spot, monedas_ordenadas

def construir_rutas(mercados_spot, monedas_seleccionadas):
    monedas_principales = {"USDT", "BTC", "ETH", "BNB", "FDUSD"}
    monedas_validas = set(monedas_seleccionadas)

    rutas = []
    pares_existentes = {}
    for symbol, market in mercados_spot.items():
        base, quote = market['base'], market['quote']
        if base in monedas_validas and quote in monedas_validas:
            pares_existentes[(base, quote)] = {"symbol": symbol, "action": "sell"}
            pares_existentes[(quote, base)] = {"symbol": symbol, "action": "buy"}

    monedas_lista = list(monedas_validas)
    for a in monedas_principales.intersection(monedas_validas):
        for b in monedas_lista:
            if a == b: continue
            if (a, b) not in pares_existentes: continue
            
            for c in monedas_lista:
                if c == a or c == b: continue
                if (b, c) in pares_existentes and (c, a) in pares_existentes:
                    rutas.append({
                        "nodos": (a, b, c, a),
                        "pasos": [
                            pares_existentes[(a, b)],
                            pares_existentes[(b, c)],
                            pares_existentes[(c, a)]
                        ]
                    })

    return rutas

def calcular_arbitraje(tickers, ruta_info, capital, comision, vol_minimo=10000.0):
    monto = capital
    for paso in ruta_info["pasos"]:
        symbol = paso["symbol"]
        action = paso["action"]
        ticker = tickers.get(symbol)
        
        if not ticker or not ticker.get("ask") or not ticker.get("bid"):
            return None

        # FILTRO 1: Volumen en 24h mínimo
        volumen_24h = ticker.get("quoteVolume", 0) or 0
        if volumen_24h < vol_minimo:
            return None

        ask = ticker["ask"]
        bid = ticker["bid"]

        if ask <= 0 or bid <= 0: 
            return None

        # FILTRO 2: Spread razonable (<1%)
        spread = (ask - bid) / ask
        if spread > 0.01:
            return None

        if action == "buy":
            monto = (monto / ask) * (1 - comision)
        else:
            monto = (monto * bid) * (1 - comision)

    beneficio_pct = (monto - capital) / capital
    return monto, beneficio_pct


# =========================================================
# PANEL LATERAL (CONFIGURACIÓN)
# =========================================================
st.sidebar.header("💰 Gestión de Capital")

# --- AJUSTE MANUAL DE BALANCE ---
nuevo_balance = st.sidebar.number_input(
    "Balance Inicial Simulación (USDT):", 
    min_value=10.0, 
    value=float(st.session_state.balance_inicial), 
    step=100.0
)

if nuevo_balance != st.session_state.balance_inicial:
    st.session_state.balance_inicial = nuevo_balance
    st.session_state.balance_usdt = nuevo_balance
    st.session_state.historial_balance = [{"Hora": datetime.now().strftime("%H:%M:%S"), "USDT": nuevo_balance}]

st.sidebar.divider()
st.sidebar.header("⚙️ Cobertura y Monedas")

exchange = conectar_exchange()
mercados_spot, monedas_ordenadas = obtener_mercados_base(exchange)

modo_alcance = st.sidebar.selectbox(
    "Preajuste de Monedas:",
    ["Top 15 Monedas", "Top 50 Monedas", "Todas las Monedas Disponibles", "Personalizado"],
    index=1
)

if modo_alcance == "Top 15 Monedas":
    monedas_default = monedas_ordenadas[:15]
elif modo_alcance == "Top 50 Monedas":
    monedas_default = monedas_ordenadas[:50]
elif modo_alcance == "Todas las Monedas Disponibles":
    monedas_default = monedas_ordenadas
else:
    monedas_default = monedas_ordenadas[:15]

monedas_seleccionadas = st.sidebar.multiselect(
    "Monedas activas en el escáner:",
    options=monedas_ordenadas,
    default=monedas_default
)

rutas_validas = construir_rutas(mercados_spot, monedas_seleccionadas)

st.sidebar.divider()

monto_operacion = st.sidebar.number_input("Monto por simulación (USDT):", min_value=10.0, value=100.0, step=10.0)
umbral_beneficio = st.sidebar.slider("Ganancia mínima requerida (%):", min_value=0.0, max_value=3.0, value=0.1, step=0.01) / 100

# --- COMISIÓN PASO A PASO DE 0.001% ---
comision_pct = st.sidebar.number_input(
    "Comisión por orden (%):", 
    min_value=0.0, 
    max_value=1.0, 
    value=0.100, 
    step=0.001, 
    format="%.3f"
) / 100

intervalo_refresco = st.sidebar.slider("Intervalo entre lecturas (seg):", min_value=1, max_value=10, value=2)

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    if st.button("▶️ Iniciar", use_container_width=True):
        st.session_state.running = True
with col_btn2:
    if st.button("⏸️ Detener", use_container_width=True):
        st.session_state.running = False

if st.sidebar.button("🔄 Reiniciar Balance y Historial", use_container_width=True):
    st.session_state.balance_usdt = st.session_state.balance_inicial
    st.session_state.historial_trades = []
    st.session_state.historial_balance = [{"Hora": datetime.now().strftime("%H:%M:%S"), "USDT": st.session_state.balance_inicial}]
    st.rerun()

# =========================================================
# CUERPO PRINCIPAL DEL DASHBOARD
# =========================================================
col1, col2, col3, col4 = st.columns(4)

pnl_abs = st.session_state.balance_usdt - st.session_state.balance_inicial
pnl_pct = (pnl_abs / st.session_state.balance_inicial) * 100 if st.session_state.balance_inicial > 0 else 0

col1.metric("Balance Virtual", f"{st.session_state.balance_usdt:.2f} USDT")
col2.metric("PnL Simulado", f"{pnl_abs:+.2f} USDT", delta=f"{pnl_pct:+.2f}%")
col3.metric("Monedas Seleccionadas", len(monedas_seleccionadas))
col4.metric("Rutas Triangulares", len(rutas_validas))

st.divider()

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("📈 Crecimiento del Portafolio")
    df_balance = pd.DataFrame(st.session_state.historial_balance)
    fig = px.line(df_balance, x="Hora", y="USDT", markers=True)
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("🎯 Oportunidades Detectadas")
    container_oportunidades = st.empty()

st.subheader("📜 Registro de Trades Ejecutados")
container_historial = st.empty()


# =========================================================
# BUCLE EN TIEMPO REAL
# =========================================================
if st.session_state.running:
    if not rutas_validas:
        st.error("No hay rutas disponibles con las monedas seleccionadas. Selecciona más monedas en la barra lateral.")
    else:
        try:
            tickers = exchange.fetch_tickers()
        except Exception as e:
            st.warning(f"Reintentando conexión con Binance... ({e})")
            tickers = {}

        oportunidades = []

        if tickers:
            for ruta_info in rutas_validas:
                res = calcular_arbitraje(tickers, ruta_info, monto_operacion, comision_pct)
                if res:
                    monto_final, beneficio_pct = res
                    if beneficio_pct >= umbral_beneficio:
                        ruta_str = " ➔ ".join(ruta_info["nodos"])
                        oportunidades.append({
                            "Ruta": ruta_str,
                            "Beneficio (%)": round(beneficio_pct * 100, 3),
                            "Ganancia (USDT)": round(monto_final - monto_operacion, 3),
                            "Retorno Total": round(monto_final, 2),
                            "raw_data": (ruta_str, beneficio_pct, monto_final)
                        })

        if oportunidades:
            df_ops = pd.DataFrame(oportunidades).sort_values(by="Beneficio (%)", ascending=False)
            container_oportunidades.dataframe(
                df_ops[["Ruta", "Beneficio (%)", "Ganancia (USDT)"]], 
                hide_index=True, 
                use_container_width=True
            )

            top_op = df_ops.iloc[0]["raw_data"]
            ruta_top, ben_top, final_top = top_op

            if st.session_state.balance_usdt >= monto_operacion:
                ganancia = final_top - monto_operacion
                st.session_state.balance_usdt += ganancia
                
                st.session_state.historial_trades.append({
                    "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Ruta Triangular": ruta_top,
                    "Rendimiento": f"{ben_top*100:+.3f}%",
                    "Ganancia Neta (USDT)": round(ganancia, 4),
                    "Nuevo Balance": round(st.session_state.balance_usdt, 2)
                })

                st.session_state.historial_balance.append({
                    "Hora": datetime.now().strftime("%H:%M:%S"),
                    "USDT": round(st.session_state.balance_usdt, 2)
                })
        else:
            container_oportunidades.info(f"Escaneando {len(rutas_validas)} rutas en tiempo real... Sin diferencias de precio aprovechables en este ciclo.")

        if st.session_state.historial_trades:
            df_hist = pd.DataFrame(st.session_state.historial_trades).iloc[::-1]
            container_historial.dataframe(df_hist, hide_index=True, use_container_width=True)
        else:
            container_historial.write("Esperando primer trade simulado...")

        time.sleep(intervalo_refresco)
        st.rerun()
else:
    st.info("💡 Haz clic en '▶️ Iniciar' en el menú de la izquierda para comenzar el escaneo.")
    if st.session_state.historial_trades:
        df_hist = pd.DataFrame(st.session_state.historial_trades).iloc[::-1]
        container_historial.dataframe(df_hist, hide_index=True, use_container_width=True)