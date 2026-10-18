# Design: scaffolds dos três projetos finais

**Data:** 2026-10-18  
**Status:** aguardando revisão do usuário  
**Escopo:** criar bases de código e datasets sintéticos para os três modelos descritos em `projeto-final.md`.

## Contexto e objetivo

O repositório contém o material do curso, mas ainda não contém aplicações iniciais nem os datasets mencionados pelo projeto final. O objetivo é adicionar três exemplos didáticos, separados e executáveis, para que cada grupo possa escolher um modelo e evoluí-lo. As aplicações devem demonstrar o fluxo Dados → IA → Pandas → Streamlit, sem tentar ser produtos completos.

A versão atual de `projeto-final.md` contém alterações locais do usuário. Ela será tratada como fonte de requisitos e não será sobrescrita nem revertida.

## Organização

Criar três diretórios independentes em `projetos/`:

```text
projetos/
├── analista-feedback/
│   ├── app.py
│   ├── pipeline.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   ├── README.md
│   └── data/
│       ├── reviews_loja.csv
│       └── produtos.csv
├── auditor-gastos/
│   ├── app.py
│   ├── pipeline.py
│   ├── schemas.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   ├── README.md
│   └── data/recibos/
│       └── arquivos .txt e .pdf de exemplo
└── guru-manuais/
    ├── app.py
    ├── pipeline.py
    ├── requirements.txt
    ├── .env.example
    ├── .gitignore
    ├── README.md
    └── data/manual_sintetico.pdf
```

Cada diretório mantém seu próprio `requirements.txt` e instruções de execução para poder ser copiado/adaptado como projeto independente. As dependências serão específicas ao modelo, reaproveitando as bibliotecas já usadas pelo curso. O `requirements.txt` da raiz permanece disponível para as aulas existentes. O `README.md` da raiz receberá somente um índice curto apontando para os três exemplos, sem reescrever o conteúdo do curso.

`schemas.py` será usado onde há extração estruturada com Pydantic (modelos 1 e 2). O Guru dos Manuais não terá um schema artificial: seu pipeline organiza extração de páginas, chunks, recuperação e resposta com fontes.

## Dados sintéticos

Todos os dados serão inventados, identificados como exemplos sintéticos nos READMEs, e incluídos no repositório para permitir experimentar com os arquivos sem prepará-los manualmente. As chamadas de IA continuarão exigindo uma chave de API.

### Analista de Feedback

- `reviews_loja.csv` terá aproximadamente 300 linhas e as colunas `id`, `data`, `id_produto`, `nota` e `comentario`.
- `produtos.csv` terá produtos suficientes para cruzar as avaliações, com `id_produto`, `nome`, `categoria` e `preco`.
- Os exemplos cobrirão datas em formatos mistos, notas ausentes e textuais (incluindo `cinco` e `4,5`), comentários vazios, duplicatas exatas e quase duplicatas, emojis, ironia e alguns comentários em inglês.

### Auditor de Gastos

- A pasta conterá cerca de 25 recibos `.txt` e `.pdf`, misturando layouts de supermercado, transporte, restaurante e conta doméstica.
- Haverá valores no formato brasileiro, datas variadas, itens com quantidade, gorjeta/taxas, pelo menos dois recibos duplicados em arquivos/layouts distintos e alguns arquivos incompletos ou sem texto extraível.
- A amostra problemática será válida como arquivo sempre que possível, para exercitar falhas de extração/validação sem comprometer a leitura do restante da pasta.

### Guru dos Manuais

- `manual_sintetico.pdf` terá 20 páginas de conteúdo fictício, mas coerente, sobre regras de um jogo/manual.
- O texto será distribuído por página de modo que perguntas sobre regras específicas tenham respostas e fontes verificáveis. O material não usará conteúdo protegido de terceiros.

## Responsabilidades dos módulos

### Modelo 1: Analista de Feedback

