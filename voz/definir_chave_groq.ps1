# Guarda a chave gratuita do Groq (a transcrição da sua fala) como variável de usuário GROQ_API_KEY.
# Rode na SUA janela: a chave nunca passa pelo chat. Atalho: dois cliques em definir_chave_groq.bat.
#   -SemAbrir   não abre a página do Groq no navegador
param([switch]$SemAbrir)
$pagina = 'https://console.groq.com/keys'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

Write-Host ""
Write-Host "CHAVE DO GROQ: é ela que transforma a sua fala em texto. É gratuita e leva 2 minutos." -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Vou abrir no seu navegador a página $pagina"
Write-Host "  2. Entre com a sua conta do Google (ou crie uma conta com o seu e-mail). Não pede cartão."
Write-Host "  3. Clique no botão Create API Key, escreva o nome guardiao e confirme em Submit."
Write-Host "  4. Clique em Copy. A chave começa com gsk_ e só aparece essa vez."
Write-Host "  5. Volte para esta janela, clique com o botão direito do mouse para colar e aperte Enter."
Write-Host ""
Write-Host "  Sem a chave o painel abre do mesmo jeito e você conversa escrevendo. Para pular, aperte Enter sem colar nada."
Write-Host ""
if (-not $SemAbrir) { try { Start-Process $pagina } catch { } }

for ($tentativa = 1; $tentativa -le 3; $tentativa++) {
    $seguro = Read-Host -AsSecureString "Cole a chave aqui (ela não aparece na tela) e aperte Enter"
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    $chave = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)).Trim()
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    if (-not $chave) {
        Write-Host "Sem chave por enquanto. Para ligar o microfone depois, dê dois cliques em definir_chave_groq.bat, nesta pasta."
        exit 2
    }
    if ($chave.Length -lt 20) { Write-Host "Isso está curto demais para ser a chave. Copie de novo pelo botão Copy."; continue }
    try {
        $null = Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/models" -Headers @{ Authorization = "Bearer $chave" } -Method Get -TimeoutSec 20
    } catch {
        Write-Host "O Groq não aceitou essa chave ($($_.Exception.Message)). Nada foi gravado. Copie de novo e tente outra vez."
        continue
    }
    [Environment]::SetEnvironmentVariable("GROQ_API_KEY", $chave, "User")
    Write-Host "Chave aceita pelo Groq e gravada neste computador." -ForegroundColor Green
    Write-Host "Se o guardião já estiver aberto, o microfone liga sozinho em até um minuto. Não precisa fechar nada."
    exit 0
}
Write-Host "Não deu certo em 3 tentativas. Nada foi gravado. Rode de novo quando quiser."
exit 1
