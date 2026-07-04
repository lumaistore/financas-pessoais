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
# Modelo Receita removido na reforma. Ver Movimentacao (tipo='receita').


# ---------------------------------------------------------------------------
# CARTÃO DE CRÉDITO  (Fase 3)
# ---------------------------------------------------------------------------
class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    cor: Mapped[Optional[str]] = mapped_column(String)


# Modelo Orcamento removido na reforma.


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
    # Data em que o reembolso LUMAI foi efetivamente recebido. Quando
    # preenchido, o item sai do relatório de "a reembolsar".
    reembolsado_em: Mapped[Optional[date]] = mapped_column(Date)

    fatura: Mapped["Fatura"] = relationship(back_populates="transacoes")
    categoria: Mapped[Optional["Categoria"]] = relationship()


# Modelo DespesaManual removido na reforma — agora tudo é Movimentacao.


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


class PagamentoCompromisso(Base):
    """Pagamento real lançado contra um compromisso (financiamento/imóvel)
    — útil para fase de evolução de obra (valores variáveis) ou quando o
    usuário quer o histórico com comprovantes."""

    __tablename__ = "pagamentos_compromisso"

    id: Mapped[int] = mapped_column(primary_key=True)
    compromisso_id: Mapped[int] = mapped_column(ForeignKey("compromissos.id"))
    data: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="parcela")  # entrada / parcela / seguro / taxa / outros
    descricao: Mapped[Optional[str]] = mapped_column(String)
    comprovante_nome: Mapped[Optional[str]] = mapped_column(String)
    comprovante_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    compromisso: Mapped["Compromisso"] = relationship()


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


