"""Modelo de dados (SQLAlchemy ORM).

Todas as tabelas do sistema são definidas aqui. A Fase 1 usa diretamente
apenas Receita, mas o schema completo já fica criado para as fases seguintes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Instituicao(Base):
    __tablename__ = "instituicoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[Optional[str]] = mapped_column(String)  # banco / corretora


# ---------------------------------------------------------------------------
# RECEITAS  (Fase 1)
# ---------------------------------------------------------------------------
class Receita(Base):
    __tablename__ = "receitas"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    fonte: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="outros")  # salario / outros
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    descricao: Mapped[Optional[str]] = mapped_column(String)


# ---------------------------------------------------------------------------
# CARTÃO DE CRÉDITO  (Fase 3)
# ---------------------------------------------------------------------------
class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    cor: Mapped[Optional[str]] = mapped_column(String)


class Orcamento(Base):
    """Meta de gasto mensal por categoria (teto). Usada para alertas no painel."""

    __tablename__ = "orcamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), unique=True)
    limite_mensal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    categoria: Mapped["Categoria"] = relationship()


class Fatura(Base):
    __tablename__ = "faturas"

    id: Mapped[int] = mapped_column(primary_key=True)
    instituicao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("instituicoes.id"))
    banco: Mapped[Optional[str]] = mapped_column(String)
    mes_referencia: Mapped[Optional[str]] = mapped_column(String)  # AAAA-MM
    data_importacao: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    arquivo: Mapped[Optional[str]] = mapped_column(String)

    # Fechamento/pagamento da fatura (validador). Anexa-se o comprovante e a
    # fatura é confirmada como "fechada" — o sistema checa se o valor pago bate
    # com o total da fatura.
    paga: Mapped[bool] = mapped_column(Boolean, default=False)
    data_pagamento: Mapped[Optional[date]] = mapped_column(Date)
    valor_pago: Mapped[Optional[float]] = mapped_column(Float)
    comprovante_nome: Mapped[Optional[str]] = mapped_column(String)
    # deferred: só carrega o arquivo quando explicitamente acessado (download).
    comprovante_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)

    transacoes: Mapped[List["TransacaoCartao"]] = relationship(
        back_populates="fatura", cascade="all, delete-orphan"
    )


class TransacaoCartao(Base):
    __tablename__ = "transacoes_cartao"

    id: Mapped[int] = mapped_column(primary_key=True)
    fatura_id: Mapped[int] = mapped_column(ForeignKey("faturas.id"))
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    categoria_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categorias.id"))
    revisado: Mapped[bool] = mapped_column(Boolean, default=False)
    # Marca "LUMAI": despesa da empresa a ser reembolsada para o usuário.
    lumai: Mapped[bool] = mapped_column(Boolean, default=False)

    fatura: Mapped["Fatura"] = relationship(back_populates="transacoes")
    categoria: Mapped[Optional["Categoria"]] = relationship()


class DespesaManual(Base):
    """Gasto que não vem de fatura de cartão: PIX, boleto, débito, dinheiro,
    Caju (vale), etc. Lançado manualmente pelo usuário."""

    __tablename__ = "despesas_manuais"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    forma: Mapped[str] = mapped_column(String, default="pix")  # pix/boleto/débito/dinheiro/caju/outros
    categoria_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categorias.id"))
    mes_referencia: Mapped[Optional[str]] = mapped_column(String)  # AAAA-MM
    lumai: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    categoria: Mapped[Optional["Categoria"]] = relationship()


# ---------------------------------------------------------------------------
# PARCELAMENTOS / FINANCIAMENTOS  (Fase 2)
# ---------------------------------------------------------------------------
class Compromisso(Base):
    __tablename__ = "compromissos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="parcelado")  # financiamento / parcelado / imovel
    valor_parcela: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_parcelas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parcelas_pagas: Mapped[int] = mapped_column(Integer, default=0)
    primeira_data: Mapped[Optional[date]] = mapped_column(Date)
    dia_vencimento: Mapped[Optional[int]] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Campos usados apenas por compromissos do tipo "imovel" (plano de pagamento
    # heterogêneo). O cronograma fica em CompromissoParcela; o saldo devedor é
    # calculado por (valor_total_plano - valor_pago), e o "balão" de
    # financiamento é acompanhado à parte (valor_financiamento).
    valor_total_plano: Mapped[Optional[float]] = mapped_column(Float)
    valor_pago: Mapped[Optional[float]] = mapped_column(Float)
    valor_financiamento: Mapped[Optional[float]] = mapped_column(Float)
    valor_corretagem: Mapped[Optional[float]] = mapped_column(Float)
    data_contrato: Mapped[Optional[date]] = mapped_column(Date)
    descricao: Mapped[Optional[str]] = mapped_column(String)

    parcelas: Mapped[List["CompromissoParcela"]] = relationship(
        back_populates="compromisso", cascade="all, delete-orphan"
    )


class CompromissoParcela(Base):
    """Tranche do cronograma de um compromisso do tipo 'imovel'."""

    __tablename__ = "compromisso_parcelas"

    id: Mapped[int] = mapped_column(primary_key=True)
    compromisso_id: Mapped[int] = mapped_column(ForeignKey("compromissos.id"))
    tipo: Mapped[str] = mapped_column(String, nullable=False)  # ATO / SINAL / ÚNICA / MENSAL / ANUAL / FINANCIAMENTO
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    eh_financiamento: Mapped[bool] = mapped_column(Boolean, default=False)

    compromisso: Mapped["Compromisso"] = relationship(back_populates="parcelas")


# ---------------------------------------------------------------------------
# INVESTIMENTOS  (Fase 4)
# ---------------------------------------------------------------------------
class InvestimentoSnapshot(Base):
    __tablename__ = "investimento_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    instituicao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("instituicoes.id"))
    ativo: Mapped[str] = mapped_column(String, nullable=False)
    classe_ativo: Mapped[Optional[str]] = mapped_column(String)
    quantidade: Mapped[Optional[float]] = mapped_column(Float)
    preco_unitario: Mapped[Optional[float]] = mapped_column(Float)
    valor_mercado: Mapped[float] = mapped_column(Float, nullable=False)
    # Moeda em que valor_mercado/valor_investido estão expressos (BRL ou USD).
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    # Cotação aplicada para converter a moeda em BRL (1.0 para ativos em BRL).
    cotacao: Mapped[float] = mapped_column(Float, default=1.0)
    # Custo de aquisição, quando conhecido — usado para calcular o rendimento.
    valor_investido: Mapped[Optional[float]] = mapped_column(Float)
    origem_arquivo: Mapped[Optional[str]] = mapped_column(String)
    # Cotação automática (Fase 13). Ticker de bolsa (ex.: BBAS3, VIG) para buscar
    # preço; ou índice de renda fixa (CDI/PREFIXADO) com taxa e data de aplicação
    # para estimar o valor por carrego.
    ticker: Mapped[Optional[str]] = mapped_column(String)
    indexador: Mapped[Optional[str]] = mapped_column(String)  # CDI / PREFIXADO / IPCA
    taxa_indice: Mapped[Optional[float]] = mapped_column(Float)  # ex.: 102 (% do CDI)
    data_aplicacao: Mapped[Optional[date]] = mapped_column(Date)


class CarteiraHistorico(Base):
    """Valor total da carteira (BRL) a cada atualização de cotações — base do
    filtro de ganho/perda por período e do gráfico intradiário (Fase 13)."""

    __tablename__ = "carteira_historico"

    id: Mapped[int] = mapped_column(primary_key=True)
    momento: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    total_brl: Mapped[float] = mapped_column(Float, nullable=False)


class DespesaMedica(Base):
    """Despesa médica dedutível no IR. Cada lançamento guarda os dados
    exigidos pela Receita: CPF/CNPJ do prestador, nome do paciente e valor
    efetivamente dedutível (pago − reembolsado pelo plano)."""

    __tablename__ = "despesas_medicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="consulta")
    paciente: Mapped[str] = mapped_column(String, nullable=False)
    prestador: Mapped[str] = mapped_column(String, nullable=False)
    cnpj_cpf: Mapped[Optional[str]] = mapped_column(String)
    valor_pago: Mapped[float] = mapped_column(Float, nullable=False)
    valor_reembolsado: Mapped[float] = mapped_column(Float, default=0.0)
    observacao: Mapped[Optional[str]] = mapped_column(String)
    comprovante_nome: Mapped[Optional[str]] = mapped_column(String)
    comprovante_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PerfilUsuario(Base):
    """Dados do usuário reutilizados em formulários (paciente padrão, etc.)."""

    __tablename__ = "perfil_usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[Optional[str]] = mapped_column(String)
    cpf: Mapped[Optional[str]] = mapped_column(String)
    # Lista de dependentes (separados por vírgula), para sugerir em pacientes.
    dependentes: Mapped[Optional[str]] = mapped_column(String)


class RetiradaLucroConfig(Base):
    """Dados fixos do recibo de distribuição de lucros (singleton)."""

    __tablename__ = "retirada_lucro_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa: Mapped[Optional[str]] = mapped_column(String)
    cnpj: Mapped[Optional[str]] = mapped_column(String)
    beneficiario: Mapped[Optional[str]] = mapped_column(String)
    cpf: Mapped[Optional[str]] = mapped_column(String)
    cidade: Mapped[Optional[str]] = mapped_column(String)


class RetiradaLucro(Base):
    """Uma retirada/distribuição de lucros, com o recibo (gerado ou anexado)."""

    __tablename__ = "retirada_lucros"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    observacao: Mapped[Optional[str]] = mapped_column(String)
    # Recibo gerado pelo app (não assinado).
    arquivo_nome: Mapped[Optional[str]] = mapped_column(String)
    arquivo_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)
    # Versão assinada (devolvida pelo usuário) ou recibo antigo importado.
    assinado: Mapped[bool] = mapped_column(Boolean, default=False)
    assinado_nome: Mapped[Optional[str]] = mapped_column(String)
    assinado_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class InvestimentoMovimento(Base):
    __tablename__ = "investimento_movimentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    instituicao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("instituicoes.id"))
    ativo: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)  # compra / venda / provento
    quantidade: Mapped[Optional[float]] = mapped_column(Float)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    origem_arquivo: Mapped[Optional[str]] = mapped_column(String)
