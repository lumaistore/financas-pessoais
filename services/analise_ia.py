"""Análise educativa da carteira via API Anthropic (Fase 6).

Privacidade em primeiro lugar:
- A chave da API é lida APENAS da variável de ambiente ANTHROPIC_API_KEY
  (carregada do arquivo .env local). Nunca fica escrita no código nem é
  versionada.
- Só números agregados saem da máquina (totais, percentuais, classes de
  ativo). Nada de CPF, números de contrato, dados bancários ou senhas.
- A resposta é sempre apresentada como análise EDUCATIVA, não recomendação
  personalizada de compra ou venda.
"""
from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

from dotenv import load_dotenv

from services.cartao import gasto_por_categoria, gasto_total
from services.compromissos import (
    listar_compromissos,
    total_financiamento_a_contratar,
    total_parcelas_mes,
    total_saldo_devedor,
)
from services.investimentos import (
    listar_datas,
    por_classe,
    rendimento,
    total_carteira,
)
from services.movimentacoes import total_por_tipo as _total_por_tipo


def total_recebido(mes_ref: str) -> float:
    return _total_por_tipo(mes_ref, "receita")

# Carrega .env uma vez (silencioso se o arquivo não existir). override=True faz
# o valor do .env vencer uma variável de ambiente herdada vazia do shell.
load_dotenv(override=True)

MODELO = "claude-sonnet-4-5-20250929"

DISCLAIMER = (
    "⚠️ Esta é uma análise **educativa** gerada por IA a partir dos seus "
    "números agregados — **não** é recomendação personalizada de compra ou "
    "venda de ativos. Decisões de investimento são suas; em caso de dúvida, "
    "procure um profissional certificado."
)

NOME_VARIAVEL = "ANTHROPIC_API_KEY"


class IAIndisponivelError(Exception):
    """Sinaliza um problema amigável para a tela (sem stack trace)."""


def chave_configurada() -> bool:
    """True se a chave estiver disponível (env local ou st.secrets na nuvem)."""
    from core.config import get_anthropic_key

    return bool((get_anthropic_key() or "").strip())


# ---------------------------------------------------------------------------
# Montagem do contexto agregado (só números, nada sensível)
# ---------------------------------------------------------------------------
def montar_contexto(mes_ref: Optional[str] = None) -> dict:
    """Reúne os números agregados das demais fases num dicionário simples."""
    if mes_ref is None:
        mes_ref = date.today().strftime("%Y-%m")

    datas = listar_datas()
    carteira: dict = {}
    if datas:
        data_inv = datas[0]
        carteira = {
            "data_posicao": data_inv.strftime("%d/%m/%Y"),
            "total": round(total_carteira(data_inv), 2),
            "por_classe": [
                {"classe": c["classe"], "total": round(c["total"], 2)}
                for c in por_classe(data_inv)
            ],
            "rendimento": {
                k: round(v, 2) for k, v in rendimento(data_inv).items()
            },
        }

    recebido = total_recebido(mes_ref)
    gasto = gasto_total(mes_ref)
    parcelas = total_parcelas_mes(mes_ref)

    compromissos = [
        {
            "nome": c["nome"],
            "tipo": "imóvel" if c.get("eh_imovel") else "parcelamento",
            "saldo_devedor": round(c["saldo_devedor"], 2),
            "progresso_pct": round(c["progresso"] * 100, 1),
        }
        for c in listar_compromissos(apenas_ativos=True)
    ]

    return {
        "mes_referencia": mes_ref,
        "fluxo_mes": {
            "recebido": round(recebido, 2),
            "gasto_cartao": round(gasto, 2),
            "parcelas_compromissos": round(parcelas, 2),
            "sobra": round(recebido - gasto - parcelas, 2),
        },
        "gasto_por_categoria": [
            {"categoria": g["categoria"], "total": round(g["total"], 2)}
            for g in gasto_por_categoria(mes_ref)
        ],
        "carteira": carteira,
        "compromissos_ativos": compromissos,
        "saldo_devedor_total": round(total_saldo_devedor(), 2),
        "financiamento_a_contratar": round(total_financiamento_a_contratar(), 2),
    }


