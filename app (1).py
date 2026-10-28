import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# set_page_config debe ser el PRIMER comando de Streamlit
st.set_page_config(layout="wide", page_title="Laboratorio Optimalidad y Sink Tree")

st.title("Laboratorio de redes: optimalidad y Sink Tree")
st.caption("Basado en Johal (2008) | Python + NetworkX + Streamlit + Plotly | Origen H, destino B")

# ---------------------------------------------------------------------------
# Datos iniciales (los de la guía; las capacidades de H–O, O–N y N–J se asumieron)
# ---------------------------------------------------------------------------
ENLACES_INICIALES = [
    ("H", "D", 8.0, 100.0),
    ("D", "A", 9.0, 100.0),
    ("A", "B", 7.0, 100.0),
    ("H", "E", 5.0, 50.0),
    ("E", "J", 10.0, 50.0),
    ("J", "C", 8.0, 100.0),
    ("C", "B", 6.0, 100.0),
    ("H", "O", 7.0, 50.0),
    ("O", "N", 9.0, 50.0),
    ("N", "J", 9.0, 50.0),
]

RUTAS_ESTATICAS = {
    "PSRC": ["H", "D", "A", "B"],
    "SSRC": ["H", "E", "J", "C", "B"],
    "TSRC": ["H", "O", "N", "J", "C", "B"],
}

POS = {
    "H": (0.0, 0.5), "D": (1.0, 2.0), "A": (2.0, 2.0), "B": (3.0, 1.5),
    "E": (1.0, 0.5), "J": (2.0, 0.5), "C": (2.5, 1.0),
    "O": (0.5, -1.0), "N": (1.5, -1.0),
}

ORIGEN, DESTINO = "H", "B"
FUNCIONES = ["Johal: mínimo de saltos", "Mínimo retardo", "Multicriterio"]


def tabla_inicial():
    return pd.DataFrame(
        [
            {"Origen": o, "Destino": d, "Retardo_ms": r, "Banda_Mbps": b, "Disponible": True}
            for o, d, r, b in ENLACES_INICIALES
        ]
    )


def restablecer():
    """Borra todo el estado de los widgets (tabla, función y pesos)."""
    for k in ("editor_enlaces", "funcion", "w_alpha", "w_beta", "w_gamma"):
        st.session_state.pop(k, None)


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
st.sidebar.header("Parámetros")
st.sidebar.button("Restablecer todo", on_click=restablecer)

funcion_opt = st.sidebar.radio("Función objetivo", FUNCIONES, key="funcion")

st.sidebar.subheader("Pesos del modelo multicriterio")
w_alpha = st.sidebar.slider("α (saltos)", 0.0, 1.0, 0.50, 0.05, key="w_alpha")
w_beta = st.sidebar.slider("β (retardo)", 0.0, 1.0, 0.35, 0.05, key="w_beta")
w_gamma = st.sidebar.slider("γ (baja capacidad)", 0.0, 1.0, 0.15, 0.05, key="w_gamma")

suma_w = w_alpha + w_beta + w_gamma
if suma_w > 0:
    alpha, beta, gamma = w_alpha / suma_w, w_beta / suma_w, w_gamma / suma_w
else:
    alpha, beta, gamma = 1 / 3, 1 / 3, 1 / 3

st.sidebar.caption(f"Normalizados: α={alpha:.4f} · β={beta:.4f} · γ={gamma:.4f}")
if funcion_opt != "Multicriterio":
    st.sidebar.caption("Los pesos solo se usan en «Multicriterio».")

# ---------------------------------------------------------------------------
# 1. Tabla de enlaces
# ---------------------------------------------------------------------------
st.header("1. Tabla de enlaces")
st.caption("Edita Retardo_ms, Banda_Mbps y Disponible. Los cambios se recalculan al instante.")

