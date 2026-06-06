"""Leitura automática de nota fiscal/recibo médico.

Estratégia em camadas (para minimizar custo e latência):
1) Se for PDF com texto extraível → regex local (grátis, instantâneo).
2) Caso contrário (imagem ou PDF escaneado) → API Claude com visão para
   extrair os campos. Só os bytes do arquivo saem da máquina, nada pessoal.

Sempre devolve um dict com {data, valor_pago, prestador, cnpj_cpf, tipo,
paciente}. Campos não encontrados ficam None — o usuário ajusta na tela.
"""
from __future__ import annotations

import base64
import io
import json
import re
from datetime import date
from typing import Optional

PROMPT_SISTEMA = (
    "Você lê notas fiscais e recibos médicos em português do Brasil. "
    "Extraia APENAS estes campos: data (DD/MM/AAAA), valor_pago (número em "
    "reais, ex.: 350.00), prestador (nome do médico/clínica/hospital), "
    "cnpj_cpf (formatado, se houver), tipo (uma das opções), paciente "
    "(nome se aparecer). Devolva um JSON puro, sem cercas markdown. Use null "
    "para campos não encontrados."
)

PROMPT_USUARIO = (
    "Analise a imagem deste documento médico e extraia os campos. "
    'Tipos válidos: "Plano de saúde", "Consulta médica", "Exame", '
    '"Hospital / Internação", "Cirurgia", "Dentista", "Psicólogo", '
    '"Psiquiatra", "Fisioterapeuta", "Fonoaudiólogo", '
    '"Aparelho ortopédico / prótese", "Aparelho auditivo / visual", '
    '"Medicamento (em internação)", "Outros". '
    'Responda APENAS o JSON: {"data":"DD/MM/AAAA"|null, "valor_pago":number|null, '
    '"prestador":string|null, "cnpj_cpf":string|null, "tipo":string|null, '
    '"paciente":string|null}'
)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _parse_data_br(s: Optional[str]) -> Optional[date]:
    """Aceita 'DD/MM/AAAA', 'AAAA-MM-DD' (ISO) e variações."""
    if not s:
        return None
    # ISO 'YYYY-MM-DD'
    m = re.match(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # BR 'DD/MM/AAAA'
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


# Palavras-chave para inferir o "tipo" da despesa a partir do texto da NF.
# Ordem importa: o primeiro match vence. Listei dos mais específicos para os
# mais genéricos.
PALAVRAS_TIPO = [
    ("Plano de saúde", ["plano de saúde", "operadora de saúde", "convênio médico",
                         "amil", "bradesco saúde", "unimed", "hapvida",
                         "sulamérica saúde", "porto seguro saúde"]),
    ("Dentista", ["odontolog", "dental", "dentário", "dentista", "ortodont",
                  "endodont", "periodont", "implantodont"]),
    ("Psicólogo", ["psicolog", "psicoterap"]),
    ("Psiquiatra", ["psiquiatr"]),
    ("Fisioterapeuta", ["fisioterap", "rpg ", "pilates clínic"]),
    ("Fonoaudiólogo", ["fonoaudiolog", "fono "]),
    # Especialidades médicas e consultórios vêm ANTES de hospital (uma NF de
    # consultório pode mencionar um endereço com "hospital"; não significa
    # que a despesa é uma internação).
    ("Consulta médica", ["dermatolog", "cardiolog", "ortoped", "ginecolog",
                          "pediatr", "urolog", "neurolog", "endocrinolog",
                          "gastroenterolog", "oftalmolog", "otorrinolaringolog",
                          "reumatolog", "nefrolog", "alergista", "alergolog",
                          "geriatr", "infectolog", "obstetri", "consultorio",
                          "consultório", "consulta", "atendimento médico",
                          "clínica médica", "clinica medica"]),
    ("Exame", ["exame", "laborat", "análise clínic", "radiograf", "raio-x",
               "raio x", "ressonância", "tomograf", "ultrassom",
               "ultra-sonografia", "ecograf", "endoscop", "colonoscop",
               "mamograf", "densitometr", "biópsia", "fleury", "dasa",
               "hermes pardini", "labi exames", "instituto de imagens", "ct ",
               "cintilograf"]),
    # Hospital só dispara em termos que indicam internação/atendimento
    # hospitalar de fato (a palavra solta "hospital" pode aparecer num
    # endereço da NF de consultório).
    ("Hospital / Internação", ["internação", "internamento", "diária hospital",
                                 "pronto socorro", "atendimento hospitalar",
                                 "hospital albert", "hospital sírio",
                                 "hospital israelita"]),
    ("Cirurgia", ["cirurgia", "cirurg", "procedimento cirúrg", "centro cirúrg"]),
    ("Aparelho ortopédico / prótese", ["prótese", "ortótese", "órtese",
                                         "aparelho ortopéd", "tipoia ",
                                         "cinta abdominal"]),
    ("Aparelho auditivo / visual", ["aparelho auditivo", "lente de contato",
                                     "lentes de contato", "armação",
                                     "óculos de grau", "audiometria"]),
    ("Medicamento (em internação)", ["medicament", "remédio", "farmacêut"]),
]


def _sem_acento(s: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "")
        if not unicodedata.combining(c)
    )


