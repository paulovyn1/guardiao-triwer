---
nome: NOME DA CAMPANHA
slug: nome-da-campanha
tipo: venda-publica
canal: Instagram
data_inicio: AAAA-MM-DD
data_fim: AAAA-MM-DD
status: planejando
importancia: media
resumo: Uma frase: o que é e para que serve.
abrir_quando: situações em que vale abrir esta nota (decidir X, agenda de A a B)
dono: {{nome}}
sigilo:
revisado_em: AAAA-MM-DD
---
# NOME DA CAMPANHA

> Valores aceitos. tipo: venda-publica | venda-ao-vivo | acao-comercial | mudanca-de-marca | estrategia | rotina. status: ideia | planejando | em-execucao | encerrada. importancia: critica | alta | media | baixa. sigilo: data até a qual é segredo (ou vazio).
> Descobriu algo novo sobre esta campanha? NÃO edite as seções. Rode `anotar_campanha.ps1 -Slug nome-da-campanha -Fonte "..." -Texto "..."` ou acrescente uma linha na seção 7. Só o guardião reorganiza.

## 1. Ficha
Muda só por decisão registrada em `decisoes\`. Escreve: guardião.
- O que é e objetivo:
- Público e canal:
- Produto, oferta e preço:
- Donos (quem faz o quê):
- Restrições fixas (o que nunca pode acontecer):

## 2. Estado agora
Máximo 10 linhas. REESCREVE-SE, não acumula. Lê: sempre. Atualiza: a cada decisão, a cada marco e na faxina semanal.
- Onde estamos:
- Próximo marco (com data):
- Bloqueios e perguntas em aberto:

## 3. Marcos e tarefas
Só marcos com data e ids do ClickUp. NÃO copiar status de tarefa: o status vive no ClickUp.
| Data | Marco ou tarefa | Dono | ClickUp |
|---|---|---|---|

## 4. Decisões
Uma linha por decisão, com o satélite onde está o porquê: `AAAA-MM-DD | decisão | decisoes\AAAA-MM.md`.

## 5. Ativos e links
Documentos, páginas, pastas, POPs, arquivos.

## 6. Resultado
Só no encerramento: números, o que funcionou, o que mudar da próxima vez. Vazio enquanto a campanha está ativa.

## 7. Caixa de entrada
Uma linha por achado, de qualquer conversa: `- AAAA-MM-DD | fonte | o que descobri`. O guardião incorpora na seção certa e esvazia na faxina semanal.
_(vazia)_

## 8. Histórico de mudanças
Uma linha por alteração de seção, só o guardião escreve: `AAAA-MM-DD | seção | o que mudou`.
