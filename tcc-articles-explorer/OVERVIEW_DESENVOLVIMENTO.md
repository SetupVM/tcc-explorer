# Explorador de Artigos — overview do desenvolvimento

Projeto final do curso *IA na Prática* (Instituto Mauá). Aplicação local em
Streamlit que importa PDFs de artigos científicos escolhidos pelo estudante,
extrai a estrutura com Docling, organiza um catálogo com Pandas, indexa trechos
no ChromaDB e responde perguntas em português com citações de artigo e página,
além de sugerir recortes de TCC.

Pasta de entrega: `tcc-explorer/tcc-articles-explorer/`.
Origem do desenvolvimento: `ia-na-pratica/explorador-de-artigos/` (antes `literatura-cientifica/`).
Histórico verificado em 25/10/2026: funcional, testado, **nada commitado no Git ainda**.

---

## 1. Resumo

- O MVP pedido foi entregue por completo: importação → extração → catálogo → índice → respostas com evidências → sugestões de TCC, em 3 áreas de interface.
- Depois de usar o app com 9 artigos reais, o usuário pediu melhorias. Elas viraram uma etapa de **pós-processamento que roda sem o Docling**: une parágrafos entre páginas, recupera texto perdido, faz uma segunda leitura das fórmulas com o Dolphin-1.5, descreve figuras com um modelo de visão local (Ollama) e preenche título, autores, ano, DOI e tema a partir do próprio PDF.
- Cada escolha de modelo foi feita **medindo**: embeddings (bge-m3 venceu e5-small/base) e leitores de fórmula (Dolphin-1.5 venceu Docling, LaTeX-OCR e Qwen2.5-VL).
- MinerU 4.0.12 foi acrescentado como terceira leitura opcional de fórmulas, por páginas escolhidas. Roda em ambiente separado, Basic/ONNX na CPU, com modelos locais; não muda automaticamente a versão escolhida pelo usuário. Ainda não participa do benchmark de qualidade dos artigos reais.
- 283 testes verificados após a integração do MinerU: 272 gerais e 11 de integração com Docling, Dolphin e bge-m3 reais. MinerU também executado localmente em PDF sintético de duas páginas: 1 fórmula encontrada em 13,8 s, cache reutilizado e associação correta com a caixa do Docling (IoU 0,7695). O catálogo real registra 9 artigos, 319 páginas e 1.107 trechos; não foi reprocessado nesta rodada.
- Após a auditoria, os exemplos e notebooks do curso foram sanitizados; `.env` reais foram preservados. A revogação de eventuais chaves ativas continua dependendo do titular. Nada do app está versionado; as respostas do RAG com `gpt-4o-mini` ainda não foram avaliadas.

---

## 2. Como rodar

Cópia de entrega preparada em 30/10/2026, sem ambientes, caches, credenciais ou banco.
O README contém a sequência completa de primeiro uso no novo clone.
As contagens da biblioteca e os benchmarks abaixo descrevem o ambiente de
desenvolvimento, não uma base pré-carregada na entrega.

```bash
cd tcc-articles-explorer
python -m venv .venv && source .venv/bin/activate     # Python 3.11/3.12 (testado 3.12.2)
pip install -r requirements.txt
python scripts/baixar_modelos.py                       # Docling, bge-m3, Dolphin (~4 GB, uma vez)
cp .env.example .env                                   # preencher OPENAI_API_KEY
streamlit run app.py
```

- Opcional: Ollama com `qwen2.5vl:7b` para descrever figuras (o usuário já tem).
- Opcional: MinerU em `.venv-mineru`, dependências em `requirements-mineru.txt` e modelos em `.cache/mineru`. Instalação e download descritos na seção **MinerU** do README; `MINERU_PYTHON`, `MINERU_HOME` e `MINERU_TIMEOUT` são configuráveis. O app exige os modelos já locais.
- Testes: `pip install -r requirements-dev.txt`, depois `pytest -m "not docling"` (cerca de 2 s) ou `pytest` (cerca de 1 min).
- Depois de mudar o código, é preciso **reiniciar** o Streamlit (veja a seção 7).

