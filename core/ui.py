"""Sistema de design compartilhado — "Fintech Premium" (índigo + verde, claro).

Uma única função `aplicar_estilo()` injeta o CSS que reveste os componentes
nativos do Streamlit (métricas, cards, abas, botões, sidebar) para um visual
coeso em desktop e mobile. Chamada no topo de cada página.

Também oferece helpers opcionais (kpi, section_header, alerta) para telas
que querem ir além do padrão.
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens (mantidos em sincronia com o mockup aprovado)
# ---------------------------------------------------------------------------
COR = {
    "primaria": "#4F46E5",
    "primaria_hover": "#4338CA",
    "primaria_bg": "#EEF0FE",
    "fundo": "#FBFBFD",
    "superficie": "#FFFFFF",
    "superficie_2": "#F4F4F7",
    "borda": "#E7E7EE",
    "borda_forte": "#D8D8E2",
    "texto": "#1A1A2E",
    "texto_2": "#6B6B7B",
    "texto_3": "#9A9AA8",
    "sucesso": "#059669",
    "sucesso_bg": "#ECFDF5",
    "perigo": "#DC2626",
    "perigo_bg": "#FEF2F2",
    "aviso": "#B45309",
    "aviso_bg": "#FFFBEB",
}


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --fin-primaria: #4F46E5;
  --fin-primaria-hover: #4338CA;
  --fin-primaria-bg: #EEF0FE;
  --fin-fundo: #FBFBFD;
  --fin-superficie: #FFFFFF;
  --fin-superficie-2: #F4F4F7;
  --fin-borda: #E7E7EE;
  --fin-borda-forte: #D8D8E2;
  --fin-texto: #1A1A2E;
  --fin-texto-2: #6B6B7B;
  --fin-texto-3: #9A9AA8;
  --fin-sucesso: #059669;
  --fin-sucesso-bg: #ECFDF5;
  --fin-perigo: #DC2626;
  --fin-perigo-bg: #FEF2F2;
  --fin-aviso: #B45309;
  --fin-aviso-bg: #FFFBEB;
}

/* ---- Base tipográfica ---- */
html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.stApp { background: var(--fin-fundo); }

/* Container principal: largura confortável e respiro */
.block-container {
  padding-top: 2.2rem;
  padding-bottom: 3rem;
  max-width: 1180px;
}

/* ---- Títulos ---- */
h1 { font-weight: 600 !important; letter-spacing: -0.025em; color: var(--fin-texto); }
h2 { font-weight: 600 !important; letter-spacing: -0.02em; }
h3 { font-weight: 600 !important; letter-spacing: -0.015em; }

/* ---- Métricas viram cards premium ---- */
[data-testid="stMetric"] {
  background: var(--fin-superficie);
  border: 0.5px solid var(--fin-borda);
  border-radius: 14px;
  padding: 16px 18px;
  transition: border-color .15s ease, box-shadow .15s ease;
}
[data-testid="stMetric"]:hover {
  border-color: var(--fin-borda-forte);
  box-shadow: 0 1px 3px rgba(20,20,40,0.04);
}
[data-testid="stMetricLabel"] {
  color: var(--fin-texto-3);
  font-size: 12.5px !important;
  font-weight: 500;
}
[data-testid="stMetricLabel"] p { font-size: 12.5px !important; }
[data-testid="stMetricValue"] {
  color: var(--fin-texto);
  font-size: 26px !important;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.15;
}
[data-testid="stMetricDelta"] {
  font-size: 12px !important;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
  width: fit-content;
  margin-top: 6px;
}

/* ---- Containers com borda (cards de seção) ---- */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 16px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
  border-color: var(--fin-borda) !important;
}

/* ---- Botões ---- */
.stButton > button {
  border-radius: 10px;
  border: 0.5px solid var(--fin-borda-forte);
  font-weight: 500;
  transition: all .15s ease;
  padding: 6px 16px;
}
.stButton > button:hover {
  border-color: var(--fin-primaria);
  color: var(--fin-primaria);
}
.stButton > button[kind="primary"] {
  background: var(--fin-primaria);
  border-color: var(--fin-primaria);
}
.stButton > button[kind="primary"]:hover {
  background: var(--fin-primaria-hover);
  border-color: var(--fin-primaria-hover);
  color: #fff;
}

/* ---- Abas ---- */
.stTabs [data-baseweb="tab-list"] {
  gap: 4px;
  border-bottom: 0.5px solid var(--fin-borda);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 8px 8px 0 0;
  padding: 8px 16px;
  font-weight: 500;
}
.stTabs [aria-selected="true"] {
  color: var(--fin-primaria) !important;
}
.stTabs [data-baseweb="tab-highlight"] { background: var(--fin-primaria); }

/* ---- Inputs ---- */
[data-baseweb="input"], [data-baseweb="select"] > div, .stTextInput input,
.stNumberInput input, .stDateInput input {
  border-radius: 10px !important;
}
input:focus, textarea:focus, [data-baseweb="input"]:focus-within,
[data-baseweb="select"] > div:focus-within {
  border-color: var(--fin-primaria) !important;
  box-shadow: 0 0 0 3px var(--fin-primaria-bg) !important;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
  background: var(--fin-superficie);
  border-right: 0.5px solid var(--fin-borda);
}
[data-testid="stSidebarNav"] a {
  border-radius: 8px;
  margin: 1px 8px;
}
[data-testid="stSidebarNav"] a:hover {
  background: var(--fin-superficie-2);
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: var(--fin-primaria-bg);
}
[data-testid="stSidebarNav"] a[aria-current="page"] span {
  color: var(--fin-primaria) !important;
  font-weight: 600;
}

/* ---- Alertas (st.info/warning/success/error) mais suaves ---- */
[data-testid="stAlert"] { border-radius: 12px; border: 0.5px solid transparent; }

/* ---- DataFrames ---- */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

/* ---- Expander ---- */
[data-testid="stExpander"] {
  border-radius: 12px;
  border: 0.5px solid var(--fin-borda);
}

/* ---- Divider mais leve ---- */
hr { border-color: var(--fin-borda); margin: 1.2rem 0; }

/* =======================================================================
   RESPONSIVO — mobile
   ======================================================================= */
@media (max-width: 640px) {
  .block-container { padding: 1.2rem 0.8rem 2rem; }
  [data-testid="stMetricValue"] { font-size: 22px !important; }
  [data-testid="stMetric"] { padding: 13px 14px; }
  h1 { font-size: 1.6rem !important; }
  .stTabs [data-baseweb="tab"] { padding: 8px 12px; font-size: 13px; }
  /* Alvos de toque maiores */
  .stButton > button { min-height: 42px; }
}
</style>
"""


