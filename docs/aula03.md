<div align="center">

# Texto livre e Json
### Aula 3: Structured Outputs com JSON e Pydantic

<br>

📱 **Material da Aula 3:**
`https://github.com/pedromatumoto/ia-na-pratica/`

</div>

---

## Agenda da Aula

1. **O Caos do Texto Livre:** Por que `split()` e Regex vão quebrar
2. **JSON: A Língua Franca:** Estrutura para integração entre sistemas.
3. **Structured Outputs & Pydantic:** Contrato de resposta e validação.
4. **Falhas reais:** Parse, campos faltantes e estratégia de retry.
5. **Hands-on:** Extrator de entidades para dados de suporte.

---

## 1. O Caos do Texto Livre: Por que a IA é "Conversadeira"

O maior erro de um desenvolvedor ao integrar LLMs em produção é tratar a resposta da IA como uma String comum. O modelo é treinado para ser prestativo, o que significa que ele adora adicionar "papo furado" (preâmbulos e conclusões).

**O Problema:**
Você pede: *"Extraia o valor da nota fiscal"*.
A IA responde: *"Com certeza! Analisei o documento e o valor identificado é R$ 1.500,00. Espero que isso ajude no seu controle financeiro!"*

> **O Risco de Produção:**
> Tentar fazer um `.split("é")[1]` ou usar um Regex para capturar esse valor é perigoso. O código de extração vai quebrar. **Sistemas precisam de contratos, não de conversas.**

---

## 2. O Padrão JSON: A Ponte entre Cérebro e Máquina

Para que a IA converse com o seu banco de dados (PostgreSQL, MongoDB) ou seu Front-end (React, Mobile), ela precisa falar a linguagem universal da web: **JSON**.

* **Estrutura Chave-Valor:** `{ "campo": "valor" }`.
* **Tipagem:** Strings, Numbers, Booleans, Arrays e Objetos aninhados.
* **Semântica:** O nome da chave (ex: `is_reentry`) ajuda o LLM a entender o que deve colocar ali.

---

## 3. Structured Outputs: O "Contrato" de Resposta

As APIs modernas (OpenAI, Gemini, etc) introduziram o recurso de **Structured Outputs**. Em vez de ficar forçando no prompt sem nem ter certeza para a IA responder um JSON, você envia um **JSON Schema** e o modelo é forçado matematicamente a seguir essa estrutura.

### Pydantic: A Camada de Validação
No Python, usamos a biblioteca **Pydantic** para definir como os dados devem chegar. Se a IA tentar enviar um texto onde deveria ser um número, o Pydantic barra o erro na hora.

```python
from pydantic import BaseModel

class TicketSuporte(BaseModel):
    cliente: str
    motivo: str
    urgencia: int # Deve ser de 1 a 5
    reembolso_solicitado: bool
```

---

## 4. Robustez para Produção

Mesmo com Structured Outputs, você precisa de tratamento de erro:
* validar campos obrigatórios;
* lidar com resposta incompleta;
* aplicar retry com instrução mais rígida;
* registrar erro para auditoria.

---

## 5. Hands-on: O Extrator de Entidades

Construa um script que simula um sistema de triagem automática de e-mails de suporte.

### O Desafio:
Processar um texto bagunçado e extrair dados estruturados para alimentar um Dashboard de atendimento.


Input (E-mail do Cliente):

    "Olá. Comprei o produto ontem (Pedido #123) e ele chegou quebrado. Estou muito decepcionado e quero meu dinheiro de volta agora, ou vou reclamar no Procon."

Output Esperado (JSON):
JSON

```
{
  "cliente": "Não identificado",
  "pedido_id": "123",
  "motivo": "Produto danificado",
  "urgencia": 5,
  "intent_reembolso": true
}
```

### Entregável da Aula
Um script que receba texto livre e devolva JSON validado por schema.

---

## Ferramentas e Referências

* **Validador de JSON**: [JSONLint](https://jsonlint.com/)

* **Pydantic Guide**: [Pydantic Docs](https://docs.pydantic.dev/)

* **Structured Outputs**: [OpenAI API Reference](https://platform.openai.com/docs/guides/structured-outputs)

* **JSON Schema**: [Understanding JSON Schema](https://json-schema.org/)

---

## Fechamento: O Fim da Triagem Manual

Substituir humanos lendo e-mails para preencher planilhas por um LLM com Structured Output economiza milhares de horas. A IA não apenas entende o texto, ela o transforma em dado útil e acionável para o seu software.

---

## Prática Extra

Desafio: adicione um campo `sentiment_analysis` ao modelo Pydantic aceitando apenas ["POSITIVE", "NEUTRAL", "NEGATIVE"] e valide a classificação para cada comentário.