---

## 3. Arquitetura

```
app.py                      Streamlit: navegação (3 áreas) e barra lateral
interface/
  comum.py                  recursos em cache, desenho das caixas na página, opções de melhoria
  pagina_importar.py        área 1: upload, situação, metadados, inspeção (Texto, Tabelas, Fórmulas, Figuras, Página do PDF, Arquivos)
  pagina_biblioteca.py      área 2: filtros, tabela, gráficos, groupby, CSV, "Melhorar todos"
  pagina_perguntar.py       área 3: pergunta, resposta com evidências, sugestões de TCC
explorador/
  config.py                 variáveis de ambiente (.env)
  armazenamento.py          validação de PDF, SHA-256, PDF original, render de página
  extracao.py               ÚNICO módulo que usa o Docling; manifesto, alertas, caixas
  pos_processamento.py      colunas, marcas d'água, parágrafos entre páginas, texto perdido, caixas por página
  formulas.py               limpeza do LaTeX, recorte, segunda leitura (Dolphin), concordância
  mineru.py                 subprocesso opcional, cache, validação Middle JSON e associação geométrica
  figuras.py                descrição de figuras via Ollama (SDK da OpenAI com outro base_url)
  metadados.py              título, autores, ano, DOI e tema (LLM com validação + identificadores)
  catalogo.py               Pandas: normalização, duplicatas, filtros, agregações, CSV
  trechos.py                chunking (seções, fórmulas com contexto, tabelas com cabeçalho repetido)
  indice.py                 ChromaDB persistente + embeddings locais
  respostas.py              prompts, Structured Outputs, validação de citações
  biblioteca.py             orquestra importar → extrair → melhorar → indexar
scripts/  baixar_modelos.py, avaliar_rag.py, mineru_worker.py (SDK no ambiente separado)
tests/    pytest + pdfs_sinteticos.py (gera artigos fictícios de 2 colunas)
dados/    catalogo.csv, pdfs/<sha256>.pdf, extracoes/<id>/, chroma/   (fora do Git)
```

### Arquivos por artigo (`dados/extracoes/<id>/`)

- `documento.json` (DoclingDocument completo), `documento.md` e `imagens/` (figuras e recortes de fórmulas).
- `elementos.json`: lista na ordem de leitura. É **a fonte para todo o resto**.
- `manifesto.json`: versão do Docling, configuração, status, alertas, cobertura, cabeçalhos e rodapés.
- `mineru/`: cache das páginas comparadas; o manifesto recebe `formulas_mineru`, com associações, ambiguidades e leituras sem correspondência.

### Campos de um elemento

- Gerais: `id` (posição na ordem do Docling, `e0000`), `tipo`, `texto`, `secao`, `paginas`, `caixa` (1ª página) e `caixas` (todas as páginas).
- Tipos: `titulo`, `secao`, `texto`, `lista`, `formula`, `tabela`, `figura`, `nota`, `codigo`, `legenda`, `texto_pdf` (recuperado do PDF), `marca_dagua`.
- Tabela: `colunas`, `linhas`, `legenda`, `caixas_legenda`.
- Figura: `imagem`, `legenda`, `texto_interno`, `descricao` e `descricao_modelo` (descrição automática).
- Fórmula: `latex` (versão usada), `latex_fonte` (docling, dolphin, mineru ou manual), `latex_revisado` (escolha explícita), `latex_docling`, `latex_dolphin`, `latex_mineru`, `concordancia`, `numero`, `imagem` (recorte). MinerU preserva também saída original, modelo/versão e caixa normalizada.
- Parágrafo unido entre páginas: `unido_com` (ids incorporados).

### Catálogo (`catalogo.csv`)

