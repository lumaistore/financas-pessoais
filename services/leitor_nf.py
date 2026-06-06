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
                texto += (pg.extract_text() or "") + "\n"
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

    # Prestador: linha próxima a 'razão social', 'nome', ou logo após o CNPJ.
    for padrao in [
        r"raz[ãa]o\s+social[:\s]*([^\n]+)",
        r"nome\s+do\s+(?:emitente|prestador)[:\s]*([^\n]+)",
    ]:
        m = re.search(padrao, texto, re.I)
        if m:
            cand = m.group(1).strip()
            if 3 <= len(cand) <= 80:
                out["prestador"] = cand
                break

    return out


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
            return _normaliza(local)
        # Senão, tenta com IA (PDF escaneado).
        ia = _ler_com_ia(dados, "application/pdf")
        if ia:
            # Combina: prioriza o que veio da IA, mantém o que veio do local.
            combinado = {**local, **{k: v for k, v in ia.items() if v}}
            return _normaliza(combinado)
        return _normaliza(local)

    if eh_imagem:
        ext = nome_lower.rsplit(".", 1)[-1]
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}[ext]
        ia = _ler_com_ia(dados, mime)
        return _normaliza(ia)

    return _normaliza({})
