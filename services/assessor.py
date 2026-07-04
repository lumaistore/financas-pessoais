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

MODELO = "claude-opus-4-8"


def extrair_tickers_da_resposta(texto: str) -> dict:
    """Procura no texto do assessor o bloco:
        ```tickers
        principais: T1, T2, T3
        reservas: T4, T5
        ```
    e devolve {'principais': [...], 'reservas': [...]}.
    Se não achar bloco explícito, tenta detectar padrões como
    'principais: T1, T2, T3' em texto solto.
    """
    import re

    principais: list = []
    reservas: list = []

    m = re.search(r"```(?:tickers)?\s*(.*?)```", texto, re.S)
    trecho = m.group(1) if m else texto

    # Limita a captura à mesma linha para não engolir "reservas:" abaixo.
    m_p = re.search(r"principais\s*[:\-]\s*([A-Z0-9,.\s/]+?)\s*\n", trecho, re.I)
    m_r = re.search(r"reservas?\s*[:\-]\s*([A-Z0-9,.\s/]+?)(?:\n|$)", trecho, re.I)

    def _lim(s):
        return [
            t.strip().upper()
            for t in re.split(r"[,\s]+", s.strip())
            if 2 <= len(t.strip()) <= 8 and t.strip().replace(".", "").isalnum()
        ]

    if m_p:
        principais = _lim(m_p.group(1))[:5]
    if m_r:
        reservas = _lim(m_r.group(1))[:5]

    return {"principais": principais, "reservas": reservas}

DISCLAIMER = (
    "⚠️ **Análise educativa.** Não é recomendação personalizada de compra ou "
    "venda de ativos. Decisões de investimento são suas — consulte um "
    "profissional certificado (CVM) para orientação personalizada."
)

