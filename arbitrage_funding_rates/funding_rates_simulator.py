"""
Funding Rate Scanner + Monthly & Compound Yield Simulator
=========================================================
Run with: streamlit run app.py
"""

import ccxt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Funding Arbitrage - Simulator Edition",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Funding Rate Scanner & Monthly Simulator")
st.caption("Delta-Neutral strategy with risk assessment and long-term capital projection.")

# =========================================================
# CONNECTION AND DATA
# =========================================================
@st.cache_resource
def conectar_exchange():
   """
    Conecta a Binance usando un Proxy CORS público para evitar 
    el bloqueo de IP y el geobloqueo en la nube gratis.
    """
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
        # Redirige la petición a través de un proxy europeo público
        "proxy": "https://corsproxy.io/?"
    })
@st.cache_data(ttl=60)
def obtener_datos_mercado(_exchange):
    try:
        tickers = _exchange.fetch_tickers()
        funding_rates = _exchange.fetch_funding_rates()
        return tickers, funding_rates
    except Exception as e:
        st.error(f"Error connecting to Binance: {e}")
        return {}, {}

# =========================================================
# SIDEBAR: CONFIGURATION
# =========================================================
st.sidebar.header("💰 Capital Settings")
capital_total = st.sidebar.number_input("Initial Capital (USDT):", min_value=20.0, value=1000.0, step=100.0)

st.sidebar.divider()
st.sidebar.header("🛡️ Risk Filters")

volumen_minimo = st.sidebar.number_input(
    "Minimum 24h Volume (USDT):", 
    min_value=100000.0, 
    value=10000000.0, 
    step=1000000.0
)

# Fee settings with BNB discount (Taker)
comision_spot_pct = st.sidebar.number_input("Spot Fee (%):", value=0.075, step=0.005) / 100
comision_fut_pct = st.sidebar.number_input("Futures Fee (%):", value=0.045, step=0.005) / 100

dias_max_recuperacion = st.sidebar.slider(
    "Max Days to Recover Fees:", 
    min_value=1, 
    max_value=10, 
    value=3
)

tasa_minima_8h = st.sidebar.number_input(
    "Minimum 8h Rate (%):", 
    min_value=0.001, 
    value=0.010, 
    step=0.005,
    format="%.3f"
) / 100