def _formatar_brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def contexto_para_texto(ctx: dict) -> str:
    """Converte o contexto em um texto legível para enviar ao modelo."""
    linhas: List[str] = []
    linhas.append(f"Mês de referência: {ctx['mes_referencia']}")

    fx = ctx["fluxo_mes"]
    linhas.append("\n## Fluxo do mês")
    linhas.append(f"- Recebido: {_formatar_brl(fx['recebido'])}")
    linhas.append(f"- Gasto no cartão: {_formatar_brl(fx['gasto_cartao'])}")
    linhas.append(f"- Parcelas/compromissos: {_formatar_brl(fx['parcelas_compromissos'])}")
    linhas.append(f"- Sobra: {_formatar_brl(fx['sobra'])}")

    if ctx["gasto_por_categoria"]:
        linhas.append("\n## Gasto por categoria")
        for g in ctx["gasto_por_categoria"]:
            linhas.append(f"- {g['categoria']}: {_formatar_brl(g['total'])}")

    cart = ctx["carteira"]
    if cart:
        linhas.append(f"\n## Carteira de investimentos (posição de {cart['data_posicao']})")
        linhas.append(f"- Patrimônio total: {_formatar_brl(cart['total'])}")
        rend = cart["rendimento"]
        linhas.append(
            f"- Rendimento (custo conhecido): {_formatar_brl(rend['lucro'])} "
            f"({rend['percentual']:.2f}% sobre {_formatar_brl(rend['investido'])})"
        )
        linhas.append("- Distribuição por classe:")
        for c in cart["por_classe"]:
            pct = (c["total"] / cart["total"] * 100) if cart["total"] else 0
            linhas.append(f"  - {c['classe']}: {_formatar_brl(c['total'])} ({pct:.1f}%)")
    else:
        linhas.append("\n## Carteira de investimentos\n- Nenhuma posição registrada.")

    linhas.append("\n## Compromissos")
    linhas.append(f"- Saldo devedor total: {_formatar_brl(ctx['saldo_devedor_total'])}")
    if ctx["financiamento_a_contratar"]:
        linhas.append(
            f"- Financiamento imobiliário a contratar (entrega das chaves): "
            f"{_formatar_brl(ctx['financiamento_a_contratar'])}"
        )
    for c in ctx["compromissos_ativos"]:
        linhas.append(
            f"- {c['nome']} ({c['tipo']}): saldo {_formatar_brl(c['saldo_devedor'])}, "
            f"{c['progresso_pct']:.0f}% pago"
        )

    return "\n".join(linhas)


PROMPT_SISTEMA = (
    "Você é um educador financeiro que conversa em português do Brasil. "
    "Você recebe um panorama agregado das finanças pessoais de alguém e produz "
    "uma análise EDUCATIVA e acolhedora — nunca uma recomendação personalizada "
    "de compra ou venda de ativos específicos. "
    "Estruture a resposta em seções curtas com markdown: (1) Visão geral do mês, "
    "(2) Pontos fortes, (3) Pontos de atenção, (4) Perguntas para a pessoa refletir. "
    "Seja concreto usando os números fornecidos, mas evite jargão. "
    "Nunca invente dados que não estão no panorama. "
    "Não recomende ativos específicos; fale de conceitos (diversificação, reserva "
    "de emergência, concentração de risco, relação entre dívida e patrimônio)."
)


def analisar_carteira(mes_ref: Optional[str] = None, pergunta_extra: str = "") -> str:
    """Chama a API Anthropic com o contexto agregado e devolve a análise.

    Levanta IAIndisponivelError com mensagem amigável se a chave não estiver
    configurada ou se a chamada falhar (rede, etc.).
    """
    if not chave_configurada():
        raise IAIndisponivelError(
            f"A chave da API não foi encontrada. Crie um arquivo `.env` na pasta "
            f"do projeto com a linha `{NOME_VARIAVEL}=sua-chave-aqui`."
        )

    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise IAIndisponivelError(
            "A biblioteca `anthropic` não está instalada. Rode: "
            "`.venv/bin/pip install anthropic`."
        ) from exc

    ctx = montar_contexto(mes_ref)
    texto_ctx = contexto_para_texto(ctx)

    mensagem_usuario = (
        "Aqui está o panorama agregado das minhas finanças. Faça uma análise "
        "educativa conforme suas instruções.\n\n" + texto_ctx
    )
    if pergunta_extra.strip():
        mensagem_usuario += (
            "\n\n## Algo específico que eu gostaria de entender\n"
            + pergunta_extra.strip()
        )

    try:
        from core.config import get_anthropic_key

        client = Anthropic(api_key=get_anthropic_key())
        resposta = client.messages.create(
            model=MODELO,
            max_tokens=1500,
            system=PROMPT_SISTEMA,
            messages=[{"role": "user", "content": mensagem_usuario}],
        )
    except Exception as exc:  # rede, chave inválida, rate limit, etc.
        raise IAIndisponivelError(
            "Não consegui falar com a API da Anthropic agora. Verifique sua "
            f"conexão e se a chave está correta. Detalhe técnico: {exc}"
        ) from exc

    partes = [bloco.text for bloco in resposta.content if getattr(bloco, "type", None) == "text"]
    return "\n".join(partes).strip() or "(resposta vazia da IA)"