- `id` (12 primeiros caracteres do SHA-256), `arquivo_original`, `sha256`.
- `titulo`, `autores`, `ano`, `doi`, `tema`, cada um com uma coluna `*_origem` (Docling, LLM, arXiv, nome do arquivo, informado, usuário).
- `palavras_chave`, `paginas`, `data_importacao`.
- `status_extracao`, `status_indexacao`, `qualidade_verificada`, `metadados_revisados`.
- `n_trechos`, `modelo_indexacao`, `config_extracao`.

### Trecho no ChromaDB

- id estável `<artigo>-<nnnn>`.
- Metadados: `artigo_id`, `titulo`, `secao`, `paginas` ("3,4"), `pagina_inicial`, `pagina_final`, `tipo` (texto, texto_com_formula, tabela, figura, texto_pdf), `imagem`.
- A coleção guarda a assinatura `modelo|trechos-vN`. Se o modelo de embeddings mudar, a busca é bloqueada até recriar o índice.

---

## 4. Fluxo

1. **Importar.** Valida o PDF (vazio, assinatura `%PDF`, protegido por senha, tamanho, número de páginas) e calcula o SHA-256. O mesmo conteúdo com outro nome é reconhecido como duplicado e não é reprocessado. O PDF original é salvo byte a byte.
2. **Extrair (Docling 2.133).** OCR automático só onde não há camada de texto, TableFormer no modo preciso, `do_formula_enrichment` e recorte das figuras. Gera o manifesto e reaproveita uma extração válida feita com a mesma configuração.
3. **Pós-processar** (`pos_processamento.py`, pode ser reaplicado sem o Docling):
   - corrige a ordem de leitura em páginas de duas colunas;
   - marca as marcas d'água;
   - une parágrafos que continuam na página seguinte;
   - trata título e seções;
   - mede a cobertura e recupera o texto perdido;
   - grava as caixas de todas as páginas.
4. **Melhorar.** Segunda leitura das fórmulas (Dolphin-1.5), descrição das figuras (Ollama) e metadados (LLM e identificadores).
5. **Indexar.** Divide em trechos e gera embeddings (bge-m3) no ChromaDB. Reindexar substitui os trechos do artigo, sem duplicar. Extrações que falharam ou estão vazias são bloqueadas; parciais exigem confirmação.
6. **Responder.** Busca semântica (opção de trazer trechos de cada artigo) → `chat.completions.parse` com Pydantic → validação das citações → referências montadas a partir do catálogo.

---

## 5. Decisões técnicas e evidências

- **Ambiente.** `.venv` próprio do app, para não alterar o `.venv` do curso. Versões fixadas em `requirements.txt` e ambiente completo em `requirements-lock.txt`.
- **`rapidocr==3.9.2` fixado.** A 3.10.0 (resolvida pelo pip) não expõe `PP_OCRV6_LANGS`, e o Docling 2.133 então **desliga o OCR sem erro visível** ("No OCR engine found" só aparece no log).
- **Ordem de leitura.** Com uma linha de autores centralizada, o preditor do Docling leu a coluna direita antes da esquerda. Correção conservadora: detecta a inversão por página e reordena só essas páginas, com alerta. Validada apenas com PDFs sintéticos (os artigos reais eram de coluna única ou não tiveram inversão).
- **Embeddings.** 8 perguntas em português sobre artigos sintéticos em inglês, contando o trecho certo no top 3:

  | Modelo | Acertos | Tamanho |
  |---|---|---|
  | e5-small | 6/8 | 0,5 GB |
  | e5-base | 6/8 | 1,1 GB |
  | **bge-m3** (escolhido) | **7/8** | 2,3 GB |

  Nos artigos reais (`avaliacao/perguntas_artigos_reais.csv`), a busca acertou 7/7 no top 8.
- **Chunking.**
  - Os trechos não atravessam seções e têm no máximo 1.200 caracteres.
  - A fórmula fica com o parágrafo anterior e o seguinte.
  - Tabelas grandes são divididas repetindo o cabeçalho.
  - Referências e linhas de autores ficam fora do índice.