if st.sidebar.button("🔄 Refresh Scanner", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# =========================================================
# DATA PROCESSING AND FILTERING
# =========================================================
exchange = conectar_exchange()
tickers, funding_rates = obtener_datos_mercado(exchange)

costo_comisiones_pct = 2 * (comision_spot_pct + comision_fut_pct)
costo_comisiones_usdt = capital_total * costo_comisiones_pct

oportunidades_seguras = []

if funding_rates and tickers:
    for symbol, fr_data in funding_rates.items():
        if not symbol.endswith("/USDT:USDT") and not symbol.endswith("/USDT"):
            continue

        rate = fr_data.get("fundingRate")
        ticker = tickers.get(symbol)

        if rate is not None and ticker:
            volumen_24h = ticker.get("quoteVolume", 0) or 0
            precio_actual = ticker.get("last", 0) or 0

            if volumen_24h < volumen_minimo or precio_actual <= 0:
                continue

            if rate < tasa_minima_8h:
                continue

            pago_8h_pct = rate * 100
            pago_diario_pct = pago_8h_pct * 3
            ganancia_diaria_usdt = capital_total * (pago_diario_pct / 100)

            if ganancia_diaria_usdt > 0:
                dias_para_recuperar_comisiones = costo_comisiones_usdt / ganancia_diaria_usdt
            else:
                dias_para_recuperar_comisiones = 999

            if dias_para_recuperar_comisiones > dias_max_recuperacion:
                continue

            # Net Yields
            ganancia_neta_mes_est = (ganancia_diaria_usdt * 30) - costo_comisiones_usdt
            rendimiento_mensual_neto_pct = (ganancia_neta_mes_est / capital_total) * 100
            apy_neto_pct = rendimiento_mensual_neto_pct * 12
            
            monto_por_lado = capital_total / 2
            cantidad_cripto = monto_por_lado / precio_actual
            moneda = symbol.split(":")[0].replace("/USDT", "")

            oportunidades_seguras.append({
                "Coin": moneda,
                "Price USDT": precio_actual,
                "8h Rate (%)": round(pago_8h_pct, 4),
                "Daily Yield (%)": round(pago_diario_pct, 3),
                "Net Monthly Yield (%)": round(rendimiento_mensual_neto_pct, 2),
                "Days to Pay Fees": round(dias_para_recuperar_comisiones, 1),
                "Net Profit Month 1 ($)": round(ganancia_neta_mes_est, 2),
                "Net APY (%)": round(apy_neto_pct, 2),
                "Executed Crypto Qty": round(cantidad_cripto, 4),
                "raw_rate": rate
            })

# =========================================================
# TAB VIEWS
# =========================================================
tab_escanner, tab_simulador = st.tabs(["📊 Current Opportunities", "📈 Monthly Growth Simulator"])

if oportunidades_seguras:
    df = pd.DataFrame(oportunidades_seguras).sort_values(by="raw_rate", ascending=False)
    top = df.iloc[0]

    # --- TAB 1: SCANNER ---
    with tab_escanner:
        st.success(f"✅ **{len(df)} opportunities** available matching safety filters.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Safest Option", top["Coin"])
        col2.metric("Net Monthly Yield", f"{top['Net Monthly Yield (%)']}%")
        col3.metric("Fee Recovery Time", f"{top['Days to Pay Fees']} days")
        col4.metric("Net Profit Month 1", f"+${top['Net Profit Month 1 ($)']} USDT")

        st.divider()

        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("📊 Net APY by Coin (Post-Fees)")
            fig = px.bar(
                df.head(10),
                x="Coin",
                y="Net APY (%)",
                color="Days to Pay Fees",
                color_continuous_scale="RdYlGn_r",
                text="Net APY (%)"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.subheader("🎯 Quick Execution Guide")
            st.markdown(f"""
            For **{top['Coin']}**:
            * **Spot:** Buy **{top['Executed Crypto Qty']} {top['Coin']}** (approx. ${capital_total/2:.2f} USDT).
            * **Futures (1x):** Short **{top['Executed Crypto Qty']} {top['Coin']}**.
            
            ⚠️ **Estimated Net Fees:** **${costo_comisiones_usdt:.2f} USDT** (Recovered in **{top['Days to Pay Fees']}** days).
            """)

        st.subheader("📜 Complete List")
        st.dataframe(
            df[["Coin", "Price USDT", "8h Rate (%)", "Net Monthly Yield (%)", "Days to Pay Fees", "Net Profit Month 1 ($)", "Net APY (%)"]],
            hide_index=True,
            use_container_width=True
        )

    # --- TAB 2: GROWTH SIMULATOR ---
    with tab_simulador:
        st.subheader("🚀 Long-Term Growth Projection")
        st.caption("Simulate how much capital you would accumulate by repeating this strategy every month.")

        col_sim1, col_sim2 = st.columns([1, 2])

        with col_sim1:
            meses_simulacion = st.slider("Time Horizon (Months):", min_value=1, max_value=24, value=12)
            
            # Select rate to simulate (defaults to current best rate)
            tasa_mensual_base = st.number_input(
                "Estimated Net Monthly Yield (%):",
                value=float(top["Net Monthly Yield (%)"]),
                step=0.5,
                help="You can use the best rate currently found or adjust to a custom average rate."
            ) / 100

            reaporte_mensual = st.number_input(
                "Additional Monthly Contribution (USDT):",
                min_value=0.0,
                value=0.0,
                step=50.0,
                help="Do you plan to add more out-of-pocket capital every month?"
            )

        # Month-by-month calculation logic
        datos_meses = []
        cap_simple = capital_total
        cap_compuesto = capital_total
        total_invertido_propio = capital_total

        for mes in range(0, meses_simulacion + 1):
            if mes == 0:
                datos_meses.append({
                    "Month": 0,
                    "Invested Capital": total_invertido_propio,
                    "Simple Interest": cap_simple,
                    "Compound Interest": cap_compuesto,
                    "Net Compound Profit": 0.0
                })
            else:
                # Simple Interest
                ganancia_simple = (capital_total * tasa_mensual_base)
                cap_simple += ganancia_simple + reaporte_mensual

                # Compound Interest (Previous month gains reinvested)
                ganancia_compuesta = (cap_compuesto * tasa_mensual_base)
                cap_compuesto += ganancia_compuesta + reaporte_mensual

                total_invertido_propio += reaporte_mensual

                datos_meses.append({
                    "Month": mes,
                    "Invested Capital": round(total_invertido_propio, 2),
                    "Simple Interest": round(cap_simple, 2),
                    "Compound Interest": round(cap_compuesto, 2),
                    "Net Compound Profit": round(cap_compuesto - total_invertido_propio, 2)
                })

        df_sim = pd.DataFrame(datos_meses)
        resultado_final = df_sim.iloc[-1]

        with col_sim2:
            st.markdown("#### 📌 Simulation Summary")
            m1, m2, m3 = st.columns(3)
            m1.metric("Initial Capital + Deposits", f"${resultado_final['Invested Capital']:.2f} USDT")
            m2.metric("Final Total (Compound Interest)", f"${resultado_final['Compound Interest']:.2f} USDT")
            m3.metric("Total Net Profit", f"+${resultado_final['Net Compound Profit']:.2f} USDT", delta=f"{((resultado_final['Net Compound Profit']/resultado_final['Invested Capital'])*100):.1f}%")

            st.divider()

            # Growth Curves Chart
            fig_sim = go.Figure()

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Month"], y=df_sim["Invested Capital"],
                mode='lines+markers', name='Invested Own Capital',
                line=dict(color='gray', dash='dash')
            ))

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Month"], y=df_sim["Simple Interest"],
                mode='lines+markers', name='Simple Growth (No Reinvesting)',
                line=dict(color='#FFA500')
            ))

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Month"], y=df_sim["Compound Interest"],
                mode='lines+markers', name='Compound Growth (Reinvesting)',
                line=dict(color='#00FF7F', width=3)
            ))

            fig_sim.update_layout(
                title="Balance Evolution Over Time (USDT)",
                xaxis_title="Months",
                yaxis_title="USDT",
                height=400,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )

            st.plotly_chart(fig_sim, use_container_width=True)

        st.markdown("#### 📜 Month-by-Month Growth Table")
        st.dataframe(df_sim, hide_index=True, use_container_width=True)

else:
    st.warning("⚠️ No opportunities currently matching the strict safety filters were found.")