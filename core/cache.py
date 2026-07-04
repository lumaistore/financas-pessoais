"""Cache leve para leituras — reduz idas ao banco (Neon) a cada rerun.

`@cache_leitura` embrulha a função com st.cache_data (TTL curto). Como o
Streamlit reexecuta o script inteiro a cada clique/navegação, sem cache toda
leitura vira uma consulta nova ao Postgres na nuvem (lento). Com cache, o
resultado é reaproveitado entre reruns.

`invalidar()` limpa o cache — chamada após qualquer escrita, para que a
próxima leitura reflita o dado novo (sem janela de defasagem).
"""
from __future__ import annotations

TTL_PADRAO = 120  # segundos


def cache_leitura(func=None, *, ttl: int = TTL_PADRAO):
    """Decorator. Uso: @cache_leitura ou @cache_leitura(ttl=300)."""
    def deco(f):
        try:
            import streamlit as st
            return st.cache_data(ttl=ttl, show_spinner=False)(f)
        except Exception:
            # Fora do Streamlit (testes/scripts): sem cache, função crua.
            return f
    return deco(func) if func is not None else deco


def invalidar() -> None:
    """Limpa todo o cache de leitura. Chamar após inserir/editar/excluir."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass


def invalida_cache(func):
    """Decorator para funções de ESCRITA: roda a função e limpa o cache depois,
    para que a próxima leitura reflita o dado novo."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        resultado = func(*args, **kwargs)
        invalidar()
        return resultado

    return wrapper
