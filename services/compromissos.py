"""Regras de negócio dos compromissos parcelados / financiamentos (Fase 2).

Saldo devedor, próximas parcelas e datas são SEMPRE calculados a partir de
poucos campos cadastrados (valor da parcela, total de parcelas, parcelas pagas
e data/dia de vencimento). Nada de saldo é armazenado.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.cache import cache_leitura, invalida_cache
from core.models import Compromisso, CompromissoParcela, PagamentoCompromisso

TIPOS_PAGAMENTO = ["entrada", "parcela", "seguro", "taxa", "amortização", "outros"]

TIPOS = ["financiamento", "parcelado", "imovel"]

# Valor do imóvel de Carneiros (sem juros) — usado no cálculo de patrimônio.
# Pode ser ajustado pelo usuário via definir_valor_imovel().
VALOR_IMOVEL_CARNEIROS = 693000.0


# ---------------------------------------------------------------------------
# Helpers de data
# ---------------------------------------------------------------------------
def add_months(d: date, n: int) -> date:
    """Soma n meses a uma data, ajustando o dia para o fim do mês quando preciso."""
    total = d.month - 1 + n
    ano = d.year + total // 12
    mes = total % 12 + 1
    # Último dia do mês de destino.
    if mes == 12:
        prox_inicio = date(ano + 1, 1, 1)
    else:
        prox_inicio = date(ano, mes + 1, 1)
    ultimo_dia = (prox_inicio - date.resolution).day
    return date(ano, mes, min(d.day, ultimo_dia))


def _data_parcela(c: Compromisso, numero: int) -> Optional[date]:
    """Data de vencimento da parcela `numero` (1-based)."""
    if c.primeira_data is not None:
        return add_months(c.primeira_data, numero - 1)
    if c.dia_vencimento is not None:
        # Sem data de início: estima a partir do mês atual.
        hoje = date.today()
        try:
            base = date(hoje.year, hoje.month, c.dia_vencimento)
        except ValueError:
            base = date(hoje.year, hoje.month, 28)
        # numero - (parcelas_pagas+1) meses a partir da próxima.
        return add_months(base, numero - (c.parcelas_pagas + 1))
    return None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@invalida_cache
def adicionar_compromisso(
    nome: str,
    valor_parcela: float,
    total_parcelas: int,
    parcelas_pagas: int = 0,
    tipo: str = "parcelado",
    primeira_data: Optional[date] = None,
    dia_vencimento: Optional[int] = None,
) -> int:
    with get_session() as s:
        c = Compromisso(
            nome=nome,
            valor_parcela=valor_parcela,
            total_parcelas=total_parcelas,
            parcelas_pagas=parcelas_pagas,
            tipo=tipo,
            primeira_data=primeira_data,
            dia_vencimento=dia_vencimento,
            ativo=parcelas_pagas < total_parcelas,
        )
        s.add(c)
        s.flush()
        return c.id


@invalida_cache
def registrar_pagamento(compromisso_id: int, quantidade: int = 1) -> None:
    """Marca `quantidade` parcelas como pagas (sem ultrapassar o total)."""
    with get_session() as s:
        c = s.get(Compromisso, compromisso_id)
        if not c:
            return
        c.parcelas_pagas = min(c.total_parcelas, c.parcelas_pagas + quantidade)
        c.ativo = c.parcelas_pagas < c.total_parcelas


@invalida_cache
def definir_parcelas_pagas(compromisso_id: int, parcelas_pagas: int) -> None:
    with get_session() as s:
        c = s.get(Compromisso, compromisso_id)
        if not c:
            return
        c.parcelas_pagas = max(0, min(c.total_parcelas, parcelas_pagas))
        c.ativo = c.parcelas_pagas < c.total_parcelas


@invalida_cache
def excluir_compromisso(compromisso_id: int) -> None:
    with get_session() as s:
        c = s.get(Compromisso, compromisso_id)
        if c:
            s.delete(c)


# ---------------------------------------------------------------------------
# Consultas e cálculos derivados
# ---------------------------------------------------------------------------
def _resumo(c: Compromisso) -> dict:
    if c.tipo == "imovel":
        return _resumo_imovel(c)
    restantes = max(0, c.total_parcelas - c.parcelas_pagas)
    proximo_numero = c.parcelas_pagas + 1 if restantes > 0 else None
    proxima_data = _data_parcela(c, proximo_numero) if proximo_numero else None
    return {
        "id": c.id,
        "nome": c.nome,
        "tipo": c.tipo,
        "valor_parcela": c.valor_parcela,
        "total_parcelas": c.total_parcelas,
        "parcelas_pagas": c.parcelas_pagas,
        "parcelas_restantes": restantes,
        "progresso": c.parcelas_pagas / c.total_parcelas if c.total_parcelas else 0,
        "valor_total": c.valor_parcela * c.total_parcelas,
        "valor_pago": c.valor_parcela * c.parcelas_pagas,
        "saldo_devedor": c.valor_parcela * restantes,
        "proxima_parcela_numero": proximo_numero,
        "proxima_data": proxima_data,
        "ativo": c.ativo,
        "eh_imovel": False,
        "financiamento": 0.0,
    }


def _resumo_imovel(c: Compromisso) -> dict:
    """Resumo de um imóvel: saldo = total do plano - pago, com o 'balão' de
    financiamento acompanhado à parte (não entra no saldo mensal)."""
    total_plano = c.valor_total_plano or 0.0
    pago = c.valor_pago or 0.0
    financiamento = c.valor_financiamento or 0.0
    # Saldo "em dinheiro" devido à construtora até a entrega (exclui o balão).
    saldo_cash = max(0.0, total_plano - financiamento - pago)

    # Próxima parcela em aberto = primeira tranche (não-financiamento) com
    # vencimento >= hoje.
    hoje = date.today()
    futuras = sorted(
        (p for p in c.parcelas if not p.eh_financiamento and p.data_vencimento >= hoje),
        key=lambda p: p.data_vencimento,
    )
    proxima = futuras[0] if futuras else None
    progresso = (pago / total_plano) if total_plano else 0.0
    return {
        "id": c.id,
        "nome": c.nome,
        "tipo": c.tipo,
        "valor_parcela": proxima.valor if proxima else 0.0,
        "total_parcelas": len([p for p in c.parcelas if not p.eh_financiamento]),
        "parcelas_pagas": 0,
        "parcelas_restantes": len(futuras),
        "progresso": progresso,
        "valor_total": total_plano,
        "valor_pago": pago,
        "saldo_devedor": saldo_cash,
        "proxima_parcela_numero": None,
        "proxima_data": proxima.data_vencimento if proxima else None,
        "ativo": c.ativo,
        "eh_imovel": True,
        "financiamento": financiamento,
        "valor_corretagem": c.valor_corretagem or 0.0,
        "data_contrato": c.data_contrato,
        "descricao": c.descricao,
    }


@cache_leitura
def listar_compromissos(apenas_ativos: bool = False) -> List[dict]:
    with get_session() as s:
        stmt = select(Compromisso).order_by(Compromisso.nome)
        compromissos = s.scalars(stmt).all()
        resumos = [_resumo(c) for c in compromissos]
    if apenas_ativos:
        resumos = [r for r in resumos if r["ativo"]]
    return resumos


@cache_leitura
def proximas_parcelas(compromisso_id: int, n: int = 6) -> List[dict]:
    """Lista as próximas `n` parcelas em aberto de um compromisso.

    Para imóveis, lê o cronograma (tranches não-financiamento com vencimento
    a partir de hoje). Para os demais, projeta a partir da parcela uniforme.
    """
    with get_session() as s:
        c = s.get(Compromisso, compromisso_id)
        if not c:
            return []
        if c.tipo == "imovel":
            hoje = date.today()
            futuras = sorted(
                (p for p in c.parcelas if not p.eh_financiamento and p.data_vencimento >= hoje),
                key=lambda p: p.data_vencimento,
            )
            return [
                {"numero": None, "tipo": p.tipo, "data": p.data_vencimento, "valor": p.valor}
                for p in futuras[:n]
            ]
        resultado = []
        for numero in range(c.parcelas_pagas + 1, min(c.total_parcelas, c.parcelas_pagas + n) + 1):
            resultado.append(
                {
                    "numero": numero,
                    "tipo": "MENSAL",
                    "data": _data_parcela(c, numero),
                    "valor": c.valor_parcela,
                }
            )
        return resultado


@cache_leitura
def total_parcelas_mes(mes_referencia: str) -> float:
    """Soma das parcelas (de compromissos ativos) que vencem no mês 'AAAA-MM'.

    Inclui as tranches de imóvel (exceto o balão de financiamento) que caem
    no mês de referência.
    """
    total = 0.0
    for r in listar_compromissos(apenas_ativos=True):
        c_id = r["id"]
        n = max(r["parcelas_restantes"] or 1, 1)
        for p in proximas_parcelas(c_id, n=n):
            if p["data"] and p["data"].strftime("%Y-%m") == mes_referencia:
                total += p["valor"]
    return total


@cache_leitura
def total_saldo_devedor() -> float:
    return sum(r["saldo_devedor"] for r in listar_compromissos(apenas_ativos=True))


@cache_leitura
def total_financiamento_a_contratar() -> float:
    """Soma dos 'balões' de financiamento ainda a contratar (imóveis ativos)."""
    return sum(r.get("financiamento", 0.0) for r in listar_compromissos(apenas_ativos=True))


@cache_leitura
def contar_ativos() -> int:
    return len(listar_compromissos(apenas_ativos=True))


# ---------------------------------------------------------------------------
# Imóveis: patrimônio (só o que já foi pago) + quanto falta (sem juros)
# ---------------------------------------------------------------------------
def _eh_imovel_compromisso(c: Compromisso) -> bool:
    """SP são tipo 'imovel'; Carneiros é 'financiamento' mas também é imóvel."""
    nome = (c.nome or "").lower()
    return c.tipo == "imovel" or "carneiros" in nome or "sfh" in nome


@invalida_cache
def definir_valor_imovel(compromisso_id: int, valor: Optional[float]) -> None:
    """Grava o valor do imóvel (sem juros) em valor_total_plano — usado para
    Carneiros, onde só temos as parcelas com juros cadastradas."""
    with get_session() as s:
        c = s.get(Compromisso, compromisso_id)
        if c:
            c.valor_total_plano = float(valor) if valor else None


@cache_leitura
def resumo_imoveis() -> dict:
    """Para o Painel de patrimônio:
    - total_pago: soma do que JÁ FOI PAGO nos imóveis (SP + Carneiros),
      sem juros/parcelas futuras.
    - sp_falta: quanto falta em parcelas nos imóveis de SP (até a entrega,
      exclui o balão de financiamento).
    - carneiros_falta: valor do imóvel de Carneiros − o que já foi pago
      (sem juros). Requer o valor do imóvel cadastrado.
    """
    total_pago = sp_falta = carn_falta = 0.0
    carn_sem_valor = False
    with get_session() as s:
        comps = s.scalars(
            select(Compromisso).where(Compromisso.ativo.is_(True))
        ).all()
        ids = [(c.id, c.tipo, c.nome, c.valor_pago, c.valor_total_plano,
                c.valor_financiamento, _eh_imovel_compromisso(c)) for c in comps]

    for cid, tipo, nome, valor_pago, total_plano, financ, eh_imovel in ids:
        if not eh_imovel:
            continue
        pago = (valor_pago or 0.0) + total_pago_compromisso(cid)
        total_pago += pago
        if tipo == "imovel":
            # Falta em parcelas até a entrega (exclui o balão de financiamento).
            sp_falta += max(0.0, (total_plano or 0.0) - (financ or 0.0) - pago)
        else:
            # Carneiros: valor do imóvel (sem juros) − pago.
            valor_imovel = total_plano or (
                VALOR_IMOVEL_CARNEIROS if "carneiros" in (nome or "").lower() else None
            )
            if valor_imovel:
                carn_falta += max(0.0, valor_imovel - pago)
            else:
                carn_sem_valor = True

    return {
        "total_pago": total_pago,
        "sp_falta": sp_falta,
        "carneiros_falta": carn_falta,
        "carneiros_sem_valor": carn_sem_valor,
        "falta_total": sp_falta + carn_falta,
    }


# ---------------------------------------------------------------------------
# Imóveis (plano de pagamento heterogêneo)
# ---------------------------------------------------------------------------
@invalida_cache
def adicionar_imovel(
    nome: str,
    data_contrato: Optional[date],
    valor_total_plano: float,
    valor_pago: float,
    valor_financiamento: float,
    parcelas: List[dict],
    valor_corretagem: Optional[float] = None,
    descricao: Optional[str] = None,
) -> int:
    """Cria um compromisso do tipo imóvel com seu cronograma.

    `parcelas`: lista de {tipo, data, valor, eh_financiamento}.
    """
    with get_session() as s:
        c = Compromisso(
            nome=nome,
            tipo="imovel",
            valor_parcela=0.0,
            total_parcelas=0,
            parcelas_pagas=0,
            valor_total_plano=valor_total_plano,
            valor_pago=valor_pago,
            valor_financiamento=valor_financiamento,
            valor_corretagem=valor_corretagem,
            data_contrato=data_contrato,
            descricao=descricao,
            ativo=valor_pago < (valor_total_plano - (valor_financiamento or 0.0)),
        )
        s.add(c)
        s.flush()
        for p in parcelas:
            s.add(
                CompromissoParcela(
                    compromisso_id=c.id,
                    tipo=p["tipo"],
                    data_vencimento=p["data"],
                    valor=float(p["valor"]),
                    eh_financiamento=bool(p.get("eh_financiamento", False)),
                )
            )
        return c.id


def _expandir_mensais(tipo: str, primeira: date, qtd: int, valor: float, passo_meses: int = 1) -> List[dict]:
    """Gera `qtd` parcelas a partir de `primeira`, espaçadas por `passo_meses`."""
    return [
        {"tipo": tipo, "data": add_months(primeira, i * passo_meses), "valor": valor, "eh_financiamento": False}
        for i in range(qtd)
    ]


@invalida_cache
def seed_imoveis_sp() -> int:
    """Carga de imóveis a partir de contratos.

    Privacidade: nenhum dado real de imóvel/contrato fica no código. Os imóveis
    reais ficam só no banco (local ou nuvem), nunca versionados. Para cadastrar
    um imóvel do zero, use a tela de Financiamentos (ou a função
    `adicionar_imovel` com o cronograma do seu contrato). Retorna 0 aqui.
    """
    return 0


# ---------------------------------------------------------------------------
# Pagamentos avulsos (lançados manualmente, com comprovante) — útil para
# financiamentos em evolução de obra (valor variável mês a mês).
# ---------------------------------------------------------------------------
@invalida_cache
def adicionar_pagamento(
    compromisso_id: int,
    data_: date,
    valor: float,
    tipo: str = "parcela",
    descricao: Optional[str] = None,
    comprovante_nome: Optional[str] = None,
    comprovante_dados: Optional[bytes] = None,
) -> int:
    with get_session() as s:
        p = PagamentoCompromisso(
            compromisso_id=compromisso_id,
            data=data_,
            valor=float(valor),
            tipo=(tipo if tipo in TIPOS_PAGAMENTO else "outros"),
            descricao=(descricao or "").strip() or None,
            comprovante_nome=comprovante_nome,
            comprovante_dados=comprovante_dados,
        )
        s.add(p)
        s.flush()
        return p.id


@cache_leitura
def listar_pagamentos(compromisso_id: int) -> List[dict]:
    with get_session() as s:
        rs = s.scalars(
            select(PagamentoCompromisso)
            .where(PagamentoCompromisso.compromisso_id == compromisso_id)
            .order_by(PagamentoCompromisso.data.desc())
        ).all()
        return [
            {
                "id": p.id,
                "data": p.data,
                "valor": p.valor,
                "tipo": p.tipo,
                "descricao": p.descricao,
                "tem_comprovante": p.comprovante_nome is not None,
                "comprovante_nome": p.comprovante_nome,
            }
            for p in rs
        ]


@invalida_cache
def excluir_pagamento(pagamento_id: int) -> None:
    with get_session() as s:
        p = s.get(PagamentoCompromisso, pagamento_id)
        if p:
            s.delete(p)


def comprovante_pagamento(pagamento_id: int):
    with get_session() as s:
        p = s.get(PagamentoCompromisso, pagamento_id)
        if not p or p.comprovante_dados is None:
            return None, None
        return p.comprovante_nome, p.comprovante_dados


@cache_leitura
def total_pago_compromisso(compromisso_id: int) -> float:
    return sum(p["valor"] for p in listar_pagamentos(compromisso_id))


# ---------------------------------------------------------------------------
# Cadastro do imóvel/financiamento de Carneiros (Caixa SFH)
# ---------------------------------------------------------------------------
@invalida_cache
def cadastrar_carneiros() -> Optional[int]:
    """Cria o compromisso do Apto Carneiros (Caixa SFH) se ainda não existir.
    Retorna o id criado ou None se já existia. Os pagamentos reais são
    lançados via `adicionar_pagamento`."""
    nome = "Apto Carneiros (Caixa SFH)"
    existentes = {r["nome"] for r in listar_compromissos()}
    if nome in existentes:
        return None
    # ~30 anos de financiamento; encargo médio estimado da fase de obra.
    cid = adicionar_compromisso(
        nome=nome,
        valor_parcela=6401.12,
        total_parcelas=360,
        parcelas_pagas=0,
        tipo="financiamento",
        dia_vencimento=10,
    )
    # Grava o valor do imóvel (sem juros) para o cálculo de patrimônio.
    definir_valor_imovel(cid, VALOR_IMOVEL_CARNEIROS)
    return cid
