# Respostas às avaliações do Google — Adote Vi.Ca

Automação que busca as avaliações sem resposta no Perfil da Empresa no Google do Adote Vi.Ca, gera uma resposta para cada uma e a publica.

## Como funciona hoje

Uma rotina agendada do Claude Code roda **na nuvem, a cada hora**, sem depender de nenhum computador ligado. A cada execução ela:

1. exporta todas as avaliações pendentes com `app/main.py`;
2. lê no Google Drive o guia de respostas, o guia de identidade da marca e as instruções de escrita;
3. escreve uma resposta para cada avaliação;
4. publica as respostas com `app/main.py --auto`;
5. copia o histórico e o log da execução para a pasta `historico` no Drive.

As respostas são publicadas **sem revisão humana**. Os guias de resposta e as instruções ficam no Drive, e não neste repositório, porque têm informações internas.

## Estrutura

| Arquivo | Função |
|---|---|
| `app/main.py` | Fluxo principal: exporta, valida, publica e grava o histórico. |
| `app/reviews.py` | Lista as avaliações (todas as páginas) e publica respostas. |
| `app/google_business.py` | Credenciais, chamadas à API e novas tentativas em erros temporários. |
| `app/google_auth.py` | Autoriza a conta do Google e gera o `token.json`. |

## Modos de execução

Rode a partir da raiz do repositório:

| Comando | O que faz |
|---|---|
| `python app/main.py` | Sem arquivos de trabalho, exporta as pendentes para `reviews_to_process.json`. Com arquivos, mostra a simulação, sem publicar. |
| `python app/main.py --publish` | Mostra cada avaliação e resposta e pede confirmação antes de publicar. |
| `python app/main.py --auto` | Publica todas as respostas de `suggestions.json` sem pedir confirmação. Não exporta. |
| `python app/main.py --ciclo` | Exporta quando não há arquivos de trabalho e publica quando as respostas estão prontas. Era usado pelo Agendador do Windows a cada 10 minutos. |

## Arquivos de trabalho

Ficam na pasta indicada por `VICA_DATA_DIR`. Sem essa variável, a pasta é a do Google Drive no computador local.

**`reviews_to_process.json`** — gerado pela exportação, com uma lista de avaliações:

```json
[
  {
    "review_id": "...",
    "reviewer_name": "...",
    "rating": 5,
    "comment": "...",
    "create_time": "...",
    "has_reply": false
  }
]
```

**`suggestions.json`** — escrito por quem gera as respostas, com um item por avaliação:

```json
[
  {
    "review_id": "<igual ao da avaliação>",
    "suggested_reply": "<texto da resposta>"
  }
]
```

Regras da publicação:
- Avaliações sem resposta em `suggestions.json` ficam para a próxima exportação.
- Avaliações que já têm resposta no Google, ou que foram removidas, são puladas.
- Se uma publicação falhar, as demais seguem. Os arquivos de trabalho são mantidos para a próxima execução.
- O arquivo inteiro é rejeitado se não for uma lista JSON válida ou tiver `review_id` repetido.

## Histórico e log

- **Histórico:** cada avaliação ganha uma pasta `historico/<data>_<nome>_<fim do id>/` com:
  - `avaliacao.json` — a avaliação original, como veio do Google;
  - `sugestao.json` — a resposta gerada;
  - `publicacao.json` — o texto publicado, a data e hora e a confirmação do Google;
  - `resposta_existente.json` — a resposta que já existia no Google, quando a avaliação já estava respondida.

  Nada é sobrescrito: se uma resposta mudar, a nova versão recebe a data e a hora no nome.
- **Log:** `logs/automacao.log`, com data e hora em cada linha e os erros completos. O arquivo gira ao chegar a cerca de 1 MB e mantém as 5 versões anteriores.

## Configuração

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Coloque o arquivo de cliente OAuth do Google em `credentials/client_secret.json`.
3. Autorize a conta, o que gera o `token.json` na raiz:
   ```bash
   python app/google_auth.py
   ```

### Variáveis de ambiente

| Variável | Uso |
|---|---|
| `GOOGLE_TOKEN_JSON` | Conteúdo do `token.json`. Quando existe, é usado no lugar do arquivo. É assim que a rotina na nuvem se autentica. |
| `VICA_DATA_DIR` | Pasta dos arquivos de trabalho e do histórico. |

Se o Google pedir uma nova autorização, rode `app/google_auth.py` de novo. Depois, atualize a variável `GOOGLE_TOKEN_JSON` no ambiente da rotina na nuvem com o conteúdo do novo `token.json`.

## Segurança

- `token.json`, `credentials/` e os logs estão no `.gitignore` e **nunca** devem ser commitados. Este repositório é público.
- **Não rode o fluxo local enquanto a rotina na nuvem estiver ativa.** Os dois responderiam às mesmas avaliações, e uma resposta substituiria a outra.
