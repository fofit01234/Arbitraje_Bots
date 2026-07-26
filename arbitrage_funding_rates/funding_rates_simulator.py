"""
Escáner de Funding Rate + Simulador de Rendimiento Mensual y Compuesto
====================================================================
Ejecutar con: streamlit run app.py
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

st.title("🛡️ Funding Rate Scanner & Simulador Mensual")
st.caption("Estrategia Delta-Neutral con evaluación de riesgos y proyección de capital a largo plazo.")

# =========================================================
# CONEXIÓN Y DATOS
# =========================================================
@st.cache_resource
def conectar_exchange():
    return ccxt.binanceusdm({"enableRateLimit": True})

@st.cache_data(ttl=60)
def obtener_datos_mercado(_exchange):
    try:
        tickers = _exchange.fetch_tickers()
        funding_rates = _exchange.fetch_funding_rates()
        return tickers, funding_rates
    except Exception as e:
        st.error(f"Error al conectar con Binance: {e}")
        return {}, {}

# =========================================================
# PANEL LATERAL: CONFIGURACIÓN
# =========================================================
st.sidebar.header("💰 Configuración de Capital")
capital_total = st.sidebar.number_input("Capital Inicial (USDT):", min_value=20.0, value=1000.0, step=100.0)

st.sidebar.divider()
st.sidebar.header("🛡️ Filtros de Riesgo")

volumen_minimo = st.sidebar.number_input(
    "Volumen Mínimo 24h (USDT):", 
    min_value=100000.0, 
    value=10000000.0, 
    step=1000000.0
)

# Comisiones ajustadas con BNB (Taker)
comision_spot_pct = st.sidebar.number_input("Comisión Spot (%):", value=0.075, step=0.005) / 100
comision_fut_pct = st.sidebar.number_input("Comisión Futuros (%):", value=0.045, step=0.005) / 100

dias_max_recuperacion = st.sidebar.slider(
    "Días máx. recup. comisiones:", 
    min_value=1, 
    max_value=10, 
    value=3
)

tasa_minima_8h = st.sidebar.number_input(
    "Tasa Mínima 8h (%):", 
    min_value=0.001, 
    value=0.010, 
    step=0.005,
    format="%.3f"
) / 100

if st.sidebar.button("🔄 Actualizar Escáner", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# =========================================================
# PROCESAMIENTO Y FILTRADO DE DATOS
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

            # Rendimientos netos
            ganancia_neta_mes_est = (ganancia_diaria_usdt * 30) - costo_comisiones_usdt
            rendimiento_mensual_neto_pct = (ganancia_neta_mes_est / capital_total) * 100
            apy_neto_pct = rendimiento_mensual_neto_pct * 12
            
            monto_por_lado = capital_total / 2
            cantidad_cripto = monto_por_lado / precio_actual
            moneda = symbol.split(":")[0].replace("/USDT", "")

            oportunidades_seguras.append({
                "Moneda": moneda,
                "Precio USDT": precio_actual,
                "Tasa 8h (%)": round(pago_8h_pct, 4),
                "Rend. Diario (%)": round(pago_diario_pct, 3),
                "Rend. Mensual Neto (%)": round(rendimiento_mensual_neto_pct, 2),
                "Días p/ Pagar Fee": round(dias_para_recuperar_comisiones, 1),
                "Ganancia Neta Mes 1 ($)": round(ganancia_neta_mes_est, 2),
                "APY Neto (%)": round(apy_neto_pct, 2),
                "Cantidad Cripto Exec": round(cantidad_cripto, 4),
                "raw_rate": rate
            })

# =========================================================
# VISTAS EN PESTAÑAS (TABS)
# =========================================================
tab_escanner, tab_simulador = st.tabs(["📊 Oportunidades Actuales", "📈 Simulador de Crecimiento Mensual"])

if oportunidades_seguras:
    df = pd.DataFrame(oportunidades_seguras).sort_values(by="raw_rate", ascending=False)
    top = df.iloc[0]

    # --- PESTAÑA 1: ESCÁNER ---
    with tab_escanner:
        st.success(f"✅ **{len(df)} oportunidades** disponibles cumpliendo los filtros de seguridad.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Opción Más Segura", top["Moneda"])
        col2.metric("Rendimiento Mensual Neto", f"{top['Rend. Mensual Neto (%)']}%")
        col3.metric("Recuperación de Fees", f"{top['Días p/ Pagar Fee']} días")
        col4.metric("Ganancia Neta Mes 1", f"+${top['Ganancia Neta Mes 1 ($)']} USDT")

        st.divider()

        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("📊 APY Neto por Moneda (Post-Comisiones)")
            fig = px.bar(
                df.head(10),
                x="Moneda",
                y="APY Neto (%)",
                color="Días p/ Pagar Fee",
                color_continuous_scale="RdYlGn_r",
                text="APY Neto (%)"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.subheader("🎯 Guía de Ejecución Rápida")
            st.markdown(f"""
            Para **{top['Moneda']}**:
            * **Spot:** Comprar **{top['Cantidad Cripto Exec']} {top['Moneda']}** (aprox. ${capital_total/2:.2f} USDT).
            * **Futuros (1x):** Vender Corto (Short) **{top['Cantidad Cripto Exec']} {top['Moneda']}**.
            
            ⚠️ **Comisiones netas estimadas:** **${costo_comisiones_usdt:.2f} USDT** (Se recuperan en **{top['Días p/ Pagar Fee']}** días).
            """)

        st.subheader("📜 Listado Completo")
        st.dataframe(
            df[["Moneda", "Precio USDT", "Tasa 8h (%)", "Rend. Mensual Neto (%)", "Días p/ Pagar Fee", "Ganancia Neta Mes 1 ($)", "APY Neto (%)"]],
            hide_index=True,
            use_container_width=True
        )

    # --- PESTAÑA 2: SIMULADOR DE CRECIMIENTO ---
    with tab_simulador:
        st.subheader("🚀 Proyección de Crecimiento A Largo Plazo")
        st.caption("Simula cuánto acumularías repitiendo la estrategia todos los meses.")

        col_sim1, col_sim2 = st.columns([1, 2])

        with col_sim1:
            meses_simulacion = st.slider("Horizonte de Tiempo (Meses):", min_value=1, max_value=24, value=12)
            
            # Opción para seleccionar la tasa a simular (por defecto toma la mejor actual)
            tasa_mensual_base = st.number_input(
                "Rendimiento Neto Mensual Estimado (%):",
                value=float(top["Rend. Mensual Neto (%)"]),
                step=0.5,
                help="Puedes usar la mejor tasa encontrada actualmente o ajustar una tasa promedio personalizada."
            ) / 100

            reaporte_mensual = st.number_input(
                "Aporte Adicional Mensual de tu Bolsillo (USDT):",
                min_value=0.0,
                value=0.0,
                step=50.0,
                help="¿Planeas meterle más dinero propio cada mes?"
            )

        # Lógica de cálculo mes a mes
        datos_meses = []
        cap_simple = capital_total
        cap_compuesto = capital_total
        total_invertido_propio = capital_total

        for mes in range(0, meses_simulacion + 1):
            if mes == 0:
                datos_meses.append({
                    "Mes": 0,
                    "Capital Invertido": total_invertido_propio,
                    "Interés Simple": cap_simple,
                    "Interés Compuesto": cap_compuesto,
                    "Ganancia Neta Compuesta": 0.0
                })
            else:
                # Interés Simple
                ganancia_simple = (capital_total * tasa_mensual_base)
                cap_simple += ganancia_simple + reaporte_mensual

                # Interés Compuesto (La ganancia del mes anterior se reinvierte)
                ganancia_compuesta = (cap_compuesto * tasa_mensual_base)
                cap_compuesto += ganancia_compuesta + reaporte_mensual

                total_invertido_propio += reaporte_mensual

                datos_meses.append({
                    "Mes": mes,
                    "Capital Invertido": round(total_invertido_propio, 2),
                    "Interés Simple": round(cap_simple, 2),
                    "Interés Compuesto": round(cap_compuesto, 2),
                    "Ganancia Neta Compuesta": round(cap_compuesto - total_invertido_propio, 2)
                })

        df_sim = pd.DataFrame(datos_meses)
        resultado_final = df_sim.iloc[-1]

        with col_sim2:
            st.markdown("#### 📌 Resumen de la Simulación")
            m1, m2, m3 = st.columns(3)
            m1.metric("Capital Inicial + Aportes", f"${resultado_final['Capital Invertido']:.2f} USDT")
            m2.metric("Total Final (Interés Compuesto)", f"${resultado_final['Interés Compuesto']:.2f} USDT")
            m3.metric("Ganancia Limpia Total", f"+${resultado_final['Ganancia Neta Compuesta']:.2f} USDT", delta=f"{((resultado_final['Ganancia Neta Compuesta']/resultado_final['Capital Invertido'])*100):.1f}%")

            st.divider()

            # Gráfico de curvas de crecimiento
            fig_sim = go.Figure()

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Mes"], y=df_sim["Capital Invertido"],
                mode='lines+markers', name='Capital Propio Invertido',
                line=dict(color='gray', dash='dash')
            ))

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Mes"], y=df_sim["Interés Simple"],
                mode='lines+markers', name='Crecimiento Simple (Sin Reinvertir)',
                line=dict(color='#FFA500')
            ))

            fig_sim.add_trace(go.Scatter(
                x=df_sim["Mes"], y=df_sim["Interés Compuesto"],
                mode='lines+markers', name='Crecimiento Compuesto (Reinvirtiendo)',
                line=dict(color='#00FF7F', width=3)
            ))

            fig_sim.update_layout(
                title="Evolución de Saldo en el Tiempo (USDT)",
                xaxis_title="Meses",
                yaxis_title="USDT",
                height=400,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )

            st.plotly_chart(fig_sim, use_container_width=True)

        st.markdown("#### 📜 Tabla de Crecimiento Mes a Mes")
        st.dataframe(df_sim, hide_index=True, use_container_width=True)

else:
    st.warning("⚠️ No se encontraron oportunidades que pasen los filtros estrictos de seguridad actualmente.")