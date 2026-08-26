<div align="center">

# Entendendo como usar as APIs
### Aula 2: API na prática com controle de custo

<br>

📱 **Material da Aula 2:**
`github.com/pedromatumoto/ia-na-pratica`

</div>

---

## Agenda da Aula

1. **Mensagens e papéis:** System, User e Assistant.
2. **Hiperparâmetros essenciais:** Temperature, Top P e Max Tokens.
3. **Custo e memória:** Histórico, janela deslizante e tokens.
4. **Segurança básica:** Prompt Injection e instruções robustas.
5. **Hands-on:** Mini chat com histórico controlado.

---

## 1. O Objeto de Mensagem: A Lei do Sistema

Diferente de um chat comum, via API trabalhamos com uma lista de objetos. O **System Prompt** é a "constituição" do seu sistema.

| Papel (Role) | Função | Exemplo de comportamento |
| :--- | :--- | :--- |
| **System** | Define as regras, tom e restrições. | "Você é um validador de JSON estrito." |
| **User** | A entrada do usuário final. | "Quero me matricular no curso." |
| **Assistant** | A resposta anterior da IA. | "Claro! Segue o link para o portal..." |


> Se o *System Prompt* for fraco, o utilizador pode forçar comportamento indevido.
> Regra prática: no System Prompt, declare limites, formato de saída e o que fazer quando faltar contexto.

---

## 2. Hiperparâmetros: O Painel de Controle

Não é só texto; é estatística. Um dos principais é a **Temperature**.

* **Temp 0.0 (Foco Total):** Previsível e determinístico. Ideal para extração de dados, tradução técnica e automação financeira.
* **Temp 0.7 (Equilíbrio):** Conversa natural com boa coerência.
* **Temp 1.0+ (Criatividade):** Mais variação e maior risco de ruído.

**Outros controles úteis:**
* **Top P:** filtra o universo de tokens candidatos.
* **Max Tokens:** limita tamanho e custo da resposta.
* **Presence/Frequency Penalty:** reduz repetição.

---

## 3. Economia de Tokens e Memória de Conversa

LLMs são stateless. Se você não reenviar o contexto, o modelo não "lembra".

### Estratégia mínima para produção inicial
1. Manter apenas as últimas N mensagens (janela deslizante).
2. Manter um System Prompt estável.
3. Controlar `max_tokens` na saída.

### A Analogia do Estagiário Genial
Imagine um estagiário que sabe tudo sobre engenharia, mas tem **amnésia instantânea**.
1. Você entrega um manual de 300 páginas e pergunta: *"Qual o torque do parafuso X?"*.
2. Ele lê as 300 páginas em 1 segundo e responde perfeitamente.
3. **Ele esquece tudo.**
4. Para a próxima pergunta, você precisa pagar e entregar as 300 páginas **de novo**.

**A Conta no final do mês:**
Enviar 100.000 tokens a cada "Bom dia" para manter o contexto vai falir o seu projeto. Otimizar o que vai no contexto é economizar dinheiro real.

---

## 4. Segurança Básica: Prompt Injection

Ataques comuns tentam sobrescrever suas instruções.

Mitigações para hoje:
* Definir no System Prompt o objetivo e as restrições.
* Pedir resposta em formato fixo quando necessário.
* Se faltar dado no contexto, responder "informação insuficiente".

---

## 5. Hands-on: Indo para o Código

Hoje vamos explorar a API e construir um mini chat com histórico controlado.

### O Desafio
Como manter uma conversa sem estourar orçamento e sem perder consistência?

### Entregável da Aula
Script funcional com:
* lista de mensagens por role;
* janela deslizante;
* parâmetros explícitos (temperature e max_tokens).

---

## Ferramentas e Referências

* **Contagem de Tokens:** [OpenAI Tokenizer](https://platform.openai.com/tokenizer)
* **Documentação API:** [OpenAI Docs](https://developers.openai.com/api/docs)
* **Ambiente de Aula:** [Google Colab](https://colab.research.google.com/)

---
## Extra
* **Playground de Testes:** [Claude Platform](https://platform.claude.com/docs/en/home)
* **Teoria de Parâmetros:** [IBM - LLM Parameters](https://www.ibm.com/think/topics/llm-parameters)
* **Curso da Anthropic ensinando como utilizar o toolkit deles** https://github.com/anthropics/courses

---

### Prática Extra
Estruture um JSON de saída para extrair dados de currículo e adicione uma regra no System Prompt para recusar perfis sem experiência em Python.
