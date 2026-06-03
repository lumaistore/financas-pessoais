# Publicar o app na nuvem (grátis, privado, 24h)

Objetivo: rodar o app **sem depender do seu Mac ligado**, com acesso só seu.

- **Hospedagem do app:** Streamlit Community Cloud (grátis, sem cartão).
- **Banco de dados:** Neon — Postgres grátis (sem cartão). É onde seus dados
  passam a morar (em vez do arquivo local).
- **Privacidade:** o app fica **privado** — só as contas de e-mail que você
  autorizar conseguem abrir.

O código já funciona nos dois modos: **sem** `DATABASE_URL` ele usa o SQLite
local (seu Mac, como hoje); **com** `DATABASE_URL` ele usa o Postgres da nuvem.

---

## Passo 1 — Criar o banco grátis no Neon
1. Acesse https://neon.tech e crie a conta (pode entrar com o GitHub).
2. Crie um projeto (qualquer nome, ex.: `financas`). Região: escolha uma dos EUA.
3. Na tela do projeto, copie a **Connection string** (começa com
   `postgresql://...` e termina com `?sslmode=require`). **Guarde** — é o seu
   `DATABASE_URL`.

## Passo 2 — Copiar seus dados do Mac para o Neon (uma vez)
No Terminal, na pasta do projeto:
```bash
DATABASE_URL="COLE_AQUI_A_CONNECTION_STRING_DO_NEON" \
  .venv/bin/python tools/migrar_para_postgres.py
```
Ele cria as tabelas no Neon e copia tudo (receitas, faturas, investimentos,
despesas, orçamentos…). No fim mostra quantas linhas copiou.

## Passo 3 — Subir o código no GitHub
1. Crie um repositório no seu GitHub (pode ser **privado**), ex.: `financas`.
2. Suba a pasta do projeto. O `.gitignore` já evita mandar segredos e dados
   (`.env`, `data/financas.db`, `data/backups/` não vão).

## Passo 4 — Publicar no Streamlit Community Cloud
1. Acesse https://share.streamlit.io e entre **com o GitHub**.
2. **New app** → escolha o repositório, branch `main`, arquivo `app.py`.
3. Em **Advanced settings → Secrets**, cole:
   ```toml
   DATABASE_URL = "a_mesma_connection_string_do_neon"
   ANTHROPIC_API_KEY = "sua_chave_da_anthropic"
   ```
4. **Deploy**. Em 1–2 min o app sobe numa URL pública.

## Passo 5 — Deixar privado (só você)
1. No painel do app no Streamlit Cloud → **Settings → Sharing**.
2. Mude para **"Only specific people can view this app"** e adicione o seu
   e-mail (o mesmo da sua conta Google). Pronto: ninguém mais abre.

## Passo 6 — Usar no celular
Abra a URL do app no navegador do celular, faça login com seu Google e
**Adicione à Tela de Início** (vira ícone, como um app).

---

## Dúvidas comuns
- **Mexer no app depois:** edite o código, dê `git push` — o Streamlit
  atualiza sozinho.
- **Continuar usando local também?** Sim. Sem `DATABASE_URL` no Mac, ele segue
  no SQLite. Mas aí os dados ficam separados (local vs nuvem) — o ideal é usar
  só a nuvem depois de migrar, para não divergir.
- **Backup:** o Neon já mantém backups automáticos; o botão de backup local
  continua útil quando você roda no Mac.
- **Segurança:** nenhuma senha de banco/corretora é guardada. A chave da
  Anthropic e a URL do banco ficam só nos *secrets* do Streamlit (não no
  código).
