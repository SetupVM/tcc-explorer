# Analista de Feedback

Starter didático do Modelo 1 de [`projeto-final.md`](../../projeto-final.md). Ele ajuda uma loja a identificar elogios, reclamações e aspectos prioritários por produto/categoria a partir de avaliações em texto livre.

## Dados de exemplo

`data/reviews_loja.csv` e `data/produtos.csv` são dados **100% sintéticos**. As 300 avaliações incluem formatos variados de data e nota, valores ausentes, inglês, emojis, ironia, comentários vazios e duplicatas exatas/quase duplicatas. Os arquivos também podem ser substituídos por CSVs enviados pela interface.

## Como rodar

Requer Python 3.10 ou superior. A partir deste diretório:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` e informe sua chave, sem compartilhá-la ou enviá-la ao GitHub:

```dotenv
OPENAI_API_KEY=sua-chave
OPENAI_MODEL=gpt-4o-mini
```

Inicie a interface:

```bash
streamlit run app.py
```

Envie `reviews_loja.csv` e `produtos.csv`, ou mantenha selecionada a opção **Usar dados sintéticos de exemplo**. A análise usa Structured Outputs com Pydantic, duas tentativas no máximo por comentário, e registra falhas sem interromper os demais. Os resultados ficam em cache durante a sessão para não repetir chamadas para os mesmos arquivos.

## Gabarito de demonstração

- ID 1: elogio positivo.
- ID 2: ironia — apesar da nota 5, “Ótimo, quebrou no segundo dia” deve ser classificado como negativo e aparecer como conflito.
- ID 3: comentário em inglês.
- IDs 5 e 6: comentários quase duplicados do mesmo produto.
- ID 7: duplicata exata do ID 1.
- ID 4: comentário vazio; permanece auditável e não é enviado à API.

A interpretação de sentimento pode variar entre modelos; o gabarito destaca os casos que devem ser conferidos na demo.