def aplicar_estilo() -> None:
    """Injeta o CSS do sistema de design. Chamar no topo de cada página,
    logo após init_db()."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers opcionais (para telas que querem ir além do st.metric padrão)
# ---------------------------------------------------------------------------
def cabecalho_pagina(titulo: str, subtitulo: str = "", icone: str = "") -> None:
    """Cabeçalho de página com ícone em badge arredondado."""
    ico = f'<span style="font-size:22px;margin-right:2px">{icone}</span>' if icone else ""
    sub = (f'<div style="color:{COR["texto_2"]};font-size:14px;margin-top:2px">{subtitulo}</div>'
           if subtitulo else "")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;
                    padding-top:4px">
          {ico}
          <div>
            <div style="font-size:26px;font-weight:600;letter-spacing:-0.025em;
                        color:{COR['texto']};line-height:1.35;
                        padding-top:2px">{titulo}</div>
            {sub}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def secao(titulo: str, icone: str = "") -> None:
    """Cabeçalho de seção discreto."""
    ico = f'{icone} ' if icone else ""
    st.markdown(
        f'<div style="font-size:15px;font-weight:600;letter-spacing:-0.01em;'
        f'color:{COR["texto"]};margin:8px 0 4px">{ico}{titulo}</div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, valor: str, delta: str = "", delta_tom: str = "neutro",
        icone: str = "", cor_valor: str = "") -> None:
    """Card de KPI premium: ícone+label, número grande, pill de variação.
    Renderizado direto (use dentro de st.columns)."""
    ico = f'<span style="font-size:15px">{icone}</span> ' if icone else ""
    delta_html = (f'<div style="margin-top:8px">{pill(delta, delta_tom)}</div>'
                  if delta else "")
    cor = cor_valor or COR["texto"]
    st.markdown(
        f"""
        <div style="background:{COR['superficie']};border:0.5px solid {COR['borda']};
                    border-radius:14px;padding:15px 17px;min-height:112px">
          <div style="display:flex;align-items:center;gap:5px;color:{COR['texto_3']};
                      font-size:12.5px;font-weight:500;margin-bottom:8px">{ico}{label}</div>
          <div style="font-size:25px;font-weight:600;letter-spacing:-0.03em;
                      color:{cor};line-height:1.25">{valor}</div>
          {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def pill(texto: str, tom: str = "neutro") -> str:
    """Retorna HTML de uma pill colorida. tom: sucesso/perigo/aviso/accent/neutro."""
    mapa = {
        "sucesso": (COR["sucesso_bg"], COR["sucesso"]),
        "perigo": (COR["perigo_bg"], COR["perigo"]),
        "aviso": (COR["aviso_bg"], COR["aviso"]),
        "accent": (COR["primaria_bg"], COR["primaria"]),
        "neutro": (COR["superficie_2"], COR["texto_2"]),
    }
    bg, fg = mapa.get(tom, mapa["neutro"])
    return (f'<span style="display:inline-flex;align-items:center;gap:3px;'
            f'font-size:11.5px;font-weight:500;padding:2px 9px;border-radius:20px;'
            f'background:{bg};color:{fg}">{texto}</span>')
