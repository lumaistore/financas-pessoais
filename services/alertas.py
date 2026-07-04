"""Alertas: dispensa de alertas padrão + geração de alertas por IA.

- Alertas padrão (services.painel.alertas) têm uma `chave` estável; o usuário
  pode dispensar por chave (fica guardado). Pode restaurar depois.
- Alertas inteligentes: uma IA analisa o resumo da conta e propõe insights
  acionáveis, guardados como registros (dispensáveis um a um).
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select

from core.cache import cache_leitura
from core.db import get_session
from core.models import AlertaDispensado, AlertaInteligente

MODELO_IA = "claude-sonnet-4-5-20250929"


def _limpar_cache_alertas() -> None:
    """Limpa APENAS os caches ligados a alertas (não o painel inteiro).
    Dispensar/restaurar alerta é leve; não deve recalcular fluxo/patrimônio."""
    for f in (dispensados, listar_ia):
        try:
            f.clear()
        except Exception:
            pass
    try:
        from services.painel import alertas
        alertas.clear()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dispensa dos alertas padrão (por chave)
# ---------------------------------------------------------------------------
@cache_leitura
def dispensados() -> List[str]:
    with get_session() as s:
        return [d.chave for d in s.scalars(select(AlertaDispensado)).all()]


def dispensar(chave: str) -> None:
    with get_session() as s:
        existe = s.scalar(select(AlertaDispensado).where(AlertaDispensado.chave == chave))
        if not existe:
            s.add(AlertaDispensado(chave=chave))
    _limpar_cache_alertas()


def restaurar_todos() -> int:
    n = 0
    with get_session() as s:
        for d in s.scalars(select(AlertaDispensado)).all():
            s.delete(d)
            n += 1
    _limpar_cache_alertas()
    return n


# ---------------------------------------------------------------------------
# Alertas inteligentes (IA)
# ---------------------------------------------------------------------------
@cache_leitura
def listar_ia() -> List[dict]:
    with get_session() as s:
        rs = s.scalars(
            select(AlertaInteligente).order_by(AlertaInteligente.prioridade)
        ).all()
        return [
            {"id": a.id, "titulo": a.titulo, "descricao": a.descricao,
             "prioridade": a.prioridade}
            for a in rs
        ]


def dispensar_ia(alerta_id: int) -> None:
    with get_session() as s:
        a = s.get(AlertaInteligente, alerta_id)
        if a:
            s.delete(a)
    try:
        listar_ia.clear()
    except Exception:
        pass


def _contexto_conta(mes_ref: str) -> str:
    """Resumo objetivo da conta para a IA analisar (sem inventar dados)."""
    from services.painel import (
        fluxo_com_delta, gastos_categoria_pivot, media_gasto_meses,
    )

    f = fluxo_com_delta(mes_ref)
    mg = media_gasto_meses(mes_ref)
    pivot = gastos_categoria_pivot()

    linhas = [
        f"Mês de referência: {mes_ref}",
        f"Recebido no mês: R$ {f['receitas']:.2f}",
        f"Gasto real no mês (sem LUMAI): R$ {f['gasto_real']:.2f}",
        f"Aplicado (investido) no mês: R$ {f['aplicacoes']:.2f}",
        f"Taxa de poupança: {f['taxa_poupanca']:.0f}%",
        f"Média de gasto dos últimos meses: R$ {mg['media']:.2f}",
        "",
        "Gasto por categoria, mês a mês (valores em R$):",
    ]
    meses = pivot["meses"]
    for ln in pivot["linhas"][:12]:
        vals = ", ".join(f"{m}={ln['por_mes'].get(m, 0):.0f}" for m in meses)
        linhas.append(f"- {ln['categoria']}: {vals}")
    return "\n".join(linhas)


_PROMPT = """
Você é um consultor financeiro pessoal analisando a conta de um usuário.
Com base SOMENTE nos dados abaixo (não invente nada), proponha de 2 a 4
ALERTAS curtos e ACIONÁVEIS — coisas que ele deveria notar ou fazer.

Priorize: categorias que cresceram muito, gastos acima da média, oportunidades
de economizar ou investir mais, padrões nas assinaturas, concentração de gastos.

Formato EXATO — uma linha por alerta, sem numeração:
TÍTULO CURTO | descrição objetiva com o número relevante

Exemplos:
Viagem subiu forte | Gastou R$ 4.446 em Viagem, bem acima da média — reveja se foi pontual.
Assinaturas recorrentes | R$ 209/mês em Assinaturas — cancele o que não usa.

Seja específico com os números reais. Português do Brasil. Só as linhas, nada mais.

DADOS DA CONTA:
""".strip()


def gerar_ia(mes_ref: str) -> int:
    """Gera novos alertas inteligentes (substitui os anteriores). Retorna
    quantos criou. 0 se não houver chave de API."""
    from core.config import get_anthropic_key

    chave = get_anthropic_key()
    if not chave:
        return -1  # sinaliza falta de chave

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=chave)
        resp = client.messages.create(
            model=MODELO_IA,
            max_tokens=700,
            messages=[{"role": "user",
                       "content": _PROMPT + "\n" + _contexto_conta(mes_ref)}],
        )
        texto = resp.content[0].text
    except Exception:
        return -2  # falha na API

    # Parse "TÍTULO | descrição"
    novos = []
    for linha in texto.splitlines():
        linha = linha.strip().lstrip("-•*0123456789. ").strip()
        if "|" in linha:
            titulo, desc = linha.split("|", 1)
            titulo = titulo.strip()
            desc = desc.strip()
            if titulo:
                novos.append((titulo, desc))

    with get_session() as s:
        # Substitui os anteriores por uma análise fresca.
        for a in s.scalars(select(AlertaInteligente)).all():
            s.delete(a)
        for i, (titulo, desc) in enumerate(novos[:4]):
            s.add(AlertaInteligente(titulo=titulo, descricao=desc, prioridade=i))
    try:
        listar_ia.clear()
    except Exception:
        pass
    return len(novos[:4])