- `pipeline.py`: carregar e limpar os CSVs, normalizar datas/notas, documentar um critério simples de duplicatas quase iguais, cruzar reviews e produtos, chamar a API com saída validada por Pydantic, limitar tentativas e registrar falhas/contradições entre nota e sentimento. Transformar aspectos em linhas e produzir agregações por produto/categoria/aspecto/sentimento.
- `schemas.py`: modelos para sentimento, idioma, urgência e lista de aspectos, usando categorias e sentimentos definidos.
- `app.py`: uploads dos dois CSVs, métricas/gráficos e tabela filtrável com comentário original e resultados.
- Desafios extras do enunciado ficam fora do escopo inicial.

### Modelo 2: Auditor de Gastos

- `pipeline.py`: ler individualmente TXT e PDF, capturar erro por arquivo sem interromper o lote, extrair dados estruturados, validar datas/valores/soma de itens e limitar tentativas. Consolidar em DataFrame, sinalizar duplicatas, agrupar por categoria/mês e explodir itens para ranking.
- `schemas.py`: estabelecimento, data, itens (descrição, quantidade, valor), total e categoria fechada.
- `app.py`: upload múltiplo, tabela e métricas de gastos, gráfico por categoria e lista legível de arquivos com falha/inconsistência.
- Insights com segunda chamada ou orçamento configurável ficam fora do escopo inicial.

### Modelo 3: Guru dos Manuais

- `pipeline.py`: extrair texto página a página do PDF, limpar quebras/cabeçalhos simples, formar chunks com sobreposição e preservar as páginas de origem; gerar embeddings e recuperar contexto via ChromaDB; responder com contexto e fontes, mantendo limites de tokens e parâmetros explícitos.
- O system prompt instrui o modelo a usar somente o contexto recuperado e a declarar quando a resposta não estiver no documento.
- `app.py`: upload de PDF, pergunta em chat/texto, resposta, trechos/páginas utilizados e histórico tabular com pergunta, fontes/páginas e tokens quando retornados pela API.
- Comparação de tamanhos de chunk fica fora do escopo inicial.

## Configuração, segurança e falhas

- Usar OpenAI como provedor inicial, coerente com as dependências já presentes no repositório; nomes de modelos ficam configuráveis por variáveis de ambiente documentadas em `.env.example`.
- Nunca incluir uma chave real nos exemplos. Os `.gitignore` da raiz e dos três projetos ignorarão ambientes virtuais, arquivos `.env`, caches Python e dados locais do ChromaDB, sem ignorar os datasets de exemplo.
- As chamadas de IA terão `temperature`, `max_tokens` e limite pequeno de tentativas explícitos. Exceções de API, leitura de arquivo, parsing ou validação serão apresentadas como problemas por registro/arquivo, sem descartar resultados válidos do restante do lote.
- A interface avisará quando faltar chave de API e explicará como configurar o ambiente, em vez de falhar com traceback.

## Documentação e verificação

Cada projeto documentará problema, conteúdo sintético, configuração da chave, dependências e comando `streamlit run app.py`. Cada README terá um pequeno gabarito de demonstração verificado manualmente: interpretação de exemplos conhecidos no modelo 1, campos/total de um recibo no modelo 2 e uma pergunta com resposta/páginas esperadas no modelo 3. O índice da raiz apontará para esses guias.

A verificação incluirá, no mínimo:

1. conferir as quantidades/colunas e os casos especiais dos datasets;
2. testar funções determinísticas de limpeza, parsing, validação, chunking e agregação sem chamadas à API;
3. importar/compilar os módulos e confirmar que cada Streamlit app inicia até a checagem de configuração;
4. conferir que exemplos e arquivos de dados não contêm segredos e que o `.gitignore` cobre `.env` e artefatos locais.

Não serão feitas chamadas pagas à API durante os testes. Não será alterado o conteúdo de `projeto-final.md`.

## Critérios de aceite

- Existem três diretórios independentes e cada um segue o respectivo fluxo mínimo do enunciado.
- Cada pasta contém os arquivos de código, configuração, documentação e dados sintéticos especificados acima.
- Os dados exercitam casos normais e problemáticos, e o tratamento de um arquivo/registro ruim não impede o processamento dos outros.
- Os READMEs explicam instalação e execução; nenhuma chave é commitada.
- As funções de dados e os módulos podem ser verificados sem depender de uma chamada real à API.
