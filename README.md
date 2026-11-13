<div align="center">

<img src="assets/robo-concurseiro.png" alt="Robô concurseiro, mascote do agente de concursos" width="220">

# Agente de Concursos

**Um bot que acompanha concursos públicos e avisa no Telegram quando surge um novo.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-agendado-2088FF?logo=githubactions&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot_API-26A5E4?logo=telegram&logoColor=white)
![Dependências](https://img.shields.io/badge/dependências-nenhuma-brightgreen)

</div>

---

## Sobre o projeto

O Agente de Concursos consulta periodicamente as listas de concursos públicos do Brasil e envia para o Telegram apenas o que é novidade. Cada aviso vem com o link do concurso e atalhos para material de estudo no PCI Concursos, para que dê para ir direto da notícia para a preparação.

## O que ele faz

- **Busca concursos por estado**, incluindo o recorte nacional (`br`).
- **Avisa só o que é novo.** Os links já enviados são guardados e nunca se repetem.
- **Mostra o essencial** de cada concurso: órgão, número de vagas e situação (aberto ou previsto).
- **Anexa material de consulta** do PCI Concursos: página de concursos do estado, apostilas, provas e simulados.
- **Permite filtros** por estado, por situação e por palavra no nome do órgão.
- **Roda sozinho**, duas vezes por dia, sem servidor próprio.

## Como funciona

```
GitHub Actions (08:00 e 18:00, horário de Brasília)
        │
        ▼
  Busca os concursos ──► API concursosPublicosAPI (Flask)
        │                        │ se falhar
        │                        ▼
        │                 Leitura direta da tabela do site
        ▼
  Remove os já enviados (state/seen.json)
        │
        ▼
  Monta a mensagem + links do PCI Concursos
        │
        ▼
     Telegram
```

1. O workflow sobe a [concursosPublicosAPI](https://github.com/Vinimartinsc/concursosPublicosAPI) dentro do próprio job e consulta cada estado configurado.
2. Se a API não responder, o bot lê a tabela de concursos diretamente do ConcursosNoBrasil.
3. Os concursos são comparados com o histórico em `state/seen.json`, e só os inéditos seguem adiante.
4. O bot envia as mensagens pela API do Telegram, divididas quando passam do limite de tamanho.
5. O histórico atualizado é salvo no repositório por um commit automático.

Na primeira execução, o bot apenas registra os concursos que já existem e envia uma mensagem de confirmação. Os avisos de novidades começam a partir da execução seguinte.

## Exemplo de mensagem

```
📢 Novos concursos — RJ

🟢 DATAPREV
Vagas: 1.823 · Aberto
Ver concurso

🟡 Polícia Civil RJ
Vagas: Várias · Previsto
Ver concurso

📚 Material de consulta (PCI)
Concursos RJ · Apostilas · Provas · Simulados
```

## Configuração

O comportamento é ajustado por variáveis, sem mexer no código.

| Variável | Padrão | Descrição |
|---|---|---|
| `UFS` | `rj,br` | Estados a monitorar, separados por vírgula. `br` é o recorte nacional. |
| `STATUSES` | `open` | Situações aceitas: `open` (aberto), `expected` (previsto) e `closed` (encerrado). |
| `KEYWORDS` | vazio | Só avisa concursos cujo órgão contenha uma das palavras, como `prefeitura,tribunal`. |
| `MAX_PER_UF` | `20` | Máximo de concursos novos enviados por estado a cada execução. |
| `FIRST_RUN_SEND` | `0` | Com `1`, envia a lista completa já na primeira execução. |
| `TELEGRAM_BOT_TOKEN` | n/a | Token do bot, guardado como *secret* do GitHub. |
| `TELEGRAM_CHAT_ID` | n/a | Conversa que recebe os avisos, guardado como *secret* do GitHub. |

## Estrutura do repositório

```
.
├── bot.py                         # o agente (busca, filtro, mensagens e envio)
├── state/seen.json                # histórico de links já enviados
├── assets/robo-concurseiro.png    # mascote do projeto
├── .env.example                   # modelo das variáveis para uso local
└── .github/workflows/concursos.yml  # agendamento no GitHub Actions
```

## Tecnologias

- **Python 3.12**, usando somente a biblioteca padrão
- **GitHub Actions** para agendamento e execução
- **Telegram Bot API** para o envio das mensagens
- **concursosPublicosAPI** (Flask e BeautifulSoup) como fonte principal de concursos

## Limitações

- Os concursos vêm de raspagem do site ConcursosNoBrasil, que não oferece API oficial. Se o site mudar de formato ou bloquear acessos automáticos, a busca pode falhar temporariamente. Nesse caso o job termina com erro e nada é marcado como enviado.
- O PCI Concursos não tem API pública. O projeto só monta links para páginas abertas do site e não extrai o conteúdo delas.
- Os dados refletem o que o site de origem publica e podem conter atrasos ou erros. Confirme sempre as informações e os prazos no edital oficial.

## Créditos

- Lista de concursos: [ConcursosNoBrasil](https://concursosnobrasil.com), via [concursosPublicosAPI](https://github.com/Vinimartinsc/concursosPublicosAPI) de Vinimartinsc (licença MIT).
- Material de estudo: [PCI Concursos](https://www.pciconcursos.com.br).

Este é um projeto independente e sem vínculo com essas empresas.
