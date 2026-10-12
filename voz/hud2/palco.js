// O painel é desenhado num palco de altura fixa (900 no computador, 420 na janela compacta, 844 no celular).
// No computador a largura do palco acompanha o formato da janela, do 16:10 ao ultrawide, para a tela inteira ser usada, sem faixas pretas dos lados.
// (O conteúdo cresce até 1920 de largura; numa janela mais larga que isso ele fica centralizado e só o fundo e o topo vão de ponta a ponta.)
// Este arquivo encaixa o palco na janela, qualquer que seja o tamanho dela, sem deformar, e avisa o painel quando a largura muda.
(function () {
  var TAM = { desktop: [1440, 900], mini: [320, 420], mobile: [390, 844] };
  var LARGURA_MAX = 4320;  // só uma trava para formatos absurdos (janela quase 5 vezes mais larga que alta)
  var modo = window.GD_MODO || 'desktop', H = TAM[modo][1];
  function largura() {
    if (modo !== 'desktop') return TAM[modo][0];
    var formato = window.innerWidth / Math.max(1, window.innerHeight);
    return Math.max(TAM.desktop[0], Math.min(LARGURA_MAX, Math.round(H * formato / 2) * 2));
  }
  window.GD_W = largura();
  function encaixar() {
    var W = largura();
    if (window.GD_W !== W) { window.GD_W = W; window.dispatchEvent(new Event('gd-palco')); }
    var raiz = document.getElementById('dc-root');
    if (!raiz) return false;
    var lw = window.innerWidth, lh = window.innerHeight, k = Math.min(lw / W, lh / H);
    raiz.style.position = 'absolute';
    raiz.style.left = '0'; raiz.style.top = '0';
    raiz.style.width = W + 'px'; raiz.style.height = H + 'px';
    raiz.style.transformOrigin = '0 0';
    raiz.style.transform = 'translate(' + ((lw - W * k) / 2).toFixed(2) + 'px,' + ((lh - H * k) / 2).toFixed(2) + 'px) scale(' + k.toFixed(5) + ')';
    return true;
  }
  var tentativas = 0, iv = setInterval(function () { if (encaixar() || ++tentativas > 200) clearInterval(iv); }, 50);
  window.addEventListener('resize', encaixar);
})();
