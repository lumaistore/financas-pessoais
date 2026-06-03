"""Planejamento: reserva de emergência e fluxo de caixa projetado (Fases 9/12).

- Reserva de emergência: quanto a sua reserva (classes líquidas da carteira)
  cobre dos seus gastos médios mensais.
- Fluxo de caixa projetado: quanto você já tem comprometido a pagar nos
  próximos meses (parcelas, financiamentos e tranches de imóveis).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from services.cartao import gasto_total, listar_faturas
from services.compromissos import add_months, total_parcelas_mes
from services.despesas import listar_despesas, total_despesas
from services.investimentos import listar_datas, por_classe

# Classes consideradas "reserva" (alta liquidez, baixo risco).
RESERVA_CLASSES = {"Caixa", "Renda Fixa"}


# ---------------------------------------------------------------------------
# Reserva de emergência
# ---------------------------------------------------------------------------
def reserva_emergencia(data_ref: Optional[date] = None) -> float:
    """Soma das classes líquidas (Caixa + Renda Fixa) no snapshot mais recente."""
    datas = listar_datas()
    if not datas:
        return 0.0
    data_ref = data_ref or datas[0]
    return sum(c["total"] for c in por_classe(data_ref) if c["classe"] in RESERVA_CLASSES)


def _meses_com_gasto() -> List[str]:
    meses = {f["mes_referencia"] for f in listar_faturas() if f.get("mes_referencia")}
    meses |= {d["mes_referencia"] for d in listar_despesas() if d.get("mes_referencia")}
    return sorted(meses)


def gasto_mensal(mes_referencia: str) -> float:
    """Gasto total de um mês: cartão (fatura) + despesas manuais."""
    return gasto_total(mes_referencia) + total_despesas(mes_referencia)


def gasto_medio_mensal() -> float:
    """Média dos gastos dos meses que têm algum gasto registrado."""
    valores = [gasto_mensal(m) for m in _meses_com_gasto()]
    valores = [v for v in valores if v > 0]
    return sum(valores) / len(valores) if valores else 0.0


def reserva_meses() -> dict:
    """Quantos meses de gasto a reserva cobre. {reserva, gasto_medio, meses}."""
    reserva = reserva_emergencia()
    medio = gasto_medio_mensal()
    meses = (reserva / medio) if medio else 0.0
    return {"reserva": reserva, "gasto_medio": medio, "meses": meses}


# ---------------------------------------------------------------------------
# Fluxo de caixa projetado
# ---------------------------------------------------------------------------
def projecao_fluxo(meses: int = 12) -> List[dict]:
    """Saídas já comprometidas (parcelas + financiamentos + imóveis) por mês,
    a partir do mês atual. Retorna [{mes, compromissos}]."""
    hoje = date.today().replace(day=1)
    resultado = []
    for i in range(meses):
        ref = add_months(hoje, i)
        mes_str = ref.strftime("%Y-%m")
        resultado.append({"mes": mes_str, "compromissos": total_parcelas_mes(mes_str)})
    return resultado