class ConsultaAssessor(Base):
    """Sessão de conversa com o 'assessor de investimentos' (IA). Guarda o
    valor consultado, o snapshot da carteira e a conversa completa em JSON
    (perguntas + respostas) para retomar depois."""

    __tablename__ = "consultas_assessor"

    id: Mapped[int] = mapped_column(primary_key=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    valor_investir: Mapped[Optional[float]] = mapped_column(Float)
    contexto_carteira: Mapped[Optional[str]] = mapped_column(String)
    conversa_json: Mapped[Optional[str]] = mapped_column(String)  # lista de {role, content}
    titulo: Mapped[Optional[str]] = mapped_column(String)  # resumo curto


class Exame(Base):
    """Resultado de exame médico anexado pelo usuário (PDF) com texto
    extraído para busca e análise educativa por IA. NÃO substitui consulta
    com médico — o disclaimer aparece em toda análise."""

    __tablename__ = "exames"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    categoria: Mapped[str] = mapped_column(String, default="Outros")
    paciente: Mapped[str] = mapped_column(String, nullable=False)
    laboratorio: Mapped[Optional[str]] = mapped_column(String)
    observacao: Mapped[Optional[str]] = mapped_column(String)
    arquivo_nome: Mapped[Optional[str]] = mapped_column(String)
    arquivo_dados: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True)
    texto_extraido: Mapped[Optional[str]] = mapped_column(String, deferred=True)
    analise_ia: Mapped[Optional[str]] = mapped_column(String, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ContaFinanceira(Base):
    """Conta bancária ou de aplicação do usuário. Usada para detectar
    transferências entre próprias contas (não são despesa/receita reais) e
    aplicações (vão para carteira de investimentos, não são despesa)."""

    __tablename__ = "contas_financeiras"

    id: Mapped[int] = mapped_column(primary_key=True)
    apelido: Mapped[str] = mapped_column(String, nullable=False)  # "Itaú CC", "C6 CC", "BTG Investimento"
    banco: Mapped[Optional[str]] = mapped_column(String)  # "Itaú", "C6", "BTG"
    tipo: Mapped[str] = mapped_column(String, default="corrente")  # corrente / poupança / aplicação
    # Palavras-chave que aparecem em descrições de extrato para identificar
    # essa conta (nome do titular, razão social, apelidos). Separadas por
    # vírgula. Ex.: "LUCAS GUEIROS,GUEIROS DE FREITAS,LGFAM"
    identificadores: Mapped[Optional[str]] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Movimentacao(Base):
    """Entrada ou saída financeira detectada automaticamente do extrato,
    lançada manualmente, ou vinda de fatura de cartão. Substitui Receita +
    DespesaManual do modelo antigo."""

    __tablename__ = "movimentacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)  # positivo sempre; direção vem do tipo

    # Classificação principal — direciona os relatórios do painel.
    # "receita"           → entrou dinheiro real (salário, LUMAI, venda)
    # "despesa"           → saiu dinheiro real
    # "transferencia"     → transferência entre contas do próprio usuário (ignorada em totais)
    # "aplicacao"         → PIX/TED para conta de aplicação (BTG etc.); vai para Investimentos
    # "resgate"           → volta de aplicação (crédito de resgate)
    tipo: Mapped[str] = mapped_column(String, default="despesa")

    # Conta em que a movimentação ocorreu (opcional; útil para ligar ao extrato)
    conta_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contas_financeiras.id"))
    # Se for transferência/aplicação, aqui vai a conta destino identificada.
    conta_destino_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contas_financeiras.id"))

    forma: Mapped[Optional[str]] = mapped_column(String)  # pix/boleto/débito/cartão/dinheiro/caju
    categoria_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categorias.id"))
    mes_referencia: Mapped[Optional[str]] = mapped_column(String)  # AAAA-MM
    observacao: Mapped[Optional[str]] = mapped_column(String)

    # Marcas de reembolso LUMAI (herança do modelo antigo).
    lumai: Mapped[bool] = mapped_column(Boolean, default=False)
    reembolsado_em: Mapped[Optional[date]] = mapped_column(Date)

    # Rastreabilidade: se veio de extrato ou fatura de cartão.
    origem: Mapped[Optional[str]] = mapped_column(String)  # "extrato:C6", "fatura:itau_202605", "manual"

    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    conta: Mapped[Optional["ContaFinanceira"]] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped[Optional["ContaFinanceira"]] = relationship(foreign_keys=[conta_destino_id])
    categoria: Mapped[Optional["Categoria"]] = relationship()


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


class CompraInvestimento(Base):
    """Histórico de compras/aportes. Cada compra também gera uma Movimentacao
    do tipo 'aplicacao' (link em movimentacao_id), para contar no fluxo do mês."""

    __tablename__ = "compras_investimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    ativo: Mapped[str] = mapped_column(String, nullable=False)
    ticker: Mapped[Optional[str]] = mapped_column(String)
    classe: Mapped[Optional[str]] = mapped_column(String)
    quantidade: Mapped[Optional[float]] = mapped_column(Float)
    preco_unitario: Mapped[Optional[float]] = mapped_column(Float)
    valor_total: Mapped[float] = mapped_column(Float, nullable=False)
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    observacao: Mapped[Optional[str]] = mapped_column(String)
    movimentacao_id: Mapped[Optional[int]] = mapped_column(Integer)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AlertaDispensado(Base):
    """Alertas padrão que o usuário dispensou (por chave estável)."""

    __tablename__ = "alertas_dispensados"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AlertaInteligente(Base):
    """Alerta/insight gerado por IA a partir dos dados da conta."""

    __tablename__ = "alertas_inteligentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String, nullable=False)
    descricao: Mapped[Optional[str]] = mapped_column(String)
    prioridade: Mapped[int] = mapped_column(Integer, default=2)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Provento(Base):
    """Provento recebido (dividendo / JCP / rendimento de FII / amortização),
    normalmente lido de um print do app da corretora via IA de visão."""

    __tablename__ = "proventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="dividendo")  # dividendo/jcp/rendimento/amortizacao
    valor: Mapped[float] = mapped_column(Float, nullable=False)  # na moeda original
    moeda: Mapped[str] = mapped_column(String, default="BRL")     # BRL / USD
    cotacao: Mapped[float] = mapped_column(Float, default=1.0)    # USD→BRL (1.0 se BRL)
    imposto: Mapped[Optional[float]] = mapped_column(Float)       # imposto retido (moeda original)
    observacao: Mapped[Optional[str]] = mapped_column(String)
    movimentacao_id: Mapped[Optional[int]] = mapped_column(Integer)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