df = st.data_editor(
    tabla_inicial(),
    key="editor_enlaces",
    hide_index=True,
    num_rows="fixed",
    disabled=["Origen", "Destino"],
    column_config={
        "Retardo_ms": st.column_config.NumberColumn("Retardo_ms", min_value=0.0),
        "Banda_Mbps": st.column_config.NumberColumn("Banda_Mbps", min_value=0.1),
        "Disponible": st.column_config.CheckboxColumn("Disponible"),
    },
)

if df[["Retardo_ms", "Banda_Mbps"]].isna().any().any():
    st.error("Hay celdas vacías en Retardo_ms o Banda_Mbps. Complétalas para continuar.")
    st.stop()

df = df.copy()
df["Disponible"] = df["Disponible"].fillna(False).astype(bool)

# d_ref y b_ref: máximos positivos de la tabla actual
ret_pos = df.loc[df["Retardo_ms"] > 0, "Retardo_ms"]
ban_pos = df.loc[df["Banda_Mbps"] > 0, "Banda_Mbps"]
d_ref = float(ret_pos.max()) if len(ret_pos) else 1.0
b_ref = float(ban_pos.max()) if len(ban_pos) else 1.0
st.caption(f"d_ref = {d_ref:g} ms · b_ref = {b_ref:g} Mbps (máximos positivos de la tabla actual)")


def costo_enlace(retardo, banda):
    """C_ij = α + β·(d_ij/d_ref) + γ·(b_ref/b_ij)"""
    return alpha + beta * (retardo / d_ref) + gamma * (b_ref / banda)


# ---------------------------------------------------------------------------
# Grafo (solo enlaces disponibles)
# ---------------------------------------------------------------------------
G = nx.Graph()
for nodo in sorted(set(df["Origen"]).union(df["Destino"])):
    G.add_node(nodo)

for _, fila in df[df["Disponible"]].iterrows():
    u, v = fila["Origen"], fila["Destino"]
    d, b = float(fila["Retardo_ms"]), float(fila["Banda_Mbps"])
    if b <= 0:
        continue
    if funcion_opt == FUNCIONES[0]:
        peso = 1.0
    elif funcion_opt == FUNCIONES[1]:
        peso = d
    else:
        peso = costo_enlace(d, b)
    G.add_edge(u, v, retardo=d, banda=b, peso=peso)


def metricas_ruta(ruta):
    """Métricas de una ruta o None si algún enlace no está disponible."""
    saltos, retardo, costo, bandas = 0, 0.0, 0.0, []
    for u, v in zip(ruta[:-1], ruta[1:]):
        if not G.has_edge(u, v):
            return None
        e = G[u][v]
        saltos += 1
        retardo += e["retardo"]
        bandas.append(e["banda"])
        costo += costo_enlace(e["retardo"], e["banda"])
    return {"saltos": saltos, "retardo": retardo, "banda": min(bandas), "costo": costo}


def valor_objetivo(m):
    if funcion_opt == FUNCIONES[0]:
        return float(m["saltos"])
    if funcion_opt == FUNCIONES[1]:
        return m["retardo"]
    return m["costo"]


# ---------------------------------------------------------------------------
# 2. Ruta óptima recalculada vs. ruta estática
# ---------------------------------------------------------------------------
st.header("2. Ruta óptima recalculada vs. ruta estática")

if funcion_opt == FUNCIONES[0]:
    st.latex(r"\min H(P)=\sum_{(i,j)\in P} h_{ij}, \qquad h_{ij}=1")
elif funcion_opt == FUNCIONES[1]:
    st.latex(r"\min D(P)=\sum_{(i,j)\in P} d_{ij}")
else:
    st.latex(
        r"\min C(P)=\sum_{(i,j)\in P}\left[\alpha+\beta\frac{d_{ij}}{d_{ref}}"
        r"+\gamma\frac{b_{ref}}{b_{ij}}\right],\quad \alpha+\beta+\gamma=1"
    )
st.latex(r"B(P)=\min_{(i,j)\in P} b_{ij}\quad(\text{cuello de botella; no es la penalización } b_{ref}/b_{ij})")

