# Guru dos Manuais

Starter didático do Modelo 3 de [`projeto-final.md`](../../projeto-final.md). Ele recupera trechos relevantes de um manual PDF e responde perguntas usando somente o contexto encontrado, exibindo páginas como fonte.

## Documento de exemplo

`data/manual_sintetico.pdf` tem 20 páginas de regras fictícias de um jogo. O documento e suas regras são sintéticos e estão no repositório para demonstrar extração, chunking com sobreposição, embeddings e busca no ChromaDB.

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
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Inicie a interface:

```bash
streamlit run app.py
```

O app usa o manual sintético quando não há upload. Clique em **Indexar documento**, depois faça uma pergunta. O índice ChromaDB fica em memória durante a sessão; o app preserva as páginas de origem, mostra os trechos recuperados e registra pergunta, fontes, páginas e tokens. Perguntas sem suporte no contexto devem receber `Não encontrei no documento.`. Respostas da mesma pergunta para o mesmo PDF são reutilizadas durante a sessão.

## Gabarito de demonstração

Pergunte: `Quantas cartas cada jogador compra no inicio do turno?`

- Trecho esperado: `No inicio do turno, cada jogador compra duas cartas.`
- Fonte esperada: página 6.
- Resposta esperada: cada jogador compra duas cartas no início do turno.

O modelo pode variar a redação, mas a regra e a página citada devem corresponder ao documento.
