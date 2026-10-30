# Roteiro de demonstração (5 a 7 minutos)

Segue o formato do Demo Day: problema → solução → demo ao vivo → desafio técnico.

## Antes de apresentar (no dia anterior)

- [ ] `python scripts/baixar_modelos.py` (sem isso a primeira extração baixa ~3 GB).
- [ ] `.env` com `OPENAI_API_KEY` e créditos na conta; testar uma pergunta.
- [ ] Biblioteca com 5 a 10 artigos **já importados, revisados e indexados**
      (a extração de um artigo inteiro leva minutos; não dá para esperar ao vivo).
- [ ] Separar **1 PDF curto** (até ~8 páginas) para importar ao vivo e o
      **mesmo PDF renomeado** para mostrar a detecção de duplicata.
- [ ] Escolher um artigo com tabela, fórmula e figura para a inspeção.
- [ ] Testar antes as 3 perguntas abaixo e anotar a resposta esperada.
- [ ] Plano B: prints das telas principais, caso a internet ou a API falhem.

## 1. O problema (1 min)

> "Para escolher um TCC a gente lê vários artigos em inglês, cheios de tabelas
> e fórmulas, e precisa comparar métodos e limitações. Jogar o PDF num chat
> não ajuda: a resposta não diz de onde veio e pode inventar resultado."

## 2. A solução (1 min)

Mostrar o diagrama do README:

> "O estudante escolhe os artigos e faz upload. O Docling extrai texto,
> tabelas, fórmulas e figuras localmente, com a página de cada coisa. O
> catálogo é um DataFrame do Pandas. Os trechos vão para o ChromaDB com
> embeddings multilíngues, e o GPT responde só com base nesses trechos, citando
> artigo e página. O código confere cada citação."

## 3. Demo ao vivo (3 min)

1. **Importar (40 s)** — na área 1, enviar o PDF curto e a cópia renomeada
   juntos. Mostrar a tabela: um importado, o outro "duplicado" pelo SHA-256.
   *(Se a extração demorar, seguir com um artigo já importado.)*
2. **Inspecionar (50 s)** — escolher o artigo preparado: aba **Fórmulas**
   (LaTeX renderizado + contexto), **Tabelas** e **Página do PDF** (caixas e
   ordem de leitura). Apontar o alerta de qualidade e o checkbox "qualidade
   verificada": *"conversão sem erro não é qualidade garantida"*.
3. **Biblioteca (20 s)** — filtros, gráfico por tema/ano, resumo com groupby e
   exportar CSV.
4. **Perguntar (70 s)**
   - "Quais limitações os autores relatam?" → mostrar 📄 relatado vs 💡
     sugestão, abrir um trecho citado e conferir a página.
   - Uma pergunta **sem resposta** na coleção (ex.: "Quanto custou treinar os
     modelos?") → o app avisa que não há evidência suficiente.
   - Aba **Sugestões de recorte de TCC** → uma proposta com pergunta de
     pesquisa, método, artigos de apoio e dúvidas em aberto.

## 4. Desafio técnico (1 min)

Escolher um:

- **Ordem de leitura em duas colunas.** "O Docling leu a coluna da direita
  antes da esquerda num artigo com autores centralizados. Isso separava a
  fórmula da frase que explica as variáveis. Criamos uma verificação por página
  que detecta a inversão e reordena só aquela página, com aviso na inspeção."
- **Fórmulas que o Docling erra.** "Comparamos quatro leitores (Docling,
  LaTeX-OCR, Dolphin, Qwen-VL) em 25 fórmulas reais. O Dolphin acertou todas as
  de gabarito, então ele faz uma segunda leitura; quando discorda do Docling, a
  tela mostra o recorte e as duas versões para o estudante decidir."
- **Parágrafos entre páginas.** "Quando uma figura caía no topo da página, o
  parágrafo ficava partido e na seção errada. Unimos quando a frase não termina
  e a próxima começa com minúscula, e medimos a cobertura do texto do PDF para
  recuperar o que o Docling perdeu."
- **Citações confiáveis.** "O modelo às vezes cita um trecho que nem enviamos.
  Usamos Structured Outputs com Pydantic e conferimos cada rótulo contra os
  trechos recuperados; citação inexistente é descartada e avisada."
- **Português × inglês.** "O embedding padrão do ChromaDB é só inglês.
  Comparamos três modelos multilíngues com perguntas de resposta conhecida e
  escolhemos o bge-m3."

Fechar: *"Tudo roda local; só a pergunta e os trechos recuperados vão para a
API."*
