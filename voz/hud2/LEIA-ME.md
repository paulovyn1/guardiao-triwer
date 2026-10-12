# Painel do guardião

Abre em `http://localhost:8767/v2/` (atalho: `..\abrir_guardiao_v2.bat`; `..\criar_atalho.ps1` põe um atalho com o ícone na área de trabalho).

| Arquivo | O que é |
|---|---|
| `index.html`, `mini.html`, `celular.html` | páginas de entrada: computador (palco 1440x900), janela compacta (320x420) e celular (390x844) |
| `Main.dc.html` | a tela inteira: CSS e marcação do design (Claude Design) e a lógica ligada ao servidor (`/plano`, `/eventos`, `/execucao`, `/calibragem`, `/pops`). É o arquivo a editar |
| `Orb3D.dc.html`, `Orb.dc.html` | a bolinha: Núcleo 3D (WebGL) e as versões 2D (Relógio e a do modo leve). Leem o volume real em `window.GD_NIVEL` |
| `Bg2.dc.html`, `Intro.dc.html` | fundo Constelação e a abertura de cerca de 9 s |
| `support.js`, `vendor\` | runtime do Claude Design e React 18, guardados aqui para o painel abrir sem internet. Não editar |
| `palco.js` | encaixa o palco na janela. A altura é fixa (900); no computador a largura acompanha o formato da janela, do 16:10 ao ultrawide, e chega ao painel em `window.GD_W` (o conteúdo cresce até 1920 e depois fica centralizado) |
| `..\guardiao_janela.py` | fixa a janela compacta por cima das outras, no canto inferior direito (o navegador sozinho não consegue) |
| `..\guardiao_atualizacao.py` | versão instalada, aviso de versão nova (botão discreto no topo) e o botão de atualizar |
| `fontes.css`, `fontes\` | as três fontes, empacotadas |

Parâmetros úteis: `?semabertura=1` (pula a abertura e a saudação, usado nos testes), `?abertura=1` (força a abertura), `?tela=dia|plan|cal|pops`.
`?solta=1` em `mini.html` abre a janela compacta sem fixá-la por cima das outras.
