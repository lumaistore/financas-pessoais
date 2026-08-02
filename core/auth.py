"""Autenticação simples por senha — permite deixar o app público no Streamlit
(sem login da plataforma) mas protegido por uma senha só sua.

A senha fica em `st.secrets["APP_SENHA"]` (ou na env APP_SENHA) — NUNCA no
código. Enquanto nenhuma senha estiver configurada, o app NÃO bloqueia (para
não travar durante a configuração).
"""
from __future__ import annotations

import hmac
import os

import streamlit as st


def _senha_esperada() -> str:
    try:
        s = st.secrets.get("APP_SENHA", None)
    except Exception:
        s = None
    return (s or os.environ.get("APP_SENHA") or "").strip()


def exigir_senha() -> None:
    """Bloqueia a página até a senha correta ser digitada. Chamar no topo de
    cada página, logo após aplicar_estilo(). Sem senha configurada → libera."""
    esperada = _senha_esperada()
    if not esperada:
        return  # nenhuma senha definida ainda → não bloqueia

    if st.session_state.get("_auth_ok"):
        return

    from core.ui import COR

    st.markdown(
        f"""
        <div style="max-width:420px;margin:9vh auto 0;text-align:center">
          <div style="font-size:48px;line-height:1">🔒</div>
          <div style="font-size:23px;font-weight:600;letter-spacing:-0.02em;
                      color:{COR['texto']};margin-top:6px">Finanças Pessoais</div>
          <div style="color:{COR['texto_2']};font-size:14px;margin-top:2px">
            Digite sua senha para acessar</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        senha = st.text_input("Senha", type="password",
                              label_visibility="collapsed", placeholder="Senha")
        if senha:
            if hmac.compare_digest(senha.strip(), esperada):
                st.session_state["_auth_ok"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()