def _inferir_tipo(texto: str) -> Optional[str]:
    """A partir do texto da NF, sugere um tipo da lista TIPOS.
    A comparação ignora acentos (ex.: 'SAUDE' casa com 'saúde')."""
    t = _sem_acento((texto or "").lower())
    if not t:
        return None
    for tipo, chaves in PALAVRAS_TIPO:
        for chave in chaves:
            if _sem_acento(chave.lower()) in t:
                return tipo
    return None


def _normaliza(d: dict) -> dict:
    """Garante o formato esperado pela UI (date python + float + strings)."""
    out = {
        "data": None,
        "valor_pago": None,
        "prestador": None,
        "cnpj_cpf": None,
        "tipo": None,
        "paciente": None,
    }
    if isinstance(d.get("data"), str):
        out["data"] = _parse_data_br(d["data"])
    if d.get("valor_pago") is not None:
        try:
            out["valor_pago"] = float(d["valor_pago"])
        except (TypeError, ValueError):
            pass
    for k in ("prestador", "cnpj_cpf", "tipo", "paciente"):
        v = d.get(k)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none"):
            out[k] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Camada 1 — PDF com texto extraível (regex local)
# ---------------------------------------------------------------------------
def _ler_pdf_texto(dados: bytes) -> dict:
    try:
        import pdfplumber

        texto = ""
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pg in pdf.pages[:2]:  # nota costuma caber em 1-2 páginas
                # x_tolerance=2 preserva os espaços em layouts colunares
                # (típico da NFS-e nacional, ex.: Recife).
                texto += (pg.extract_text(x_tolerance=2) or "") + "\n"
    except Exception:
        return {}

    if len(texto.strip()) < 30:  # PDF é só imagem — manda pra IA
        return {}

    out: dict = {}

    # Data: pega a primeira data DD/MM/AAAA do documento.
    md = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", texto)
    if md:
        try:
            out["data"] = date(int(md.group(3)), int(md.group(2)), int(md.group(1))).isoformat()
        except ValueError:
            pass

    # Valor: tenta achar "Valor total / total a pagar / R$ ..." (priorizando 'total').
    valor = None
    for padrao in [
        r"valor\s+total[^\d]{0,15}R?\$?\s*([\d\.\,]+)",
        r"total\s+(?:a\s+pagar|geral|do\s+documento)[^\d]{0,15}R?\$?\s*([\d\.\,]+)",
        r"valor\s+pago[^\d]{0,15}R?\$?\s*([\d\.\,]+)",
        r"R\$\s*([\d\.\,]+)",
    ]:
        m = re.search(padrao, texto, re.I)
        if m:
            num = m.group(1)
            if "," in num and "." in num:
                if num.rfind(",") > num.rfind("."):
                    num = num.replace(".", "").replace(",", ".")
                else:
                    num = num.replace(",", "")
            elif "," in num:
                num = num.replace(".", "").replace(",", ".")
            try:
                valor = float(num)
                if valor > 0:
                    break
            except ValueError:
                continue
    if valor:
        out["valor_pago"] = valor

    # CNPJ ou CPF (formatado).
    mc = re.search(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})\b", texto)
    if mc:
        out["cnpj_cpf"] = mc.group(1)
    else:
        # CNPJ/CPF sem máscara
        mc2 = re.search(r"\b(\d{14}|\d{11})\b", texto)
        if mc2:
            n = mc2.group(1)
            if len(n) == 14:
                out["cnpj_cpf"] = f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
            else:
                out["cnpj_cpf"] = f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"

    # Prestador (emissor da NFS-e). Estratégia: isola a seção do EMITENTE
    # (antes do "TOMADOR DO SERVIÇO") e procura o campo "Nome / Nome
    # Empresarial" ou "Razão Social". Pega o que estiver na mesma linha
    # depois do rótulo, ou na próxima linha não-vazia que pareça um nome.
    prestador = _extrair_prestador(texto)
    if prestador:
        out["prestador"] = prestador

    # Tipo: infere por palavras-chave do texto inteiro.
    tipo = _inferir_tipo(texto)
    if tipo:
        out["tipo"] = tipo

    return out