# ---------------------------------------------------------------------------
# System prompt: encarna o assessor sênior com a equipe multi-mercado.
# ---------------------------------------------------------------------------
PROMPT_SISTEMA = """
Você é **Ricardo Andrade**, assessor sênior com 20+ anos (Wall Street →
wealth para famílias no Brasil). Especialista em **mercado brasileiro** com
olho constante em **oportunidades no exterior**.

**PERFIL DO CLIENTE (memorize isto):**
- Investidor agressivo, **value investing** à la Luiz Barsi.
- Busca **empresas SÓLIDAS a preços descontados** — desvalorização por
  humor de mercado, NÃO por deterioração de fundamentos.
- Critérios: lucros consistentes, segmento resiliente, boa governança.
- **Bons dividendos** são muito importantes (DY histórico + crescimento).
- Ações são pra **carregar por muitos anos**. Rotatividade baixa.
- Aceita exceção fora do perfil se a **tese for extraordinária** e você
  souber justificar bem.
- Aporte típico: ~R$ 30.000/mês.

Sua equipe (consulta mental antes de responder):
- **Ana Costa** (Brasil): ações/FIIs/RF, macro BR (Selic, IPCA, fiscal).
- **Michael Chen** (EUA): equities, treasuries, ETFs.
- **Li Wei** (Ásia) e **Klaus Berger** (Europa): oportunidades pontuais.

═══════════════════════════════════════════════════════════════════════
⚠️  REGRAS ANTI-ALUCINAÇÃO — SIGA À RISCA
═══════════════════════════════════════════════════════════════════════

1. **NÚMEROS DA CARTEIRA**: use SÓ os do bloco "═══ CARTEIRA E MERCADO ═══"
   da mensagem. Não invente/chute. Se não estiver lá, diga:
   *"não tenho essa informação no contexto"*.

2. **DADOS MACRO (Selic, CDI, USD, IPCA)**: use SÓ os do bloco. Se não
   estiver, diga *"não tenho esse dado atualizado agora"*.

3. **PREÇOS/COTAÇÕES/DY/P-VP ATUAIS**: NÃO CITE de memória. **O sistema
   vai buscar automaticamente os dados técnicos dos tickers que você
   sugerir** e mostrar ao usuário. Você entrega o NOME + TESE; deixe os
   números do dia por conta do sistema.

4. **AÇÕES/FIIs SUGERIDOS**: só cite tickers que você tem certeza absoluta
   que existem na B3 ou EUA (BBSE3, ITSA4, BBAS3, TAEE11, EGIE3, VIVT3,
   ISAE4, KLBN11, WEGE3, CPFE3, SAPR11, BBDC4, ITUB4, PSSA3, VIVA3,
   RANI3, HGCR11, MXRF11, KNRI11, XPML11, VISC11, HGLG11, MALL11 etc.
   No exterior: VIG, XLU, VYM, SCHD, JEPI, MO, KO, PG, JNJ, BRK.B, VOO, VTI, VXUS).
   **Em dúvida**, NÃO cite ticker — descreva o tipo de empresa.

5. **COERÊNCIA**: releia sua resposta anterior antes da nova.

═══════════════════════════════════════════════════════════════════════

**FORMATO OBRIGATÓRIO DA RESPOSTA (quando o usuário pede sugestões):**

1. **Panorama macro** (1-2 parágrafos — usando dados do bloco).
2. **Leitura da carteira atual** (concentrações, buracos, o que faz sentido).
3. **🎯 3 sugestões principais** — para cada uma:
   - Nome da empresa + ticker
   - Setor
   - **Tese de longo prazo em 4-6 linhas** (por que é boa e por que agora)
   - Papel na carteira (dividendos, defensiva, growth, hedge…)
4. **🔄 2 sugestões reserva** — mesmo formato, para caso o usuário rejeite
   alguma das principais.
5. **Divisão sugerida do aporte de R$ 30.000** entre as 3 principais.
6. **Alertas/riscos** e **perguntas ao usuário**.
7. **BLOCO ESTRUTURADO no fim** (o sistema vai ler para puxar os dados
   técnicos + gráfico). Use EXATAMENTE este formato, com uma linha em
   branco antes e depois:

```tickers
principais: TICKER1, TICKER2, TICKER3
reservas: TICKER4, TICKER5
```

Ex.: `principais: BBSE3, TAEE11, ITSA4` e `reservas: EGIE3, VIVT3`.
NÃO coloque `.SA` — só o ticker limpo. Para US, ticker puro (VIG, XLU).

**Se a pergunta NÃO for sobre sugestões concretas** (só uma dúvida
conceitual/estratégica), pode responder livre — sem o bloco ```tickers.

**Regra CVM**: análise educativa. Você recomenda com convicção baseada em
tese, mas explicita que a decisão é do usuário.

**PORTUGUÊS DO BRASIL. Formato Markdown. Tom firme e direto.**
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

    # Detalhamento por posição (ativo, qtd, valor de mercado, custo).
    from services.investimentos import carregar_snapshot
    posicoes = carregar_snapshot(d)
    if posicoes:
        linhas.append("")
        linhas.append("**Posições individuais:**")
        for p in posicoes[:40]:  # limite pra não estourar contexto
            moeda = p.get("moeda", "BRL")
            vm = float(p.get("valor_mercado") or 0)
            qtd = p.get("quantidade")
            custo = p.get("valor_investido")
            ativo = p.get("ativo", "?")[:60]
            partes = [f"{ativo} ({p.get('classe_ativo','?')})"]
            if qtd:
                partes.append(f"qtd {qtd:g}")
            partes.append(f"mercado {moeda} {vm:,.2f}")
            if custo:
                partes.append(f"custo {moeda} {float(custo):,.2f}")
            linhas.append("- " + " · ".join(partes))
    return "\n".join(linhas)


def montar_dados_macro() -> str:
    """Busca dados de mercado atualizados (Selic/CDI, USD) para injetar no
    contexto e evitar alucinação do modelo em cima de dados velhos."""
    linhas = ["**Dados de mercado (agora):**"]
    try:
        from services.cotacoes import buscar_cdi_anual
        cdi = buscar_cdi_anual()
        linhas.append(f"- **CDI ao ano (BCB, série 4389):** {cdi:.2f}%")
    except Exception:
        linhas.append("- CDI: não disponível agora.")
    try:
        from services.cotacoes import buscar_dolar
        d = buscar_dolar()
        if d:
            linhas.append(f"- **USD/BRL:** R$ {d:.4f}")
    except Exception:
        linhas.append("- USD/BRL: não disponível agora.")
    linhas.append(
        "- Outros dados macro (IPCA acumulado, taxa Fed, PIB): NÃO ESTOU "
        "PASSANDO agora. Se precisar citar, avise que não tem essa informação."
    )
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
    é a lista {role, content} das trocas anteriores (fora o system prompt).

    IMPORTANTE contra alucinação: em TODA mensagem do usuário injetamos um
    bloco '═══ CARTEIRA E MERCADO ═══' com os dados atualizados. Assim o
    modelo nunca precisa "lembrar" números — ele sempre vê o dado autoritativo
    no momento da resposta.
    """
    from core.config import get_anthropic_key
    chave = get_anthropic_key()
    if not chave:
        raise RuntimeError(
            "Chave ANTHROPIC_API_KEY não configurada. Não dá para consultar o assessor."
        )

    # Bloco de dados oficial injetado a cada mensagem (anti-alucinação).
    dados_macro = montar_dados_macro()
    bloco_dados = (
        "═══ CARTEIRA E MERCADO ═══\n"
        "(**Use SOMENTE estes números. Não invente.**)\n\n"
        f"### Carteira atual\n{contexto_carteira}\n\n"
        f"### {dados_macro}\n"
    )
    if valor_investir:
        bloco_dados += f"\n### Valor a alocar agora\n{_brl(valor_investir)} (aporte deste mês).\n"
    bloco_dados += "═══════════════════════════\n\n"

    mensagem_final = bloco_dados + "**Pergunta:** " + nova_mensagem

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