camino_optimo = []
existe_ruta = G.has_node(ORIGEN) and G.has_node(DESTINO) and nx.has_path(G, ORIGEN, DESTINO)
if existe_ruta:
    camino_optimo = nx.shortest_path(G, ORIGEN, DESTINO, weight="peso")

ruta_estatica_sel = None
filas = []
for nombre, ruta in RUTAS_ESTATICAS.items():
    m = metricas_ruta(ruta)
    if m is not None and ruta_estatica_sel is None:
        ruta_estatica_sel = nombre
    filas.append(
        {
            "Ruta": nombre,
            "Camino": "–".join(ruta),
            "Disponible": "Sí" if m else "No",
            "H(P) saltos": str(m["saltos"]) if m else "—",
            "D(P) ms": f"{m['retardo']:g}" if m else "—",
            "B(P) Mbps": f"{m['banda']:g}" if m else "—",
            "C(P)": f"{m['costo']:.3f}" if m else "—",
            "Nota": "",
        }
    )

if existe_ruta:
    m_opt = metricas_ruta(camino_optimo)
    filas.append(
        {
            "Ruta": "ÓPTIMA",
            "Camino": "–".join(camino_optimo),
            "Disponible": "Sí",
            "H(P) saltos": str(m_opt["saltos"]),
            "D(P) ms": f"{m_opt['retardo']:g}",
            "B(P) Mbps": f"{m_opt['banda']:g}",
            "C(P)": f"{m_opt['costo']:.3f}",
            "Nota": f"recalculada con «{funcion_opt}»",
        }
    )

for f in filas:
    if f["Ruta"] == ruta_estatica_sel:
        f["Nota"] = "◄ estática seleccionada"

st.dataframe(pd.DataFrame(filas), hide_index=True)

col_a, col_b = st.columns(2)
with col_a:
    if ruta_estatica_sel:
        m_est = metricas_ruta(RUTAS_ESTATICAS[ruta_estatica_sel])
        st.info(
            f"**Estática seleccionada ({ruta_estatica_sel}):** "
            f"{'–'.join(RUTAS_ESTATICAS[ruta_estatica_sel])}\n\n"
            f"Valor de la función objetivo: {valor_objetivo(m_est):.4f}"
        )
    else:
        st.warning("Ninguna de las tres rutas preconfiguradas está disponible.")
with col_b:
    if existe_ruta:
        st.success(
            f"**Óptima recalculada:** {'–'.join(camino_optimo)}\n\n"
            f"Valor de la función objetivo: {valor_objetivo(m_opt):.4f}"
        )
    else:
        st.error("No existe ruta entre H y B con los enlaces disponibles.")

if ruta_estatica_sel and existe_ruta:
    if camino_optimo == RUTAS_ESTATICAS[ruta_estatica_sel]:
        st.write("La ruta estática seleccionada coincide con la óptima recalculada.")
    else:
        v_est = valor_objetivo(metricas_ruta(RUTAS_ESTATICAS[ruta_estatica_sel]))
        v_opt = valor_objetivo(m_opt)
        st.warning(
            f"La ruta estática seleccionada difiere de la óptima recalculada "
            f"(objetivo {v_est:.4f} frente a {v_opt:.4f})."
        )

# ---------------------------------------------------------------------------
# 3. Sink Tree hacia B
# ---------------------------------------------------------------------------
st.header("3. Sink Tree hacia B")
st.caption("Cada router apunta a un único siguiente salto hacia el destino. No es el grafo completo ni una lista de rutas de respaldo.")

distancias, caminos = nx.single_source_dijkstra(G, DESTINO, weight="peso")

tabla_sink, sink_edges = [], []
for nodo in sorted(G.nodes()):
    if nodo == DESTINO:
        tabla_sink.append({"Router": nodo, "Siguiente salto": "Destino", "Costo acumulado": "0"})
    elif nodo in caminos:
        camino = caminos[nodo][::-1]  # nodo -> ... -> B
        sig = camino[1]
        sink_edges.append((nodo, sig))
        tabla_sink.append({"Router": nodo, "Siguiente salto": sig, "Costo acumulado": f"{distancias[nodo]:.4g}"})
    else:
        tabla_sink.append({"Router": nodo, "Siguiente salto": "Aislado", "Costo acumulado": "—"})