def _extrair_prestador(texto: str) -> Optional[str]:
    """Lê o nome do prestador/emissor de uma NF. Robusto contra layouts em
    colunas (pdfplumber pode emitir o texto em ordem inesperada). Estratégias
    em camadas:
      1) Busca por cabeçalhos ('Nome / Nome Empresarial', 'Razão Social' …)
         dentro da seção do EMITENTE (antes do bloco do TOMADOR).
      2) Procura linhas com sufixo societário (LTDA, S/A, EIRELI, ME, EPP).
      3) Pega a linha vizinha ao primeiro CNPJ encontrado.
    Em qualquer caso, evita capturar o nome do TOMADOR/cliente."""
    # Seção do emitente: do início até o cabeçalho do tomador.
    tom = re.search(
        r"\btomador\s+d[oe]?\s*servi[çc]o\b|\bdestinat[áa]rio\b|"
        r"\bdados\s+do\s+tomador\b",
        texto, re.I,
    )
    secao = texto[: tom.start()] if tom else texto

    # -- Camada 1: cabeçalhos clássicos -------------------------------------
    # \s* aceita o formato com OU sem espaços (NFS-e nacional do Recife,
    # por ex., emite 'Nome/NomeEmpresarial' colado).
    cabecalhos = [
        r"nome\s*/?\s*nome\s*empresarial",
        r"raz[ãa]o\s*social",
        r"nome\s*empresarial",
        r"nome\s+do\s+(?:emitente|prestador)",
        r"^nome\s*[:.]",
    ]
    linhas = secao.split("\n")
    for idx, linha in enumerate(linhas):
        for cab in cabecalhos:
            mh = re.search(cab, linha, re.I)
            if not mh:
                continue
            depois = linha[mh.end():].lstrip(" :\t/")
            cand = _limpar_candidato(_isolar_nome(depois))
            if cand:
                return cand
            for j in range(idx + 1, min(idx + 6, len(linhas))):
                cand = _limpar_candidato(_isolar_nome(linhas[j]))
                if cand:
                    return cand
                if linhas[j].strip():
                    break
            break

    # -- Camada 2: linha com sufixo de pessoa jurídica ---------------------
    # Ex.: "DERMATHO - CLINICA DERMATOLOGICA ANTUNES E BRAZ LTDA"
    sufixos = r"(?:LTDA|S/?\.?A\.?|EIRELI|MEI|ME|EPP|S\.?S\.?)"
    for linha in linhas:
        s = linha.strip()
        if 8 <= len(s) <= 120 and re.search(rf"\b{sufixos}\b\.?\s*$", s, re.I):
            cand = _limpar_candidato(s)
            if cand:
                return cand
    # Também tenta sem âncora no fim (sufixo no meio do nome).
    for linha in linhas:
        s = linha.strip()
        if 8 <= len(s) <= 120 and re.search(rf"\b{sufixos}\b", s, re.I):
            cand = _limpar_candidato(s)
            if cand:
                return cand

    # -- Camada 3: vizinhança do primeiro CNPJ -----------------------------
    mc = re.search(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", secao)
    if mc:
        # Olha as 5 linhas em volta da linha do CNPJ.
        antes = secao[: mc.start()].splitlines()
        depois = secao[mc.end():].splitlines()
        candidatos = [*antes[-4:], *depois[:4]]
        for c in candidatos:
            cand = _limpar_candidato(c)
            if cand and re.search(r"[A-Z]{3}", cand):  # tem algo em maiúsculo
                return cand

    return None


def _isolar_nome(linha: str) -> str:
    """Numa linha como 'DERMATHO-...LTDA dermatho@hotmail.com', tira o
    e-mail / CNPJ / CPF / telefone que aparece depois do nome. Retorna só
    a parte do nome (que pode ter espaços internos)."""
    if not linha:
        return linha
    s = linha.strip()
    # Corta a partir do primeiro e-mail (palavra com @).
    s = re.split(r"\s+\S*@\S+", s, maxsplit=1)[0]
    # Corta a partir do primeiro CNPJ/CPF formatado.
    s = re.split(r"\s+\d{2,3}[\.\-/]", s, maxsplit=1)[0]
    # Corta a partir de telefones óbvios ((81)...).
    s = re.split(r"\s+\(\d{2}\)", s, maxsplit=1)[0]
    return s.strip()


def _limpar_candidato(s: str) -> Optional[str]:
    """Devolve `s` limpo se parece um nome válido de empresa/pessoa; senão None."""
    s = (s or "").strip(" \t-:|")
    if not s or len(s) < 5 or len(s) > 120:
        return None

    sl = s.lower()

    # 1) Rótulos/cabeçalhos comuns que NÃO são nome de empresa.
    prefixos_invalidos = (
        "cnpj", "cpf", "nif", "endere", "e-mail", "telefone", "fone",
        "inscri", "tomador", "raz", "nome", "munic", "uf", "cep",
        "valor", "simples", "regime", "data", "n[uú]mero",
        # NFS-e nacional: cabeçalhos da seção do emitente + chave de
        # acesso/QR. Concatenados também (sem espaço) por causa da
        # extração colunar do pdfplumber.
        "emitente", "prestador", "discrim",
        "chave", "acesso", "portal", "verifica", "autenti", "c[óo]digo",
        "servi[çc]o", "nfs", "n[ºo°]", "p[áa]gina",
        "tomadorda",  # 'TOMADORDA' colado
    )
    for p in prefixos_invalidos:
        if re.match(p, sl):
            return None

    # 2) Cabeçalhos de coluna concatenados (ex.: 'CNPJ/CPF/NIF'). Sinal:
    # mais de uma barra com letras coladas (CNPJ/CPF/NIF tem duas barras
    # nesse formato; 'S/A' tem só uma e passa).
    if len(re.findall(r"[A-Za-z]/[A-Za-z]", s)) >= 2:
        return None
    # Se aparecem mais de 2 termos que costumam ser cabeçalhos juntos.
    sl_compacto = re.sub(r"\s+", " ", sl)
    indicios = ("cnpj", "cpf", "nif", "inscrição", "inscricao", "telefone",
                "e-mail", "munic", "uf", "cep", "regime", "simples")
    if sum(1 for ind in indicios if ind in sl_compacto) >= 2:
        return None

    # 3) Texto colado sem espaços. Exceção: razão social com tudo colado
    # ('DERMATHO-CLINICA...LTDA') é legítima na NFS-e nacional — aceita
    # se terminar com sufixo societário.
    termina_em_sufixo = bool(
        re.search(r"(LTDA|EIRELI|MEI|ME|EPP|S/?\.?A\.?)\.?\s*$", s, re.I)
    )
    sem_marcas = re.sub(r"[^\w\s]", " ", s)
    palavras = sem_marcas.split()
    if len(palavras) < 1:
        return None
    if not termina_em_sufixo:
        if len(palavras) < 2:
            return None
        if any(len(p) > 22 for p in palavras):
            return None
        if s.count(" ") < max(1, len(s) // 18):
            return None

    return s


# ---------------------------------------------------------------------------
# Camada 2 — Visão com IA (foto, PDF escaneado)
# ---------------------------------------------------------------------------
def _ler_com_ia(dados: bytes, mime: str) -> dict:
    try:
        from anthropic import Anthropic
        from core.config import get_anthropic_key
    except Exception:
        return {}

    chave = get_anthropic_key()
    if not chave:
        return {}

    b64 = base64.standard_b64encode(dados).decode("utf-8")
    if mime == "application/pdf":
        media_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }
    else:
        media_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }

    try:
        client = Anthropic(api_key=chave)
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=400,
            system=PROMPT_SISTEMA,
            messages=[{
                "role": "user",
                "content": [media_block, {"type": "text", "text": PROMPT_USUARIO}],
            }],
        )
    except Exception:
        return {}

    texto = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    # Remove possíveis cercas de markdown.
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.S)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------
def ler_nf(dados: bytes, nome_arquivo: str) -> dict:
    """Extrai campos de uma NF/recibo. Devolve dict com chaves
    {data, valor_pago, prestador, cnpj_cpf, tipo, paciente} — None onde não
    foi possível identificar."""
    nome_lower = (nome_arquivo or "").lower()
    eh_pdf = nome_lower.endswith(".pdf")
    eh_imagem = nome_lower.endswith((".png", ".jpg", ".jpeg", ".webp"))

    if eh_pdf:
        # Tenta primeiro o caminho local rápido.
        local = _ler_pdf_texto(dados)
        # Se conseguiu ao menos valor + data, ótimo.
        if local.get("valor_pago") and local.get("data"):
            return _normaliza_com_fallback(local)
        # Senão, tenta com IA (PDF escaneado).
        ia = _ler_com_ia(dados, "application/pdf")
        if ia:
            # Combina: prioriza o que veio da IA, mantém o que veio do local.
            combinado = {**local, **{k: v for k, v in ia.items() if v}}
            return _normaliza_com_fallback(combinado)
        return _normaliza_com_fallback(local)

    if eh_imagem:
        ext = nome_lower.rsplit(".", 1)[-1]
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}[ext]
        ia = _ler_com_ia(dados, mime)
        return _normaliza_com_fallback(ia)

    return _normaliza({})


def _normaliza_com_fallback(d: dict) -> dict:
    """Como _normaliza, mas se 'tipo' veio vazio, tenta inferir pelo nome do
    prestador (caso a IA tenha pegado o prestador mas não o tipo)."""
    out = _normaliza(d)
    if not out.get("tipo") and out.get("prestador"):
        out["tipo"] = _inferir_tipo(out["prestador"])
    return out
