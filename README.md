# Finanças Pessoais

Sistema privado de gestão de finanças pessoais, rodando 100% local.
Banco SQLite, interface Streamlit. Nenhum dado sai da sua máquina.

## Como rodar

```bash
cd financas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (opcional nesta fase) configurar a chave da Anthropic, usada só na aba de análise:
cp .env.example .env   # edite e preencha ANTHROPIC_API_KEY

streamlit run app.py
```

O app abre no navegador. Use o menu lateral para navegar.

## Status — Fase 1 (Fundação + Receitas)

- ✅ Estrutura do projeto, banco SQLite e schema completo
- ✅ Módulo de **Receitas** (cadastro, listagem, exclusão, filtro por mês)
- ✅ **Painel Mensal** (esqueleto, já exibe total recebido)
- 🔜 Parcelamentos · Faturas de cartão · Investimentos · Painel completo · Análise IA

## Privacidade

- Dados em `data/financas.db` (local, ignorado pelo git).
- Uploads em `data/uploads/` (local, ignorado pelo git).
- A chave da API fica só no `.env`, nunca no código.
- O sistema nunca pede nem armazena senhas de bancos ou corretoras.
