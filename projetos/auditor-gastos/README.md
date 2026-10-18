# Auditor de Gastos

Starter didático do Modelo 2 de [`projeto-final.md`](../../projeto-final.md). Ele extrai recibos em formatos variados, valida os valores e consolida os gastos por categoria e mês.

## Dados de exemplo

`data/recibos/` contém 25 recibos **sintéticos** (TXT e PDF) de supermercado, transporte, restaurante e conta doméstica. Há formatos de data e moeda mistos, itens com quantidade, gorjeta/taxa, duas compras duplicadas, um recibo incompleto e um PDF válido sem camada de texto. PDFs escaneados não recebem OCR.

O campo `valor` de cada item é o total da linha (incluindo a quantidade), não o preço unitário. A soma das linhas precisa coincidir com `valor_total`, com tolerância de R$ 0,05.

## Como rodar

Requer Python 3.10 ou superior. A partir deste diretório:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` e adicione sua chave, sem compartilhá-la ou enviá-la ao GitHub:

```dotenv
OPENAI_API_KEY=sua-chave
OPENAI_MODEL=gpt-4o-mini
```

Inicie a interface:

```bash
streamlit run app.py
```

Envie vários arquivos TXT/PDF ou mantenha selecionada a opção **Usar recibos sintéticos de exemplo**. A extração usa Structured Outputs com Pydantic e validações locais; cada arquivo é isolado, com no máximo duas tentativas. Resultados dos mesmos arquivos ficam em cache durante a sessão. O app sinaliza inconsistências, duplicatas e falhas de leitura sem descartar recibos válidos.

## Gabarito de demonstração

- `mercado_01.txt`: estabelecimento Mercado Bom Preco, data 10/01/2025, categoria alimentação, total R$ 36,50; as linhas de R$ 28,00 e R$ 8,50 conferem.
- `mercado_01_copia.pdf`: segunda representação da mesma compra; deve ser marcada como duplicata.
- `recibo_15.txt`: contém o valor brasileiro `R$ 1.234,56`.
- `recibo_sem_texto.pdf`: deve aparecer na lista de arquivos com problema.
