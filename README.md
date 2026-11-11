# Agente de concursos → Telegram

Envia para o seu Telegram os concursos novos de cada UF, com links de material de
consulta do PCI Concursos (concursos da UF, apostilas, provas e simulados).

- **Concursos:** [concursosPublicosAPI](https://github.com/Vinimartinsc/concursosPublicosAPI)
  (Flask + scraping do ConcursosNoBrasil). O workflow clona e sobe a API dentro do próprio job.
- **PCI Concursos:** não existe API oficial, então o agente só monta links diretos para as
  páginas públicas do site (sem extrair conteúdo).
- **Sem duplicados:** os links já enviados ficam em `state/seen.json` (commitado pelo workflow).
- **Só biblioteca padrão do Python:** `bot.py` não precisa de `pip install`.

## 1. Criar o bot no Telegram

1. No Telegram, abra o **@BotFather** e envie `/newbot`. Guarde o **token**.
2. Abra a conversa com o seu bot novo e envie qualquer mensagem (ex.: `oi`).
3. Descubra o seu chat_id:
   ```bash
   TELEGRAM_BOT_TOKEN=seu_token python bot.py --chat-id
   ```

## 2. Testar localmente

```bash
# terminal 1: sobe a API
git clone https://github.com/Vinimartinsc/concursosPublicosAPI.git
cd concursosPublicosAPI && pip install -r requirements.txt && flask --app app run --port 5000

# terminal 2: mostra as mensagens sem enviar
python bot.py --dry-run
```

## 3. Rodar todo dia no GitHub Actions

1. Crie um repositório e suba estes arquivos.
2. Em **Settings → Secrets and variables → Actions**, crie os *secrets*
   `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
3. (Opcional) Em *Variables*, defina `UFS` (padrão `rj,br`), `STATUSES` (padrão `open`) e
   `KEYWORDS` (filtro por nome do órgão).
4. Em **Actions → Agente de concursos → Run workflow** para testar. Depois ele roda sozinho
   às 08:00 e 18:00 (horário de Brasília).

Na primeira execução o agente só registra os concursos atuais e manda uma mensagem de
confirmação; a partir daí você recebe apenas os novos. Para receber a lista completa já na
primeira vez, rode com `FIRST_RUN_SEND=1`.

## Ressalvas

- A API é um scraper do ConcursosNoBrasil. O próprio README dela diz para não usar em
  produção: se o site mudar o HTML, a busca falha. O workflow então termina com erro
  (você recebe o e-mail de falha do GitHub) e nada é marcado como enviado.
- Em repositórios sem commits por 60 dias o GitHub pausa workflows agendados; como o
  `state/seen.json` é commitado quando há novidades, isso costuma não acontecer, mas
  vale reativar em *Actions* se parar.
