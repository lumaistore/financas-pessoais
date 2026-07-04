"""Assessor de Investimentos — persona sênior com equipe multi-mercado.

⚠️ IMPORTANTE: análise educativa, NÃO recomendação personalizada de compra
ou venda de ativos (regra CVM). O disclaimer aparece em todas as respostas.

Como funciona:
- Antes da consulta, montamos um contexto com a carteira ATUAL do usuário.
- O usuário informa quanto quer investir.
- O assessor "consulta" mentalmente a equipe (BR/EUA/China/Europa) via
  system prompt e propõe 2-3 cenários de alocação com racional de longo prazo.
- A conversa continua: o usuário questiona e ajustam decisões juntos.
- A conversa fica salva para retomar.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import ConsultaAssessor
from services.investimentos import listar_datas, por_classe, rendimento, total_carteira

MODELO = "claude-sonnet-4-5-20250929"

DISCLAIMER = (
    "⚠️ **Análise educativa.** Não é recomendação personalizada de compra ou "
    "venda de ativos. Decisões de investimento são suas — consulte um "
    "profissional certificado (CVM) para orientação personalizada."
)

# ---------------------------------------------------------------------------
# System prompt: encarna o assessor sênior com a equipe multi-mercado.
# ---------------------------------------------------------------------------
PROMPT_SISTEMA = """
Você é **Ricardo Andrade**, assessor de investimentos sênior com mais de 20 anos
de experiência iniciada em Wall Street (Goldman/Morgan Stanley) e hoje gestor
de wealth para famílias no Brasil. Você não vende ativos — você constrói e
mantém carteiras de longo prazo (5, 10, 20 anos).

Você lidera uma equipe de analistas que você **consulta mentalmente antes de
falar**:

- **Ana Costa** (Brasil): renda fixa DI/pré/IPCA+, ações e FIIs. Contexto
  atual: taxa Selic, IPCA, ciclo político/fiscal, câmbio.
- **Michael Chen** (EUA): equities S&P/NASDAQ, treasuries, corporate bonds,
  ETFs de qualidade. Foco em fed policy, real yields, earnings.
- **Li Wei** (China/Ásia): H-shares, ADRs chinesas, Japão, Índia. Foco em
  ciclo imobiliário/estímulos, risco geopolítico.
- **Klaus Berger** (Europa): DAX/CAC, renda fixa €, small-caps de qualidade.
  Foco em ECB, energia, competitividade industrial.

**FILOSOFIA:**
1. **Longo prazo sempre** — decisão que sobreviva a ciclos macroeconômicos,
   trocas de governo, choques geopolíticos, correções de mercado.
2. **Diversificação real** — por classe (RF/RV/imóveis/caixa), por geografia
   (BR/EUA/desenvolvidos ex-US/emergentes) e por moeda.
3. **Compostos e paciência** — valorizar dividendos crescentes, juros
   compostos, evitar market timing.
4. **Simplicidade** — se não conseguir explicar em 3 frases por que uma
   posição faz sentido em 10 anos, não é uma boa posição.

**COMO RESPONDER:**
1. Fale como um assessor humano — direto, seguro, sem jargão desnecessário.
2. Cite mentalmente o time quando fizer diferença: *"A Ana lembra que…",
   "O Michael observaria…"*.
3. Ofereça **2 ou 3 opções de alocação** ao pedido (conservadora / balanceada
   / mais construtiva), NUNCA uma única "certa". Justifique cada uma em 2-4
   linhas de racional de longo prazo.
4. **Aponte** concentrações e riscos da carteira atual (com carinho, sem
   pânico). Sugestões devem endereçá-los quando fizer sentido.
5. **Termine com 2-3 perguntas** para o usuário refletir/direcionar.
6. Não diga "compre X" nem "venda Y" — diga "avaliar aumentar exposição em X
   pelos motivos Z" ou "considerar reduzir…".
7. **Regra CVM**: análise educativa, NÃO recomendação personalizada. Sempre
   deixe implícito que a decisão é do usuário.

**QUANDO O USUÁRIO QUESTIONAR:**
- Escute o argumento. Se for válido, **ajuste** a proposta.
- Se for equívoco (ex.: euforia com um ativo específico, market timing),
  **discorde educadamente** e explique com base em histórico/racional.
- Traga a perspectiva do especialista mais relevante para o tema.

