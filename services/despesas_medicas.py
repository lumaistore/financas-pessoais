"""Despesas médicas dedutíveis no IR.

A Receita Federal aceita como dedução despesas com saúde do contribuinte e
seus dependentes desde que:
- O prestador esteja identificado (CPF/CNPJ);
- O paciente esteja identificado;
- Só é dedutível o valor NÃO reembolsado pelo plano de saúde;
- Medicamentos comprados em farmácia NÃO são dedutíveis (exceto quando
  incluídos na conta hospitalar de uma internação).
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy import select

from core.db import get_session
from core.models import DespesaMedica

# Categorias aceitas pelo IR. "Medicamento" fica como aviso (ver docstring).
TIPOS = [
    "Plano de saúde",
    "Consulta médica",
    "Exame",
    "Hospital / Internação",
    "Cirurgia",
    "Dentista",
    "Psicólogo",
    "Psiquiatra",
    "Fisioterapeuta",
    "Fonoaudiólogo",
    "Aparelho ortopédico / prótese",
    "Aparelho auditivo / visual",
    "Medicamento (em internação)",
    "Outros",
]

# Tipos NÃO dedutíveis avisados ao usuário.
NAO_DEDUTIVEIS = {"Medicamento (farmácia)"}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def adicionar(
    data_: date,
    tipo: str,
    paciente: str,
    prestador: str,
    cnpj_cpf: Optional[str],
    valor_pago: float,
    valor_reembolsado: float = 0.0,
    observacao: Optional[str] = None,
    comprovante_nome: Optional[str] = None,
    comprovante_dados: Optional[bytes] = None,
) -> int:
    with get_session() as s:
        d = DespesaMedica(
            data=data_,
            tipo=tipo or "Outros",
            paciente=paciente.strip(),
            prestador=prestador.strip(),
            cnpj_cpf=(cnpj_cpf or "").strip() or None,
            valor_pago=float(valor_pago),
            valor_reembolsado=float(valor_reembolsado or 0.0),
            observacao=(observacao or "").strip() or None,
            comprovante_nome=comprovante_nome,
            comprovante_dados=comprovante_dados,
        )
        s.add(d)
        s.flush()
        return d.id


def listar(ano: Optional[int] = None) -> List[dict]:
    with get_session() as s:
        rs = s.scalars(select(DespesaMedica).order_by(DespesaMedica.data.desc())).all()
        out = []
        for r in rs:
            if ano is not None and r.data.year != ano:
                continue
            dedutivel = float(r.valor_pago) - float(r.valor_reembolsado or 0.0)
            out.append({
                "id": r.id,
                "data": r.data,
                "tipo": r.tipo,
                "paciente": r.paciente,
                "prestador": r.prestador,
                "cnpj_cpf": r.cnpj_cpf,
                "valor_pago": r.valor_pago,
                "valor_reembolsado": r.valor_reembolsado or 0.0,
                "dedutivel": max(dedutivel, 0.0),
                "observacao": r.observacao,
                "tem_comprovante": r.comprovante_nome is not None,
                "comprovante_nome": r.comprovante_nome,
                "ano": r.data.year,
            })
        return out


def atualizar(
    despesa_id: int,
    data_: date,
    tipo: str,
    paciente: str,
    prestador: str,
    cnpj_cpf: Optional[str],
    valor_pago: float,
    valor_reembolsado: float,
    observacao: Optional[str],
) -> None:
    with get_session() as s:
        d = s.get(DespesaMedica, despesa_id)
        if not d:
            return
        d.data = data_
        d.tipo = tipo or "Outros"
        d.paciente = paciente.strip()
        d.prestador = prestador.strip()
        d.cnpj_cpf = (cnpj_cpf or "").strip() or None
        d.valor_pago = float(valor_pago)
        d.valor_reembolsado = float(valor_reembolsado or 0.0)
        d.observacao = (observacao or "").strip() or None


def excluir(despesa_id: int) -> None:
    with get_session() as s:
        d = s.get(DespesaMedica, despesa_id)
        if d:
            s.delete(d)


def comprovante(despesa_id: int):
    with get_session() as s:
        d = s.get(DespesaMedica, despesa_id)
        if not d or d.comprovante_dados is None:
            return None, None
        return d.comprovante_nome, d.comprovante_dados


def anexar_comprovante(despesa_id: int, nome: str, dados: bytes) -> None:
    with get_session() as s:
        d = s.get(DespesaMedica, despesa_id)
        if d:
            d.comprovante_nome = nome
            d.comprovante_dados = dados


# ---------------------------------------------------------------------------
# Agregações
# ---------------------------------------------------------------------------
def total_dedutivel(ano: int) -> float:
    return sum(r["dedutivel"] for r in listar(ano))


def total_pago(ano: int) -> float:
    return sum(r["valor_pago"] for r in listar(ano))


def total_reembolsado(ano: int) -> float:
    return sum(r["valor_reembolsado"] for r in listar(ano))


def por_tipo(ano: int) -> List[dict]:
    acc: dict = {}
    for r in listar(ano):
        a = acc.setdefault(r["tipo"], {"tipo": r["tipo"], "qtd": 0, "pago": 0.0, "dedutivel": 0.0})
        a["qtd"] += 1
        a["pago"] += r["valor_pago"]
        a["dedutivel"] += r["dedutivel"]
    return sorted(acc.values(), key=lambda x: x["dedutivel"], reverse=True)


def por_paciente(ano: int) -> List[dict]:
    acc: dict = {}
    for r in listar(ano):
        a = acc.setdefault(r["paciente"], {"paciente": r["paciente"], "qtd": 0, "dedutivel": 0.0})
        a["qtd"] += 1
        a["dedutivel"] += r["dedutivel"]
    return sorted(acc.values(), key=lambda x: x["dedutivel"], reverse=True)


def pendentes_cnpj(ano: int) -> List[dict]:
    """Despesas SEM CPF/CNPJ do prestador — IR exige preencher antes do envio."""
    return [r for r in listar(ano) if not r["cnpj_cpf"]]


# ---------------------------------------------------------------------------
# Relatório anual (Excel pronto para o IR)
# ---------------------------------------------------------------------------
def gerar_excel_ir(ano: int) -> bytes:
    """Gera um .xlsx com todas as despesas do ano + resumos, pronto para
    declarar/conferir no IR."""
    despesas = listar(ano)
    cols = ["data", "tipo", "paciente", "prestador", "cnpj_cpf",
            "valor_pago", "valor_reembolsado", "dedutivel",
            "tem_comprovante", "observacao"]
    df = pd.DataFrame(despesas)
    if df.empty:
        df = pd.DataFrame(columns=cols)
    df = df[cols]
    df.columns = ["Data", "Tipo", "Paciente", "Prestador", "CNPJ/CPF",
                  "Valor pago (R$)", "Reembolsado (R$)", "Dedutível (R$)",
                  "Comprovante?", "Observação"]
    if "Data" in df and not df.empty:
        df["Data"] = df["Data"].apply(lambda d: d.strftime("%d/%m/%Y"))
        df["Comprovante?"] = df["Comprovante?"].map({True: "Sim", False: "Não"})

    df_tipo = pd.DataFrame(por_tipo(ano))
    if not df_tipo.empty:
        df_tipo = df_tipo[["tipo", "qtd", "pago", "dedutivel"]]
        df_tipo.columns = ["Tipo", "Qtd.", "Total pago (R$)", "Dedutível (R$)"]

    df_pac = pd.DataFrame(por_paciente(ano))
    if not df_pac.empty:
        df_pac.columns = ["Paciente", "Qtd.", "Dedutível (R$)"]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Despesas", startrow=2)
        ws = writer.sheets["Despesas"]
        ws["A1"] = f"Despesas Médicas {ano} — gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ws["A2"] = f"Total dedutível (R$): {total_dedutivel(ano):,.2f}"
        for col, w in {"A": 12, "B": 22, "C": 28, "D": 32, "E": 20,
                       "F": 14, "G": 14, "H": 14, "I": 13, "J": 30}.items():
            ws.column_dimensions[col].width = w
        if not df_tipo.empty:
            df_tipo.to_excel(writer, index=False, sheet_name="Por tipo")
        if not df_pac.empty:
            df_pac.to_excel(writer, index=False, sheet_name="Por paciente")
    return buffer.getvalue()
