# Campanhas: ÍNDICE e calendário

Cada campanha (lançamento, venda, ação comercial, mudança de marca, estratégia de período) tem uma nota própria em `campanhas\`, todas no MESMO modelo (`campanhas\_modelo.md`): cabeçalho com os dados de índice e 8 seções fixas. **A tabela abaixo é gerada por `indice_campanhas.ps1` a partir dos cabeçalhos das notas: nunca editar à mão.** Quando uma fonte contradiz uma nota, a fonte vence e a nota é corrigida na hora. Teto deste arquivo: 120 linhas.

**Como ler:** abrir só a campanha que o bloco toca, e só as seções necessárias: `powershell -ExecutionPolicy Bypass -File ler_campanha.ps1 -Slug nome-da-campanha` traz Ficha, Estado agora e Caixa de entrada; `-Secao tarefas,decisoes` traz o resto sob demanda.
**Como atualizar:** descobriu algo? `anotar_campanha.ps1 -Slug X -Fonte "..." -Texto "..."` põe uma linha na Caixa de entrada sem ler a nota. Só o guardião reorganiza as outras seções (na faxina semanal ou ao registrar uma decisão).
**Como criar uma campanha nova:** copiar `campanhas\_modelo.md`, preencher o cabeçalho e a Ficha, rodar `indice_campanhas.ps1`.

## Campanhas

<!-- INDICE:INICIO (gerado por indice_campanhas.ps1, nao editar) -->
<!-- INDICE:FIM -->

## Regras que valem em TODAS as campanhas (sempre lidas, não estão só nas notas)

[nenhuma ainda. Exemplos de regra transversal: "ninguém do time comenta X antes da data", "duas campanhas não disputam o mesmo público no mesmo mês".]

## Linha do tempo (todas as campanhas)

| Data | O que |
|---|---|
