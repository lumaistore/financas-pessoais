"""Exames médicos — armazenamento, leitura automática, busca e análise
educativa por IA.

⚠️ A análise é educativa e nunca diagnóstico. Sempre consultar médico.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import Exame


CATEGORIAS = [
    "Sangue",
    "Urina",
    "Imagem",
    "Cardiologia",
    "Gastroenterologia",
    "Endocrinologia",
    "Genético",
    "Anatomopatológico",
    "Microbiologia",
    "Outros",
]


# Palavras-chave usadas para inferir a categoria a partir do texto do laudo.
PALAVRAS_CATEGORIA = [
    ("Sangue", ["hemograma", "leucograma", "plaqueta", "hematócrito",
                "hematocrito", "hemoglobin", "vcm", "hcm", "chcm",
                "colesterol", "triglicéri", "triglice", "glicemia",
                "glicose", "hba1c", "hemoglobina glicada", "tsh", "t4",
                "vitamina d", "vitamina b12", "ferritina", "ferro",
                "creatinina", "ureia", "ácido úrico", "acido urico",
                "tgo", "tgp", "ast", "alt", "ggt", "bilirrubin",
                "psa", "testosteron", "cortisol"]),
    ("Urina", ["urina", "eas ", "urocultura", "sumário de urina",
               "sumario de urina", "elementos anormais"]),
    ("Imagem", ["ressonância", "ressonancia", "tomografia", "raio-x",
                "raio x", "radiograf", "ultrassom", "ultra-som",
                "ecograf", "mamograf", "densitometr", "pet ct", "pet-ct"]),
    ("Cardiologia", ["eletrocardio", "ecocardio", "holter",
                      "teste ergom", "mapa ", "monitorização ambulatorial"]),
    ("Gastroenterologia", ["endoscop", "colonoscop", "retossigmoid",
                            "manometria"]),
    ("Endocrinologia", ["curva glicêmica", "curva glicemica",
                         "teste de tolerância", "ovários policísticos"]),
    ("Genético", ["sequenciamento", "ngs ", "painel genético",
                   "painel genetico", "exoma", "genoma", "cariótipo",
                   "snp ", "polimorfismo"]),
    ("Anatomopatológico", ["biópsia", "biopsia", "anatomopatolog",
                             "imuno-histo", "imuno histo"]),
    ("Microbiologia", ["cultura", "antibiograma", "psa cultura",
                        "sorologia", "anti-h", "vdrl", "hiv"]),
]


# ---------------------------------------------------------------------------
# Extração de texto do PDF + inferência de campos
# ---------------------------------------------------------------------------
def extrair_texto(dados: bytes) -> str:
    """Lê todas as páginas do PDF preservando espaços (x_tolerance=2)."""
    try:
        import pdfplumber
    except Exception:
        return ""
    try:
        partes: List[str] = []
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pg in pdf.pages:
                t = pg.extract_text(x_tolerance=2) or ""
                if t:
                    partes.append(t)
        return "\n".join(partes)
    except Exception:
        return ""


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c))


def inferir_categoria(texto: str) -> Optional[str]:
    t = _sem_acento((texto or "").lower())
    if not t:
        return None
    for cat, chaves in PALAVRAS_CATEGORIA:
        for chave in chaves:
            if _sem_acento(chave.lower()) in t:
                return cat
    return None


def inferir_data(texto: str) -> Optional[date]:
    """Tenta achar a data da coleta/exame no texto."""
    # Padrão preferido: 'DATA COLETA/RECEBIMENTO: 25/04/2025 ...'
    for padrao in [
        r"data\s+(?:da\s+)?coleta[^0-9]{0,30}(\d{1,2})/(\d{1,2})/(\d{4})",
        r"data\s+do\s+exame[^0-9]{0,30}(\d{1,2})/(\d{1,2})/(\d{4})",
        r"data[^0-9]{0,30}(\d{1,2})/(\d{1,2})/(\d{4})",
    ]:
        m = re.search(padrao, texto, re.I)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def inferir_laboratorio(texto: str) -> Optional[str]:
    """Pega o nome do laboratório (geralmente no topo)."""
    primeiras_str = "\n".join((texto or "").split("\n")[:30])
    laboratorios = [
        "CERPE", "Fleury", "Hermes Pardini", "DASA", "Alvaro", "Sabin",
        "Delboni", "Lavoisier", "Bronstein", "Labi Exames",
        "Instituto Hermes Pardini", "Diagnóstico das Américas",
    ]
    sem_acentos = _sem_acento(primeiras_str.lower())
    for lab in laboratorios:
        if _sem_acento(lab.lower()) in sem_acentos:
            return lab  # retorna a marca capitalizada do dicionário
    # Fallback: 1ª linha que mencione laboratorio/clinica/hospital.
    for linha in primeiras_str.split("\n"):
        s = linha.strip()
        if (3 <= len(s) <= 80
            and not re.match(r"\d|cpf|rg|nome|data|paciente|sexo|www\.", s, re.I)
            and any(p in _sem_acento(s.lower()) for p in
                    ("laborat", "diagnost", "clinic", "hospital"))):
            return s
    return None


def inferir_nome(texto: str, categoria: Optional[str]) -> str:
    """Sugere um nome para o exame (ex.: 'Hemograma', 'Ressonância de joelho')."""
    if not texto:
        return categoria or "Exame"
    nomes_priorit = [
        "Hemograma", "Colesterol Total", "Glicemia", "TSH", "T4 livre",
        "Vitamina D", "Vitamina B12", "Ferritina", "Creatinina",
        "Hemoglobina glicada", "HbA1c", "PSA", "Testosterona", "Cortisol",
        "Ecocardiograma", "Eletrocardiograma", "Holter", "Endoscopia",
        "Colonoscopia", "Ressonância magnética", "Tomografia computadorizada",
        "Ultrassom", "Mamografia", "Densitometria óssea", "Raio-X",
    ]
    t = _sem_acento(texto.lower())
    for n in nomes_priorit:
        if _sem_acento(n.lower()) in t:
            return n
    return categoria or "Exame"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def adicionar(
    data_: date,
    nome: str,
    categoria: str,
    paciente: str,
    arquivo_nome: Optional[str],
    arquivo_dados: Optional[bytes],
    laboratorio: Optional[str] = None,
    observacao: Optional[str] = None,
    texto_extraido: Optional[str] = None,
) -> int:
    with get_session() as s:
        e = Exame(
            data=data_,
            nome=nome.strip() or "Exame",
            categoria=categoria or "Outros",
            paciente=paciente.strip(),
            laboratorio=(laboratorio or "").strip() or None,
            observacao=(observacao or "").strip() or None,
            arquivo_nome=arquivo_nome,
            arquivo_dados=arquivo_dados,
            texto_extraido=texto_extraido,
        )
        s.add(e)
        s.flush()
        return e.id


def atualizar(eid: int, data_: date, nome: str, categoria: str,
              paciente: str, laboratorio: Optional[str],
              observacao: Optional[str]) -> None:
    with get_session() as s:
        e = s.get(Exame, eid)
        if not e:
            return
        e.data = data_
        e.nome = nome.strip() or "Exame"
        e.categoria = categoria or "Outros"
        e.paciente = paciente.strip()
        e.laboratorio = (laboratorio or "").strip() or None
        e.observacao = (observacao or "").strip() or None


def excluir(eid: int) -> None:
    with get_session() as s:
        e = s.get(Exame, eid)
        if e:
            s.delete(e)


def listar(ano: Optional[int] = None, paciente: Optional[str] = None,
           categoria: Optional[str] = None) -> List[dict]:
    with get_session() as s:
        rs = s.scalars(select(Exame).order_by(Exame.data.desc())).all()
        out = []
        for e in rs:
            if ano is not None and e.data.year != ano:
                continue
            if paciente and e.paciente != paciente:
                continue
            if categoria and e.categoria != categoria:
                continue
            out.append({
                "id": e.id,
                "data": e.data,
                "nome": e.nome,
                "categoria": e.categoria,
                "paciente": e.paciente,
                "laboratorio": e.laboratorio,
                "observacao": e.observacao,
                "tem_arquivo": e.arquivo_nome is not None,
                "arquivo_nome": e.arquivo_nome,
                "tem_analise": False,  # carregado sob demanda
                "ano": e.data.year,
            })
        return out


def arquivo(eid: int):
    with get_session() as s:
        e = s.get(Exame, eid)
        if not e or e.arquivo_dados is None:
            return None, None
        return e.arquivo_nome, e.arquivo_dados


def texto(eid: int) -> Optional[str]:
    with get_session() as s:
        e = s.get(Exame, eid)
        return e.texto_extraido if e else None


def analise(eid: int) -> Optional[str]:
    with get_session() as s:
        e = s.get(Exame, eid)
        return e.analise_ia if e else None


def salvar_analise(eid: int, texto_analise: str) -> None:
    with get_session() as s:
        e = s.get(Exame, eid)
        if e:
            e.analise_ia = texto_analise


def historico_mesmo_nome(eid: int) -> List[dict]:
    """Outros exames do mesmo paciente com nome similar (para evolução)."""
    with get_session() as s:
        atual = s.get(Exame, eid)
        if not atual:
            return []
        nome_base = (atual.nome or "").lower()
        rs = s.scalars(
            select(Exame)
            .where(Exame.paciente == atual.paciente)
            .order_by(Exame.data)
        ).all()
        out = []
        for e in rs:
            if e.id == atual.id:
                continue
            if (e.nome or "").lower() == nome_base or e.categoria == atual.categoria:
                out.append({"id": e.id, "data": e.data, "nome": e.nome,
                            "categoria": e.categoria})
        return out


# ---------------------------------------------------------------------------
# Análise educativa por IA
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "⚠️ **Análise educativa, NÃO diagnóstico.** Esta leitura é gerada por "
    "IA a partir do texto do laudo. Os números e termos podem ser "
    "interpretados de forma errada — somente o seu médico tem o contexto "
    "clínico completo para diagnosticar e orientar tratamento."
)

PROMPT_SISTEMA = (
    "Você é um educador em saúde, fala português do Brasil. Recebe o texto "
    "de um laudo de exame e produz uma LEITURA EDUCATIVA — não diagnóstico. "
    "Estrutura: \n"
    "1) **Resumo em 1 parágrafo** (que tipo de exame é, paciente, data).\n"
    "2) **Marcadores fora da referência** (lista; mostre o valor, a faixa "
    "de referência e UMA frase do que aquele marcador costuma indicar).\n"
    "3) **Marcadores em destaque dentro da referência** (3-5 itens "
    "importantes, mesmo que normais).\n"
    "4) **Perguntas que valem levar ao médico** (3 a 5 perguntas).\n"
    "Restrições: NÃO sugerir tratamento, NÃO sugerir medicamento, NÃO "
    "afirmar 'você tem X'. Use 'pode indicar', 'costuma estar associado a'. "
    "Cite os números do laudo quando possível. Seja conciso (até 500 palavras)."
)


def analisar_com_ia(eid: int, historico_resumo: Optional[str] = None) -> str:
    """Gera análise educativa do laudo via Claude. Lança ValueError se a
    chave não estiver configurada."""
    txt = texto(eid)
    if not txt:
        raise ValueError("Não há texto extraído deste exame para analisar.")
    from core.config import get_anthropic_key
    chave = get_anthropic_key()
    if not chave:
        raise ValueError("A chave ANTHROPIC_API_KEY não está configurada.")
    from anthropic import Anthropic

    msg_user = "Texto do laudo:\n\n" + txt[:20000]
    if historico_resumo:
        msg_user += "\n\nHistórico de exames anteriores do paciente:\n" + historico_resumo

    client = Anthropic(api_key=chave)
    resp = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1500,
        system=PROMPT_SISTEMA,
        messages=[{"role": "user", "content": msg_user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