- **RAG.**
  - Os trechos vão ao modelo rotulados T1…Tn entre marcas `<trecho>`; o texto do PDF é neutralizado contra *prompt injection*.
  - A saída é JSON validado por Pydantic. Citações inexistentes são descartadas e avisadas, e uma afirmação "do artigo" sem citação válida é marcada.
  - A resposta separa "relatado nos artigos" de "sugestão do assistente".
- **Fórmulas.** Benchmark com 25 fórmulas reais, das quais 6 com gabarito (*Attention*):
  - Docling: errou `d_model` e `step_num`;
  - LaTeX-OCR: "Atention", `1000` em vez de `10000`, além de dependências antigas;
  - Qwen2.5-VL: às vezes devolve um documento LaTeX inteiro;
  - **Dolphin-1.5 acertou 6/6**, em 1,7 s por fórmula na CPU, sem dependência nova.

  Por isso o Dolphin faz a segunda leitura. O limite de concordância é 0,97, porque o erro de `d_model` dava 0,94. Quando as leituras divergem, as duas vão para o índice e a interface mostra o recorte para o usuário escolher ou editar. O LaTeX do Docling é limpo (`A t t e n t i o n` → `Attention`), preservando `\text{}` e o espaço depois de comandos.
  Com MinerU, a comparação considera todos os pares disponíveis. A associação exige sobreposição geométrica única na mesma página; caixas ambíguas ou inexistentes ficam no relatório, sem inclusão automática no índice. Antes da revisão, alternativas divergentes entram no RAG identificadas por fonte e com aviso de incerteza; após escolha explícita, apenas a escolhida entra. Concordância não comprova correção e não há votação entre leitores.
- **Figuras.** `qwen2.5vl:7b` via Ollama, cerca de 6 s por figura. A descrição entra no trecho marcada como "descrição automática; não é texto do artigo", e o prompt do RAG proíbe apresentá-la como resultado dos autores.
- **Metadados (ordem de confiança).**
  - DOI impresso.
  - Carimbo do arXiv na camada de texto (ano da 1ª versão e DOI `10.48550/arXiv.<id>`).
  - Nome do arquivo (`2407.17866v2.pdf`, `ssrn-<id>.pdf`).
  - LLM: autores e ano só são aceitos se aparecerem no texto; o título do Docling é mantido, a menos que pareça errado; tema de uma lista fechada de 16 áreas.
  - Sem chave, o tema vem da similaridade de embeddings.
  - O preenchimento automático preserva valores digitados e palavras-chave existentes. A opção explícita de substituir temas, na melhoria em lote, continua disponível.
- **Caixas na página.**
  - Antes só se guardava a 1ª caixa de cada elemento, e a medição mostrou 0 de 85 legendas e 0 de 100 elementos multipágina com caixa.
  - Agora são guardadas todas (recuperadas do `documento.json`) e desenhadas: "N leg." para a legenda, "N…" para a continuação, e cabeçalho e rodapé em cinza.
  - A tela mede o texto do PDF fora de qualquer caixa: 0% nos 8 artigos digitais e cerca de 13% no escaneado de 1910.
- **Custo.**
  - Toda ação cara depende de um botão explícito; Docling, índice e Dolphin ficam em `st.cache_resource`.
  - A mesma pergunta com o mesmo contexto não é reenviada na sessão. O cache identifica conteúdo, páginas, títulos, prompts e parâmetros do modelo, não apenas IDs dos trechos.
  - Só a pergunta, os trechos recuperados e o início do artigo (para os metadados) vão para a OpenAI.

---

## 6. Linha do tempo

1. **MVP.**
   - Módulos, interface, testes e documentação: README, ROTEIRO_DEMO (5–7 min), `.env.example`, `.gitignore`.
   - Conferência visual com 2 PDFs reais, que revelou expoentes perdidos em tabela, célula mesclada duplicada e rótulo de figura virando seção.
   - Bug da ordem de duas colunas e incompatibilidade do rapidocr corrigidos.
