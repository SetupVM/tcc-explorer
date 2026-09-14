# 🏆 Desafio Final: IA na Prática (Aula 7)

## O Cenário: Carta Branca
Ao longo das 7 aulas, aprendemos a arquitetar sistemas com IA, controlar APIs, estruturar dados e processar informações complexas. Agora, a bola está com vocês e **vocês têm total liberdade para escolher o tema do projeto.**

O seu desafio é identificar um problema real e construir um *produto de dados* para resolvê-lo. Pode ser um gargalo do atual estágio/trabalho, uma dificuldade da vida universitária, ou até mesmo algo focado em hobbies (finanças pessoais, análise de jogos, esporte, viagens). A única regra é: **o sistema tem de ser útil e resolver um problema de forma automatizada.**

## Objetivo do Projeto
Construir um pipeline de dados inteligente, de ponta a ponta, que receba dados brutos/desestruturados, utilize a inteligência de um LLM para tratá-los ou consultá-los, e exiba os resultados numa interface visual funcional com **Streamlit**.

---

## Requisitos Técnicos Obrigatórios (MVP)

Apesar de o tema ser livre, o projeto de vocês **deve** conter obrigatoriamente as 4 camadas abaixo:

### Grupos de até 3 pessoas

### 1. Camada de Dados (Pandas + Aulas 5 e 6)
* O sistema deve ler pelo menos uma base de dados externa (um `.csv` sujo, um `.xlsx` ou múltiplos arquivos `.txt`/`.pdf`).
* O código deve realizar pelo menos uma operação de **limpeza** (tratar nulos, remover duplicatas ou corrigir tipagem).
* O código deve realizar pelo menos uma operação de **agregação ou filtro** (ex: `groupby()` para gerar um resumo financeiro ou quantitativo).

### 2. Camada Cognitiva (Inteligência Artificial + Aulas 2, 3 e 4)
* O sistema deve realizar chamadas para a API (OpenAI ou Gemini) com **controle de custo** (temperature, max_tokens).
* **Opção A (Extração/Classificação - Aula 3):** Usar *Structured Outputs* (JSON com Pydantic) para ler textos livres da base de dados e criar uma nova coluna padronizada (ex: Análise de Sentimento de comentários, extração de dados específicos).
* **Opção B (Mini-RAG - Aula 4):** Usar embeddings e busca semântica (ChromaDB ou similar) para vetorizar documentos complexos e permitir buscas contextualizadas (ex: um assistente que lê manuais e responde a dúvidas baseadas neles).

### 3. Camada de Interface (Streamlit + Aula 7)
* O projeto deve ter uma interface gráfica feita em **Streamlit** (obrigatório).
* O utilizador final deve conseguir fazer o upload do ficheiro (`st.file_uploader`) ou digitar a sua pergunta (`st.text_input`) diretamente na tela.
* O resultado deve ser exibido na tela de forma visual (tabelas interativas, métricas ou gráficos básicos).
* **Checklist de engenharia:** código organizado em funções, nomes legíveis, pipeline funcional e testável.

### 4. Camada de Engenharia e Versionamento (GitHub + Aula 7)
* O projeto deve estar num repositório público no GitHub.
* O repositório **NÃO** pode conter a chave da API (`.env` deve estar no `.gitignore`).
* O repositório deve ter um arquivo `requirements.txt` completo.
* O repositório deve ter um `README.md` profissional, explicando:
  * Qual problema o sistema resolve (pitch claro).
  * Como usar a aplicação (instruções passo a passo).
  * Como rodar o código localmente (`git clone`, `pip install`, `streamlit run`).

---

## 💡 Ideias de Projetos (Apenas como inspiração)

Caso não saibam por onde começar, aqui ficam algumas ideias que podem adaptar:

1. **O Auditor Pessoal (Aulas 5 e 6):** Uma aplicação que lê dezenas de faturas ou recibos misturados em `.txt`, usa a IA para extrair "Estabelecimento", "Valor" e "Categoria" em JSON (Aula 3), limpa com Pandas e gera um painel de gastos mensal em Streamlit.
2. **O Analista de Feedback (Aula 5):** O app recebe um `.csv` com centenas de *reviews* (de um produto, de um filme, ou de um jogo). A IA lê cada uma, classifica (Positivo, Negativo, Neutro) com Structured Outputs (Aula 3), e o Pandas gera um gráfico com o resumo do que as pessoas mais gostam ou odeiam.
3. **O Guru dos Manuais (Mini-RAG - Aula 4):** Uma interface de chat onde se faz o upload de um arquivo `.pdf` complexo (como regras de um jogo de tabuleiro longo, editais de concursos ou manuais). O sistema usa embeddings para vetorizar o texto (Aula 4) e permite fazer perguntas precisas ao documento com contexto recuperado.

---

## 📅 Entregáveis e Prazos

* **Data de Entrega (GitHub):** 31/05 até as 23h59. Apenas o link do repositório deve ser enviado.
* **Demo Day:** o projeto precisa ser apresentado para mim, na data melhor para o grupo.

### O Formato do Demo Day (Aula 7):
Cada grupo terá **5 a 7 minutos** para apresentar. Menos slides, mais produto rodando. A estrutura é:
1. **O Problema (1 min):** Qual é a dor ou desafio real que escolheram resolver?
2. **A Solução (1 min):** Como usaram IA + Dados para criar este produto?
3. **Ao Vivo (Live Demo) (3 min):** Executar a aplicação Streamlit e mostrar o fluxo funcionando.
4. **Desafios Técnicos (1 min):** Qual foi a parte mais difícil e como foi resolvida?

---

## 📊 Critérios de Avaliação

O projeto será avaliado em 4 dimensões, alinhadas às 7 aulas:

1. **Funcionalidade (40%):** 
   - O código roda sem erros?
   - A aplicação resolve o problema proposto?
   - A integração com API (Aulas 2, 3, 4) funciona corretamente?
   - O pipeline Pandas (Aulas 5, 6) processa dados conforme esperado?

2. **Arquitetura e Clean Code (20%):** 
   - Código organizado em funções claras?
   - Variáveis e nomes de função legíveis?
   - System Prompt bem construído (Aula 2)?
   - Tratamento de erros para falhas de API e parsing?

3. **Domínio e Complexidade (20%):** 
   - Domínio comprovado de Pandas (Aulas 5, 6) ou apenas tutoriais copiados?
   - Uso correto de Structured Outputs ou Mini-RAG (Aulas 3, 4)?
   - Demonstração prática de controle de custo (Aula 2)?

4. **Apresentação e Produto (20%):** 
   - Interface Streamlit é intuitiva e funcional (Aula 7)?
   - `README.md` profissional e completo?
   - Demo de 5 a 7 min clara, focada no valor entregue?
   - Repositório GitHub limpo e bem documentado?