col1, col2 = st.columns([1, 2])
with col1:
    st.dataframe(pd.DataFrame(tabla_sink), hide_index=True)

with col2:
    pos = {k: v for k, v in POS.items() if G.has_node(k)}
    sink_set = {frozenset(e) for e in sink_edges}

    def segmentos(aristas):
        xs, ys = [], []
        for a, b in aristas:
            if a in pos and b in pos:
                xs += [pos[a][0], pos[b][0], None]
                ys += [pos[a][1], pos[b][1], None]
        return xs, ys

    otras = [e for e in G.edges() if frozenset(e) not in sink_set]
    caidos = [(r["Origen"], r["Destino"]) for _, r in df.iterrows() if not r["Disponible"]]

    fig = go.Figure()
    ox, oy = segmentos(otras)
    fig.add_trace(go.Scatter(x=ox, y=oy, mode="lines", line=dict(width=1.5, color="#BBBBBB"), hoverinfo="skip"))
    cx, cy = segmentos(caidos)
    fig.add_trace(go.Scatter(x=cx, y=cy, mode="lines", line=dict(width=1.5, color="#D62728", dash="dash"), hoverinfo="skip"))
    sx, sy = segmentos(sink_edges)
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines", line=dict(width=3, color="#1F4E79"), hoverinfo="skip"))

    nodos = list(pos.keys())
    colores = ["#D62728" if n == DESTINO else ("#2CA02C" if n in camino_optimo else "#1F77B4") for n in nodos]
    fig.add_trace(
        go.Scatter(
            x=[pos[n][0] for n in nodos],
            y=[pos[n][1] for n in nodos],
            mode="markers+text",
            text=nodos,
            textposition="top center",
            marker=dict(size=22, color=colores),
            hoverinfo="text",
            hovertext=[f"Router {n}" for n in nodos],
        )
    )

    # Flechas hacia el siguiente salto (acortadas para no tapar los nodos)
    for a, b in sink_edges:
        if a in pos and b in pos:
            x0, y0 = pos[a]
            x1, y1 = pos[b]
            t0, t1 = 0.14, 0.86
            fig.add_annotation(
                x=x0 + (x1 - x0) * t1, y=y0 + (y1 - y0) * t1,
                ax=x0 + (x1 - x0) * t0, ay=y0 + (y1 - y0) * t0,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=3, arrowsize=1.4, arrowwidth=2, arrowcolor="#1F4E79",
            )

    fig.update_layout(
        showlegend=False,
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    st.plotly_chart(fig)
    st.caption(
        "Rojo: destino B · Verde: camino óptimo H–B · Azul: otros routers · "
        "Flechas azules: Sink Tree · Rojo discontinuo: enlaces caídos · Gris: enlaces activos fuera del Sink Tree"
    )

# ---------------------------------------------------------------------------
# 4. Exportar evidencias
# ---------------------------------------------------------------------------
st.header("4. Exportar resultados")
df_exp = pd.DataFrame(filas)
df_exp["Funcion_objetivo"] = funcion_opt
df_exp["alpha_beta_gamma"] = f"({alpha:.3f}, {beta:.3f}, {gamma:.3f})"
df_exp["d_ref"] = d_ref
df_exp["b_ref"] = b_ref
df_exp["Estatica_seleccionada"] = ruta_estatica_sel or "Ninguna"
df_exp["Camino_optimo"] = "–".join(camino_optimo) if camino_optimo else "Sin ruta"

st.download_button(
    "Descargar CSV de resultados",
    data=df_exp.to_csv(index=False).encode("utf-8-sig"),
    file_name="resultados_experimentos.csv",
    mime="text/csv",
)
