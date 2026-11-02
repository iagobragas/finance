# finance

Controle financeiro pessoal (e de MEI) com partidas dobradas, feito em cima do [Beancount](https://beancount.github.io/docs/) e do [Fava](https://beancount.github.io/fava/). Você joga os extratos do banco numa pasta. O sistema reconhece, categoriza, evita duplicados e mostra tudo num painel web local, com ciclo do cartão, orçamento, previsão, reembolsos e DAS.

Roda 100% no seu computador. Nada é enviado para servidor nenhum.

**Código e dados ficam separados.** Este repositório tem só o código e um exemplo fictício. Seus extratos, livro e configurações moram numa pasta de dados que nunca entra no git (veja [Seus dados](#seus-dados)).

---

## Sumário

- [O que tem](#o-que-tem)
- [Instalação no Mac](#instalação-no-mac)
- [Primeiros passos](#primeiros-passos)
- [Uso no dia a dia](#uso-no-dia-a-dia)
- [Extratos suportados](#extratos-suportados)
- [Seus dados](#seus-dados)
- [Usar em mais de um Mac (iCloud)](#usar-em-mais-de-um-mac-icloud)
- [Configuração](#configuração)
- [Como o sistema pensa](#como-o-sistema-pensa)
- [Estrutura do código](#estrutura-do-código)
- [Adicionar um banco novo](#adicionar-um-banco-novo)
- [Problemas comuns](#problemas-comuns)

---

## O que tem

O painel abre em `http://localhost:5050` e tem estas abas:

| Aba | Para que serve |
|---|---|
| **Ciclo** | Quanto sobra até o fim do ciclo (ex.: 16 → 15), com o que ainda entra, as faturas que vencem, assinaturas, parcelas e DAS. Mostra os próximos ciclos até a última parcela, com três cenários: só o que é certo, no ritmo médio ou seguindo o Planejamento. |
| **Resumo** | O ano mês a mês: receitas, fixas, variáveis e resultado. Mostra também o disponível nas contas e o total devido nos cartões. |
| **Contas** | Extrato de cada conta e cartão, com saldo, conferência e comprovantes. |
| **Gastos** | Todos os gastos com filtros por categoria, meio de pagamento e cartão. Permite marcar como reembolsável, inclusive em lote ou por período de viagem. |
| **Receitas** | Quanto entrou de cada fonte, o limite do MEI, as notas fiscais e os reembolsos a receber. |
| **Buscar** | Busca livre ("uber > 30", "mercado set"). |
| **Planejamento** | Orçamento 50/30/20 e quanto gastar por categoria (em R$ ou em % da receita). Também tem assinaturas, parcelas, compromissos, metas de investir e doar, e a previsão dos próximos meses. |
| **Simulador** | O que muda com um aumento, um gasto novo, etc. |
| **Lançar** | Lançamento manual rápido: valor, descrição e Enter, com a categoria sugerida. |
| **Importar** | Arraste os arquivos do banco. Mostra o que está atrasado e como baixar cada extrato. |
| **Pendências** | O que falta categorizar, transferências sem par e extratos atrasados. |

---

## Instalação no Mac

Precisa de [Homebrew](https://brew.sh), Python 3.11 e `pdftotext` (para ler faturas em PDF):

```sh
brew install python@3.11 poppler git
git clone <url-deste-repositório> finance
cd finance
./finance exemplo        # abre o painel com dados fictícios, para ver como é
```

Na primeira execução, o `./finance` cria o ambiente Python (`.venv/`) e instala as dependências (`requirements.txt`). Isso leva menos de um minuto.

---

## Primeiros passos

```sh
./finance init           # cria a pasta de dados (dados/) com as configurações de exemplo e um livro vazio
```

Depois:

1. Ajuste **`dados/config/accounts.yaml`** com suas contas e cartões (dia de fechamento e de vencimento), as empresas que pagam você (`empresas:` e `pagamentos:`), o início do ciclo e os dados do MEI.
2. Ajuste **`dados/config/rules.yaml`** para casar as descrições dos seus extratos com as categorias. Coloque seu nome e CNPJ na regra de transferência para você mesmo.
3. Rode `./finance`, abra a aba **Importar** e arraste os extratos.
4. Na aba **Pendências**, categorize o que ficou sem regra. Cada escolha pode virar uma regra nova (fica em `rules_user.yaml`).
5. Na aba **Planejamento**, defina salários, orçamento por categoria e metas.

---

## Uso no dia a dia

```sh
./finance                # importa, valida, abre o painel e reimporta sozinho quando algo muda
./finance build          # só importa e valida
./finance check          # só valida (os saldos batem com os extratos?)
./finance exemplo        # o mesmo, mas com os dados fictícios de exemplo/
```

**Rotina mensal:** baixe os extratos e arraste na aba **Importar**, ou jogue em `dados/inbox/` com qualquer nome. O sistema:

- reconhece o banco e o período;
- renomeia e guarda em `dados/statements/<fonte>/`;
- descarta arquivo repetido;
- não duplica lançamentos quando os períodos se sobrepõem;
- deixa na inbox, com aviso, o que não reconhecer.

Lançamentos que não aparecem em extrato nenhum (dinheiro vivo, empréstimo) entram pela aba **Lançar** e ficam em `dados/ledger/manual.beancount`.

---

## Extratos suportados

| Fonte | Formato | Como baixar |
|---|---|---|
| Conta Inter PF | CSV | App Inter → Extrato → Exportar → CSV |
| Conta Cora PJ | OFX (ou CSV antigo) | App/Web Cora → Extrato → Exportar OFX |
| Cartão Inter | CSV (ou PDF da fatura) | App Inter → Cartão → Fatura → Exportar CSV (dá para baixar a fatura aberta) |
| Cartão Nubank | OFX (ou CSV) | App Nubank → Fatura → Exportar OFX (a qualquer hora, inclusive a aberta) |
| Conta Nubank PF | OFX | App Nubank → Conta → Extrato → Exportar OFX (mês a mês) |
| NFS-e do MEI | XML/PDF | Emissor nacional → Notas emitidas → baixar XML |

Contas em **OFX de qualquer banco** funcionam sem código novo: basta mapear o número da conta em `ofx_contas` no `accounts.yaml`.

---

## Seus dados

A pasta de dados é procurada nesta ordem:

1. a variável de ambiente `FINANCE_DATA`;
2. `dados/` ao lado do código, que pode ser uma pasta de verdade ou um **link** para outra (iCloud, por exemplo).

Conteúdo da pasta:

```
dados/
  config/          suas configurações (contas, regras, plano, reembolsos…)
  ledger/
    main.beancount       opções do livro + includes
    imported.beancount   GERADO a partir de statements/, não edite
    manual.beancount     lançamentos manuais (aba Lançar)
  statements/      extratos organizados automaticamente, não mexa
  inbox/           onde chegam os arquivos novos
  comprovantes/    fotos e PDFs de comprovantes (aba Contas)
  notas/           notas fiscais emitidas (NFS-e)
```

`dados/` está no `.gitignore`. **Nunca** tire de lá nem faça commit dessa pasta: ela tem extratos, CNPJ, salário e, se você usar, credenciais.

---

## Usar em mais de um Mac (iCloud)

O código vai pelo git e os dados pelo iCloud Drive.

**No Mac onde os dados já estão:**

```sh
cd finance
# 1. mova a pasta de dados para o iCloud Drive (pode ser pelo Finder também)
mv dados ~/Library/Mobile\ Documents/com~apple~CloudDocs/Financas
# 2. deixe um link no lugar
ln -s ~/Library/Mobile\ Documents/com~apple~CloudDocs/Financas dados
./finance check
```

**No outro Mac:**

```sh
brew install python@3.11 poppler git
git clone <url-deste-repositório> finance
cd finance
ln -s ~/Library/Mobile\ Documents/com~apple~CloudDocs/Financas dados
./finance
```

Cuidados:

- **Mantenha a pasta baixada.** No Finder, clique com o botão direito em *Financas* e escolha **Manter Baixado**. Assim o iCloud não troca os arquivos por atalhos para economizar espaço.
- **Use um Mac por vez.** Se os dois estiverem com o painel aberto e você editar nos dois, o iCloud pode criar cópias com conflito (como "forecast 2.yaml"). Feche o `./finance` num antes de usar no outro.
- **Permissão de acesso.** Na primeira vez, o macOS pode pedir para o Terminal acessar o iCloud Drive. Se aparecer *Operation not permitted*, vá em **Ajustes do Sistema → Privacidade e Segurança → Acesso Total ao Disco** e ative o Terminal (ou o app que você usa, como o iTerm).
- O `.venv/` é local de cada Mac e não vai para o iCloud nem para o git.

---

## Configuração

Tudo em `dados/config/`. As abas editam a maior parte desses arquivos, mas dá para editar à mão; o painel recarrega sozinho.

| Arquivo | O que tem | Quem edita |
|---|---|---|
| `accounts.yaml` | Contas por tipo de extrato (`sources`, `ofx_contas`), cartões (`card_cycles`: fechamento e vencimento), início do ciclo, MEI (limite, dia e valor do DAS), dia de pagamento de cada empresa, `empresas` (quem paga e reembolsa), nomes de exibição | Você |
| `rules.yaml` | Regras de categoria (regex → conta). A primeira que casar vence | Você |
| `rules_user.yaml` | Regras criadas na aba Pendências (têm prioridade) | Aba Pendências |
| `overrides.yaml` | Decisões lançamento a lançamento | Aba Pendências |
| `forecast.yaml` | Plano: receitas (média, fixo ou com aumentos), orçamento por categoria (média, fixo, ajuste em % ou % da receita), compromissos, extras, metas de investir e doar | Aba Planejamento |
| `reembolsos.yaml` | Parte fixa de cada pagamento e gastos reembolsáveis | Abas Gastos e Lançar |
| `assinaturas.yaml` | Assinaturas canceladas | Aba Planejamento |
| `comprovantes.yaml` | Comprovante ligado a cada gasto | Aba Contas |

### Categorias

```
Income:Trabalho:<Empresa>          salário de cada empresa (o nome é o mesmo de `empresas:` em accounts.yaml)
Income:Outras:*                    rendimentos, presentes, não identificadas
Expenses:Fixas:*                   o que se repete todo mês e é difícil cortar (moradia, assinaturas, DAS)
Expenses:Variaveis:*               o que dá para controlar (mercado, restaurantes, transporte)
Assets:Reembolsos:<Empresa>        gastos que a empresa vai devolver
Assets:Transferencias              dinheiro que só muda de lugar entre contas suas
```

O Beancount não aceita acento em nomes de conta: `Educacao` aparece como "Educação" pelo mapeamento de nomes (`nomes:` em `accounts.yaml` mais os padrões em `app/fava_resumo/__init__.py`).

---

## Como o sistema pensa

1. **O gasto conta na data da compra** (competência), não na data em que a fatura é paga.
2. **Pagar a fatura não é gasto.** O dinheiro sai da conta e abate a dívida do cartão (passivo).
3. **Transferência entre contas suas** (PJ → PF, Pix para si mesmo) passa por `Assets:Transferencias`. Não é receita nem despesa, e o saldo dessa conta deve ficar perto de zero. Se não ficar, está faltando o extrato de alguma conta.
4. **Cada parcela conta no mês dela.** As parcelas futuras entram na previsão e no ciclo, na fatura certa.
5. **Os saldos são conferidos com o banco** (`balance`) dia a dia; se não bater, o `./finance check` acusa.
6. **Reembolso não é receita.** Um gasto reembolsável vira valor a receber da empresa, e o que a empresa paga acima do salário base quita esses valores.
7. **Ciclo**: começa depois dos vencimentos (por padrão, dia 16 → 15). Uma compra no cartão sai do caixa no ciclo em que a fatura vence. A meta de investir é calculada sobre o salário, sem reembolsos.

---

## Estrutura do código

```
finance                  atalho: cria o .venv e chama app.cli
requirements.txt
app/
  paths.py               onde ficam o código e os dados (FINANCE_DATA / dados/)
  cli.py                 ./finance [build|check|init|exemplo]
  organize.py            inbox → statements/ (reconhece, renomeia, descarta duplicados)
  parsers.py             leitura de cada formato (CSV Inter/Cora/Nubank, PDF da fatura Inter, OFX)
  build.py               statements/ → ledger/imported.beancount (regras, transferências, parcelas, saldos)
  forecast.py            previsão: médias, plano, parcelas futuras, assinaturas, metas
  cycles.py              ciclo atual e próximos (faturas, o que entra, o que vence)
  assinaturas.py         detecta cobranças recorrentes
  comprovantes.py        liga arquivos de comprovante aos gastos
  nfse.py                lê as notas fiscais (XML) do MEI
  diasuteis.py           feriados e próximo dia útil
  fava_resumo/           extensão do Fava: uma classe por aba + templates/ + um .js por aba
exemplo/                 pasta de dados fictícia (./finance exemplo); base para ./finance init
```

---

## Adicionar um banco novo

- **Se o banco exporta OFX:** baixe um arquivo, veja o número da conta (`<ACCTID>`) e adicione em `ofx_contas` no `accounts.yaml`, com `conta`, `tipo`, `pasta` e `nome`. Use `cartao: true` para cartão de crédito.
- **Se é CSV ou PDF:**
  1. escreva o reconhecedor (`is_...`) e o parser em `app/parsers.py`, e registre os dois na lista usada pelo `detect()`;
  2. adicione a fonte em `sources` no `accounts.yaml`;
  3. se quiser o passo a passo de download na aba Importar, adicione a fonte em `FONTE_NOMES`, em `app/fava_resumo/__init__.py`.

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `pasta de dados não encontrada` | Rode `./finance init`, ou crie o link `dados` para a sua pasta (veja a seção do iCloud). |
| `Operation not permitted` no iCloud | Dê **Acesso Total ao Disco** ao Terminal (Ajustes do Sistema → Privacidade e Segurança). |
| Mudei um template/JS e não aparece | O Fava guarda os templates em cache: pare (Ctrl+C) e rode `./finance` de novo. |
| Saldo não confere (`check` acusa) | Falta um extrato no período ou há um lançamento manual errado. Veja a aba Contas. |
| Muita coisa em "A revisar" | Crie regras na aba Pendências ou em `rules.yaml`. |
| Arquivos "… 2.yaml" no iCloud | Conflito de edição em dois Macs: compare, fique com o certo e apague o outro. |