2. **Feedback com 9 artigos reais** (parágrafos partidos, fórmulas erradas, tema, imagens).
   - Diagnóstico com medição: parágrafos partidos quando havia uma figura no topo da página; cobertura de 87–99,8%; LaTeX espaçado; título errado em capa do JSTOR.
   - Benchmark dos leitores de fórmula e implementação das melhorias.
   - Aplicação na biblioteca real (seção 7).
3. **Temas.** O usuário pediu para substituir os temas de teste: inferidos com `gpt-4o-mini` para os 9.
4. **Autores, ano e DOI.** Preenchidos para 9, 9 e 8 dos 9 artigos (o de 1910 não tem DOI impresso). Corrigidos os acentos soltos do PDF ("St˛epie´n" → "Stępień") e a marca de rodapé no fim do título ("IMAGINATION1").
5. **Caixas.** Legendas, continuações e cabeçalhos ficaram visuais, com a medição de texto fora das caixas.
6. **Correções da auditoria (25/10/2026).** Preservados argumentos numéricos de fórmulas e parágrafos científicos antes confundidos com marcas d'água; adicionada migração do pós-processamento v4. Cache passa a considerar o conteúdo, a busca exclui artigos desatualizados e respeita o limite escolhido. Reindexação calcula vetores antes de gravar e tenta restaurar o índice anterior em falhas. Revisão de qualidade acompanha alterações na extração; o preenchimento preserva campos manuais e funciona mesmo com inferência automática desligada. Exemplos/notebooks sanitizados, regressões com AppTest e três telas verificadas em dados temporários. Streamlit reiniciado após as correções. Nenhuma chamada real de inferência foi feita nesta rodada.
7. **Terceira leitura de fórmulas (25/10/2026).** MinerU 4.0.12/DocVortex 0.6.1 instalados em `.venv-mineru`, com modelos Basic/ONNX locais verificados. A aba Fórmulas permite comparar qualquer página, exibe até três leituras e preserva escolhas explícitas. Worker separado, cache por conteúdo/configuração e associação conservadora por posição. Testes de contrato, persistência e interface, mais execução local real em PDF sintético. Nenhuma chamada a API externa de inferência; PDFs e índice da biblioteca real preservados.

---

## 7. Problemas encontrados e lições

- **Streamlit com código antigo.** Um app iniciado antes de uma mudança de código continua com os módulos antigos em memória: deu `ImportError` e, pior, poderia salvar o catálogo sem as colunas novas. **Sempre reiniciar o app após mudar o código.**
- **Índice ChromaDB corrompido.** O script de melhorias e o app reiniciado gravaram no mesmo `dados/chroma` ao mesmo tempo, e qualquer processo novo caía ao abrir o índice (segfault, código 139). O índice foi reconstruído a partir das extrações (1.107 trechos, verificado) e trocado com o app parado. **Nunca dois processos gravando em `dados/`.**
- **LLM pequeno.** O `llama3.2` local (usado para testar o fluxo sem a chave do usuário) escolheu temas piores que a similaridade de embeddings e ignorou a regra sobre descrições automáticas. A qualidade com `gpt-4o-mini` só foi observada na inferência de metadados.
- **Validação "está no texto" não basta para o título.** Um LLM devolveu um aviso de direitos como "título". Por isso o título do Docling tem prioridade.
- **Leitura com limite de caracteres.** Uma métrica de semelhança frouxa (0,9) deixava passar um erro de uma palavra. O limite foi calibrado com o caso real.

---

## 8. Desvios em relação ao pedido original (todos a pedido do usuário)

