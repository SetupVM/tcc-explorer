# Projeto Final em Sala: IA na Prática 

## O Cenário: 3 Caminhos, 1 Entrega

Nas duas últimas aulas vocês vão construir um produto de dados completo: dados brutos entram, a IA trabalha, o Pandas organiza e o Streamlit mostra o resultado.

Para que dê tempo, o tema já vem definido. Cada grupo escolhe **um dos 3 modelos** abaixo. Todos usam as mesmas 4 camadas do desafio final (Dados, Cognitiva, Interface e Engenharia), com um **dataset fornecido** e **checkpoints** no roteiro.

Os projetos foram dimensionados para **2 aulas de 100 minutos, com uso de IA para programar liberado** (veja as regras na seção [Uso de IA](#-uso-de-ia-para-programar)).

**Grupos de até 3 pessoas.** 

---

## Os 3 Modelos

| | Modelo 1 | Modelo 2 | Modelo 3 |
|---|---|---|---|
| **Nome** | Analista de Feedback | Auditor de Gastos | Guru dos Manuais |
| **Entrada** | 2 `.csv` sujos (reviews + produtos) | Recibos em `.txt` e `.pdf`, com layouts diferentes | 1 `.pdf` longo (manual, regras, edital) |
| **IA (aulas)** | Structured Outputs aninhado (Aula 3) | Structured Outputs com lista de itens + validação (Aulas 3 e 6) | Mini-RAG com fontes (Aula 4) |
| **Pandas (aulas)** | Limpeza, `merge`, `explode`, `groupby` (Aula 5) | Consolidação, deduplicação, `explode`, `groupby` (Aulas 5 e 6) | Limpeza de texto + log de perguntas (Aulas 5 e 6) |
| **Saída no Streamlit** | Métricas, gráficos e drill-down nos comentários | Tabela de gastos, gráfico e lista de arquivos com problema | Chat com resposta, páginas e trechos usados |

---

## Modelo 1: O Analista de Feedback

**Problema:** uma loja online recebe centenas de reviews em texto livre e ninguém consegue ler tudo. O time precisa saber **o que os clientes elogiam e o que reclamam, por produto e por categoria**, e quais ações priorizar.

**Dataset fornecido:**
- `reviews_loja.csv` (~300 linhas): `id`, `data`, `id_produto`, `nota`, `comentario`.
- `produtos.csv`: `id_produto`, `nome`, `categoria`, `preco`.

A base está **suja**: datas em formatos misturados, notas nulas ou escritas como texto (`"cinco"`, `"4,5"`), comentários quase duplicados, comentários vazios, emojis, **ironia** (`"Ótimo, quebrou no segundo dia"`) e alguns textos em inglês.

**O que o sistema deve fazer:**

1. **Dados (Pandas):** ler os dois arquivos, limpar, definir um critério para duplicatas "quase iguais" e cruzar as bases com `merge`.
2. **IA (Aula 3):** para cada comentário, extrair com Pydantic um objeto **aninhado**: `sentimento_geral`, `idioma`, `urgente` e uma lista de `aspectos`, cada um com `aspecto` (entrega, preço, qualidade, atendimento ou outro) e `sentimento`.
3. **Confiabilidade:** validar a saída, reprocessar com número limitado de tentativas quando o parsing falhar e registrar o que não deu certo. Sinalizar os casos em que a nota numérica contradiz o sentimento extraído.
4. **Dados (Pandas):** transformar a lista de aspectos em linhas (`explode`) e gerar agregações, como produto × aspecto × sentimento e ranking de problemas por categoria.
5. **Interface (Streamlit):** upload dos dois CSVs, métricas, gráficos e tabela filtrável com acesso aos comentários originais.

**Desafio extra (escolham um):**
- Uma segunda chamada de IA que gera um **resumo executivo com ações recomendadas** a partir dos *dados agregados* (não dos 300 comentários, para controlar o custo).
- Botão para baixar o CSV enriquecido.
- Comparar dois *prompts* e mostrar qual acertou mais no gabarito.

---

## Modelo 2: O Auditor de Gastos

**Problema:** uma pessoa (ou pequena empresa) guarda dezenas de recibos e faturas em formatos diferentes e quer saber **para onde o dinheiro está indo**, com números em que dê para confiar.

**Dataset fornecido:** pasta `recibos/` com 20 a 30 arquivos `.txt` e `.pdf`, cada um com um layout diferente (supermercado com vários itens, app de transporte, restaurante com gorjeta, conta de luz).
Alguns recibos aparecem em dois arquivos com formatação diferente, valores vêm como `R$ 1.234,56`, as datas misturam formatos e há arquivos incompletos ou ilegíveis.

**O que o sistema deve fazer:**

1. **Dados (Aula 6):** ler todos os `.txt` e `.pdf` da pasta, sem que um arquivo ruim derrube o programa.
2. **IA (Aula 3):** extrair cada recibo para um objeto **aninhado** com `estabelecimento`, `data`, `itens` (lista com descrição, quantidade e valor), `valor_total` e `categoria` (lista fechada: alimentação, transporte, moradia, lazer, outros).
3. **Validação:** conferir se a soma dos itens bate com o `valor_total` (com tolerância definida pelo grupo), rejeitar datas inválidas e valores negativos, reprocessar com número limitado de tentativas e **listar os arquivos que falharam ou ficaram inconsistentes**.
4. **Dados (Pandas):** consolidar tudo, corrigir tipos, detectar duplicatas (mesmo estabelecimento, data e valor), gerar `groupby` por categoria e por mês e usar `explode` nos itens para montar um ranking dos mais caros.
5. **Interface (Streamlit):** upload múltiplo (`accept_multiple_files=True`), tabela de gastos, métricas, gráfico por categoria e lista de problemas.

**Desafio extra (escolham um):**
- *Insights* do mês (por exemplo, onde há espaço para cortar gastos) gerados por uma segunda chamada de IA a partir da *tabela agregada*, sem reenviar os recibos.
- Orçamento mensal por categoria, com alerta quando o gasto ultrapassar o limite.

---

## Modelo 3: O Guru dos Manuais

**Problema:** manuais, regulamentos e editais são longos e ninguém os lê inteiros. Queremos um assistente que **responda perguntas com base no documento**, sem inventar.

**Dataset fornecido:** 1 PDF de 20 a 40 páginas (regras de um jogo de tabuleiro, manual de um equipamento ou edital). O grupo pode trocar por outro PDF de interesse.

**O que o sistema deve fazer:**

1. **Dados (Aula 6 + Pandas):** extrair o texto do PDF página a página, limpar (cabeçalhos repetidos, quebras de linha, espaços) e dividir em *chunks* com um pouco de sobreposição, guardando a **página de origem** de cada um.
2. **IA (Aula 4):** gerar embeddings dos chunks, guardar no ChromaDB, buscar os trechos mais próximos da pergunta e montar o prompt com esse contexto. O *system prompt* deve mandar responder **somente com base no contexto** e dizer "não encontrei no documento" quando for o caso.
3. **Confiabilidade:** tratar falhas de API e perguntas fora do escopo do documento sem quebrar o app.
4. **Dados (Pandas):** registrar cada pergunta num DataFrame (pergunta, trechos usados, páginas, tokens) e exibir esse histórico na tela.
5. **Interface (Streamlit):** upload do PDF, campo de pergunta (`st.text_input` ou `st.chat_input`), resposta e os trechos usados como fonte, com a página de cada um.

**Desafio extra:** comparar dois tamanhos de *chunk* (por exemplo, 500 e 1000 caracteres) e mostrar qual acerta mais no gabarito.

---

## Requisitos Mínimos (valem para os 3 modelos)

**Dados**
- Lê pelo menos uma fonte externa (CSV, TXT ou PDF).
- Faz pelo menos uma limpeza e uma agregação ou filtro com Pandas.

**IA**
- Chamadas à API (OpenAI ou Gemini) com `temperature` e `max_tokens` definidos.
- Um *system prompt* escrito pelo grupo.
- Tratamento de erro para falha de API e de parsing, com número limitado de tentativas.

**Interface**
- App em Streamlit com entrada do usuário (upload ou pergunta) e resultado visual.
- Código organizado em funções.

**Engenharia**
- Repositório público no GitHub, sem chave de API (`.env` no `.gitignore`).
- `requirements.txt` completo.
- `README.md` com: o problema que resolve, como usar, como rodar (`git clone`, `pip install`, `streamlit run`) e o resultado do gabarito.

---

## Regras de Custo e Segurança (importante em sala)

- Sempre defina `max_tokens`. Chamadas dentro de loop sem limite estouram o orçamento rápido.
- **Nunca** coloque a chave no código nem faça commit do `.env`.
- Evitem chamar a API de novo para o mesmo dado: guardem o resultado em variável ou arquivo.
- Limitem as tentativas de reprocessamento (2 ou 3). Um *retry* sem limite é um custo sem limite.

---

## Uso de IA para programar

Vocês **podem e devem** usar IA (ChatGPT, Gemini, Claude, Copilot etc.) para escrever código. O foco da avaliação é o produto funcionando e o **entendimento** do que foi construído. As regras:

1. **Entenda o que entrou no projeto.** Na demo, vou sortear um integrante para explicar um trecho do código. "A IA que escreveu" não é resposta.
2. **Nunca cole a chave de API** em prompts, chats ou prints. Mandem só o trecho do código, sem o `.env`.
3. **Escrevam e revisem o *system prompt* do app.** Ele é a parte do projeto que mais depende do entendimento do grupo.
4. **Desconfie do que a IA gera.** Rodem, leiam e testem. Confiram com o que era realmente esperado, também vou conferir.
5. **Estrutura boa.** O código deve ser feito com boas práticas, organizados devidamente em funções.

Dicas para render mais:
- Peça **uma camada por vez** (primeiro os dados, depois a IA, depois a interface) e funções pequenas.
- Cole o **erro completo** quando algo quebrar.
- Informe a estrutura de arquivos sugerida abaixo, para o código vir organizado.

---

**Estrutura sugerida de arquivos:**

```
meu-projeto/
├── app.py            # interface Streamlit
├── pipeline.py       # funções de Pandas e de IA
├── schemas.py        # modelos Pydantic (Modelos 1 e 2)
├── avaliacao.py      # roda o gabarito e calcula o acerto
├── requirements.txt
├── .gitignore        # inclui .env
└── README.md
```

---

## Apresentação

Pra mostrar o projeto, quero que vocês expliquem o que fizeram, mostrando uma demo na hora.

---

**Entrega:** link do repositório público no GitHub.