**PORTUGUÊS DO BRASIL. Formato Markdown.**
""".strip()


# ---------------------------------------------------------------------------
# Contexto (carteira atual)
# ---------------------------------------------------------------------------
def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def montar_contexto_carteira() -> str:
    """Resumo compacto da carteira atual (última posição) para o assessor."""
    datas = listar_datas()
    if not datas:
        return "O usuário ainda não tem carteira cadastrada no sistema."
    d = datas[0]
    total = total_carteira(d)
    classes = por_classe(d)
    rend = rendimento(d)

    linhas = [
        f"**Data da posição:** {d.strftime('%d/%m/%Y')}",
        f"**Patrimônio total:** {_brl(total)}",
        (f"**Rendimento (posições com custo conhecido):** {_brl(rend['lucro'])} "
         f"({rend['percentual']:.2f}%)"),
        "",
        "**Distribuição por classe:**",
    ]
    for c in classes:
        pct = (c["total"] / total * 100) if total else 0
        linhas.append(f"- {c['classe']}: {_brl(c['total'])} ({pct:.1f}%)")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# CRUD de consultas
# ---------------------------------------------------------------------------
def criar_consulta(valor_investir: Optional[float], contexto: str, titulo: str = "") -> int:
    with get_session() as s:
        c = ConsultaAssessor(
            valor_investir=valor_investir,
            contexto_carteira=contexto,
            conversa_json=json.dumps([]),
            titulo=titulo or f"Consulta {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        )
        s.add(c)
        s.flush()
        return c.id


def listar_consultas() -> List[dict]:
    with get_session() as s:
        rs = s.scalars(
            select(ConsultaAssessor).order_by(ConsultaAssessor.criada_em.desc())
        ).all()
        out = []
        for r in rs:
            conv = json.loads(r.conversa_json or "[]")
            ultima = conv[-1]["content"][:120] if conv else ""
            out.append({
                "id": r.id,
                "criada_em": r.criada_em,
                "valor_investir": r.valor_investir,
                "titulo": r.titulo,
                "n_mensagens": len(conv),
                "preview": ultima,
            })
        return out


def renomear_consulta(cid: int, titulo: str) -> None:
    with get_session() as s:
        c = s.get(ConsultaAssessor, cid)
        if c:
            c.titulo = titulo.strip() or c.titulo


def duplicar_como_base(cid_origem: int, valor_investir: Optional[float],
                        contexto_atualizado: str, titulo: str) -> Optional[int]:
    """Cria uma nova consulta contendo, como primeira mensagem do assessor,
    um resumo da conversa anterior (para o Ricardo lembrar o histórico).
    Assim, novas aplicações podem partir das decisões passadas."""
    origem = carregar_consulta(cid_origem)
    if not origem:
        return None
    conv_origem = origem["conversa"]
    if not conv_origem:
        return None

    # Resumo bem simples: junta as respostas do assessor (primeira e última).
    respostas = [m["content"] for m in conv_origem if m["role"] == "assistant"]
    resumo_anterior = ""
    if respostas:
        primeira = respostas[0][:800]
        ultima = respostas[-1][:800] if len(respostas) > 1 else ""
        resumo_anterior = (
            "**Resumo da sessão anterior (contexto):**\n\n"
            f"{primeira}"
            + (f"\n\n---\n\n{ultima}" if ultima else "")
        )

    cid = criar_consulta(valor_investir, contexto_atualizado, titulo)
    if resumo_anterior:
        # Marca como uma "mensagem do assistente" para o modelo levar em conta.
        salvar_conversa(cid, [
            {"role": "user", "content": "Lembre-se da nossa última consulta."},
            {"role": "assistant", "content": resumo_anterior},
        ])
    return cid


def carregar_consulta(cid: int) -> Optional[dict]:
    with get_session() as s:
        c = s.get(ConsultaAssessor, cid)
        if not c:
            return None
        return {
            "id": c.id,
            "criada_em": c.criada_em,
            "valor_investir": c.valor_investir,
            "contexto_carteira": c.contexto_carteira,
            "titulo": c.titulo,
            "conversa": json.loads(c.conversa_json or "[]"),
        }


def salvar_conversa(cid: int, conversa: List[dict]) -> None:
    with get_session() as s:
        c = s.get(ConsultaAssessor, cid)
        if c:
            c.conversa_json = json.dumps(conversa, ensure_ascii=False)


def excluir_consulta(cid: int) -> None:
    with get_session() as s:
        c = s.get(ConsultaAssessor, cid)
        if c:
            s.delete(c)


# ---------------------------------------------------------------------------
# Chamada ao modelo
# ---------------------------------------------------------------------------
def conversar(
    valor_investir: Optional[float],
    contexto_carteira: str,
    conversa: List[dict],
    nova_mensagem: str,
) -> str:
    """Manda a próxima pergunta ao assessor e devolve a resposta. `conversa`
    é a lista {role, content} das trocas anteriores (fora o system prompt)."""
    from core.config import get_anthropic_key
    chave = get_anthropic_key()
    if not chave:
        raise RuntimeError(
            "Chave ANTHROPIC_API_KEY não configurada. Não dá para consultar o assessor."
        )

    # Se é a 1ª pergunta, injeta o contexto da carteira e o valor no início.
    if not conversa:
        preambulo = "**Contexto para esta consulta**\n\n"
        preambulo += f"### Carteira atual\n{contexto_carteira}\n\n"
        if valor_investir:
            preambulo += (
                f"### Valor a alocar agora\n{_brl(valor_investir)} "
                f"(aporte único deste mês).\n\n"
            )
        preambulo += "### Pergunta do usuário\n" + nova_mensagem
        mensagem_final = preambulo
    else:
        mensagem_final = nova_mensagem

    mensagens = list(conversa) + [{"role": "user", "content": mensagem_final}]

    from anthropic import Anthropic
    client = Anthropic(api_key=chave)
    resp = client.messages.create(
        model=MODELO,
        max_tokens=2500,
        system=PROMPT_SISTEMA,
        messages=mensagens,
    )
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