- **Metadados.** O pedido dizia "não inventar autores/ano/DOI". Hoje eles são preenchidos, mas só a partir do texto ou de identificadores, com a origem registrada. O DOI do arXiv identifica a versão do arXiv, não a publicação final.
- **Interpretação de figuras.** Era "evolução futura" e foi implementada como opcional (Ollama local), com a descrição marcada como automática.
- **Tema.** Era "informado pelo usuário" e agora é inferido de uma lista fechada; o usuário pode editar, e a edição passa a prevalecer.

---

## 9. Verificado × não verificado

**Verificado**
- 272 testes gerais e 11 de integração passando após adicionar MinerU.
- MinerU Basic/ONNX real, sem API: fórmula de PDF sintético reconhecida, cache reutilizado e associação com Docling/Dolphin conferida. Essa conferência é separada dos testes rápidos com dublês.
- Pipeline real em 9 PDFs.
- Busca: 7/7 nos sintéticos e 7/7 nos reais.
- Interface testada no navegador e com `AppTest`: importação com duplicata e PDF inválido, inspeção, biblioteca, busca sem LLM, escolha de fórmula, página com caixas.
- Fluxo de pergunta com um LLM real local (`llama3.2`).
- Metadados com `gpt-4o-mini` (cerca de 27 chamadas pequenas com a chave do usuário).

**Não verificado**
- Respostas do RAG e sugestões de TCC com `gpt-4o-mini`. Falta rodar `python scripts/avaliar_rag.py avaliacao/perguntas_artigos_reais.csv --llm`, que inclui 2 perguntas sem resposta.
- Correção de duas colunas em artigos reais (só testada com sintéticos).
- Qualidade das 55 descrições de figuras além de uma amostra.
- As 28 fórmulas divergentes (de 93) ainda não foram revisadas pelo usuário.
- Ganho de precisão do MinerU nos artigos reais: a primeira validação usa um PDF sintético com fórmula conhecida. O modo Basic não garante detectar toda fórmula; fórmulas inline sem caixa própria não são associadas automaticamente.

---

## 10. Pendências e próximos passos

- **Segurança.**
  - Chaves aparentes foram removidas de `dev/.env.example` e dos notebooks `aula2`, `aula3` e `aula4`, inclusive das saídas. Os exemplos usam variáveis de ambiente e não imprimem o valor da chave. Se as credenciais removidas estiverem ativas, o titular deve substituí-las; a auditoria não validou as chaves nem comprovou publicação.
  - O `.env` da raiz usa o nome `OPEN_AI_API_KEY`; o app lê `explorador-de-artigos/.env` com `OPENAI_API_KEY`.
- **Git.** O app inteiro está sem commit. O curso exige um repositório público com README e `requirements.txt` (ambos prontos). `notebooks/testes_extracao/`, ambientes virtuais e caches locais agora estão no `.gitignore`; o destino público ainda precisa ser definido.
- **Aplicar correções às extrações existentes.** O pós-processamento v4 sinaliza a necessidade de *Melhorar* e reindexar. Reavalia marcas d'água e recupera fórmulas do texto original do Docling, sem apagar escolhas manuais. Leituras Dolphin antigas sem saída original precisam de revisão se houver erro. A biblioteca real não foi alterada durante as correções.
- **Limpeza.** `dados/backup_antes_melhorias_2026-10-21/` (105 MB, ignorado pelo Git) pode ser apagado quando o usuário estiver satisfeito.
- **Avaliação.** Rodar a avaliação com `--llm` e testar as sugestões de TCC antes do Demo Day.
- **Revisão.** Revisar as fórmulas divergentes (a aba Fórmulas já filtra por elas) e conferir os temas.
- **Arquivo pendente.** `artigos/ssrn-4501707.pdf` ainda não foi importado.
- **Evoluções possíveis.**
  - Dolphin como extrator de página inteira (alternativa ao Docling).
  - Busca híbrida (BM25 + embeddings).
  - Avaliação automática de fidelidade.
  - Recorte de fórmula ampliado quando o Docling divide uma fórmula em dois blocos.
