# 🏆 Desafio Final: IA na Prática

## O Cenário: Carta Branca
Ao longo do curso, vimos como a Inteligência Artificial e a Engenharia de Dados podem resolver o caos do mundo corporativo. Agora, a bola está com vocês e **vocês têm total liberdade para escolher o tema do projeto.**

O seu desafio é identificar um problema real e construir um *produto de dados* para resolvê-lo. Pode ser um gargalo do atual estágio/trabalho, uma dificuldade da vida universitária, ou até mesmo algo focado em hobbies (finanças pessoais, análise de jogos, esporte, viagens). A única regra é: **o sistema tem de ser útil e resolver um problema de forma automatizada.**

## Objetivo do Projeto
Construir um pipeline de dados inteligente, de ponta a ponta, que receba dados brutos/desestruturados, utilize a inteligência de um LLM para tratá-los ou consultá-los, e exiba os resultados numa interface visual funcional.

---

## Requisitos Técnicos Obrigatórios (MVP)

Apesar de o tema ser livre, o projeto de vocês **deve** conter obrigatoriamente as 4 camadas abaixo:

### Grupos de até 3 pessoas

### 1. Camada de Dados (Pandas)
* O sistema deve ler pelo menos uma base de dados externa (um `.csv` sujo, um `.xlsx` ou múltiplos arquivos `.txt`/`.pdf`).
* O código deve realizar pelo menos uma operação de **limpeza** (tratar nulos, remover duplicatas ou corrigir tipagem).
* O código deve realizar pelo menos uma operação de **agregação ou filtro** (ex: `groupby()` para gerar um resumo financeiro ou quantitativo).

### 2. Camada Cognitiva (Inteligência Artificial)
* O sistema deve realizar chamadas para a API (OpenAI ou Gemini).
* **Opção A (Extração/Classificação):** Usar *Structured Outputs* (JSON) para ler textos livres da base de dados e criar uma nova coluna padronizada (ex: Análise de Sentimento de comentários, extração de dados específicos).
* **Opção B (RAG):** Usar o `ChromaDB` para vetorizar documentos complexos e permitir buscas semânticas (ex: um assistente que lê manuais e responde a dúvidas baseadas neles).

### 3. Camada de Interface (Streamlit)
* O projeto deve ter uma interface gráfica feita em **Streamlit** ou correlato.
* O utilizador final deve conseguir fazer o upload do ficheiro (`st.file_uploader`) ou digitar a sua pergunta (`st.text_input`) diretamente na tela.
* O resultado deve ser exibido na tela de forma visual (tabelas interativas, métricas ou gráficos básicos).

### 4. Camada de Engenharia e Versionamento (GitHub)
* O projeto deve estar num repositório público no GitHub.
* O repositório **NÃO** pode conter a chave da API (`.env` deve estar no `.gitignore`).
* O repositório deve ter um arquivo `requirements.txt`.
* O repositório deve ter um `README.md` muito bem escrito, explicando o que é o projeto, qual problema resolve e como rodar o código localmente.

---

## 💡 Ideias de Projetos (Apenas como inspiração)

Caso não saibam por onde começar, aqui ficam algumas ideias que podem adaptar::

1. **O Auditor Pessoal:** Uma aplicação que lê dezenas de faturas ou recibos misturados em `.txt`, usa a IA para extrair "Estabelecimento", "Valor" e "Categoria" em JSON, e usa o Pandas para mostrar um painel de gastos do mês.
2. **O Analista de Feedback:** O app recebe um `.csv` com centenas de *reviews* (de um produto, de um filme, ou de um jogo). A IA lê cada uma, classifica (Positivo, Negativo, Neutro) e categoriza o tema principal. O Pandas gera um gráfico com o resumo do que as pessoas mais gostam ou odeiam.
3. **O Guru dos Manuais (Mini-RAG):** Uma interface de chat onde se faz o upload de um arquivo `.pdf` complexo (como regras de um jogo de tabuleiro longo, editais de concursos ou manuais da faculdade). O sistema usa o ChromaDB para vetorizar o texto e permite fazer perguntas precisas ao documento.

---

## Entregáveis e Prazos

* **Data de Entrega (GitHub):** 31/05 até as 23h59. Apenas o link do repositório deve ser enviado.
* **Demo Day:** o projeto precisa ser apresentado para mim, na data melhor para o grupo.

### O formato do Demo Day:
Cada grupo terá **5 a 7 minutos** para apresentar. Não quero slides cheio de textos. A estrutura da apresentação deve ser:
1. **O Problema (1 min):** "Qual é a dor ou desafio que escolhemos resolver?"
2. **A Solução (1 min):** "Como usamos IA para criar este produto?"
3. **Ao Vivo (Live Demo) (3 min):** Executar a aplicação Streamlit e mostrar que funciona.
4. **Desafios Técnicos (1 min):** "Qual foi a parte mais difícil do código e como a superamos?"

---

## Critérios de Avaliação

1. **Funcionalidade (40%):** O código roda sem quebrar? A aplicação resolve o problema proposto? A integração com a API funciona?
2. **Arquitetura e Clean Code (20%):** O código está organizado? As variáveis têm nomes lógicos? O System Prompt foi bem construído para evitar alucinações da IA?
3. **Complexidade e Domínio (20%):** O grupo demonstrou dominar o Pandas e o fluxo de dados, ou apenas copiou tutoriais básicos?
4. **Apresentação e Produto (20%):** A interface no Streamlit é amigável? O `README.md` está profissional? A apresentação foi clara e focado no valor entregue?
