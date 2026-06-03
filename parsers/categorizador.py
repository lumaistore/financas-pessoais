"""Categorização automática de transações por palavra-chave.

A categoria é apenas uma SUGESTÃO — o usuário revisa e ajusta na tela.
As regras são simples e fáceis de editar.
"""
from __future__ import annotations

# Categorias padrão criadas no primeiro uso.
CATEGORIAS_PADRAO = [
    "Alimentação",
    "Mercado",
    "Transporte",
    "Viagem",
    "Saúde",
    "Lazer",
    "Assinaturas",
    "Vestuário",
    "Casa",
    "Serviços",
    "Educação",
    "Outros",
]

# Palavra-chave (minúscula, sem acento sensível) -> categoria.
REGRAS = {
    # Alimentação / restaurantes
    "ifood": "Alimentação", "rappi": "Alimentação", "restaurante": "Alimentação",
    "burger": "Alimentação", "mcdonald": "Alimentação", "pizza": "Alimentação",
    "bar ": "Alimentação", "padaria": "Alimentação", "cafe": "Alimentação",
    # Mercado
    "supermerc": "Mercado", "mercado": "Mercado", "atacad": "Mercado",
    "carrefour": "Mercado", "pao de acucar": "Mercado", "sam s club": "Mercado",
    "sams club": "Mercado", "ferreira costa": "Casa",
    # Transporte
    "uber": "Transporte", "99 ": "Transporte", "99app": "Transporte",
    "posto": "Transporte", "ipiranga": "Transporte", "shell": "Transporte",
    "estacionamento": "Transporte", "parking": "Transporte",
    # Viagem
    "airbnb": "Viagem", "azul": "Viagem", "latam": "Viagem", "gol ": "Viagem",
    "tap ": "Viagem", "hotel": "Viagem", "booking": "Viagem", "dufry": "Viagem",
    "linhas aereas": "Viagem", "park hotel": "Viagem",
    # Saúde
    "farmacia": "Saúde", "drogaria": "Saúde", "raia": "Saúde", "pacheco": "Saúde",
    "dermatho": "Saúde", "clinica": "Saúde", "hospital": "Saúde", "apol": "Saúde",
    "prudent": "Saúde",
    # Assinaturas / streaming
    "netflix": "Assinaturas", "spotify": "Assinaturas", "amazon prime": "Assinaturas",
    "amazonprime": "Assinaturas", "prime canais": "Assinaturas",
    "disney": "Assinaturas", "hbo": "Assinaturas", "youtube": "Assinaturas",
    "google": "Assinaturas", "apple.com": "Assinaturas",
    # Lazer / academia
    "gym": "Lazer", "academia": "Lazer", "select gym": "Lazer",
    "cinema": "Lazer", "league": "Lazer", "barbearia": "Serviços",
    # Vestuário
    "polo wear": "Vestuário", "milano": "Vestuário", "renner": "Vestuário",
    "riachuelo": "Vestuário", "skx": "Vestuário", "skechers": "Vestuário",
    # Casa / reformas
    "tintas": "Casa", "sanvidro": "Casa", "vidro": "Casa", "leroy": "Casa",
    "oasis": "Casa",
    # Compras gerais / marketplaces
    "amazon": "Outros", "mercadolivre": "Outros", "mercado livre": "Outros",
    "magazine": "Outros", "shopee": "Outros", "aliexpress": "Outros",
    # Serviços / pagamentos
    "pagtesouro": "Serviços", "pagseguro": "Serviços", "mp*": "Serviços",
    "pg *": "Serviços", "auvp": "Educação", "propig": "Serviços",
}


def sugerir_categoria(descricao: str) -> str:
    d = (descricao or "").lower()
    for chave, categoria in REGRAS.items():
        if chave in d:
            return categoria
    return "Outros"
