# Regras opcionais

Só valem para quem tem a peça instalada. O onboarding pergunta e anota em `equipe.md`, seção "Canais e agentes". Sem nada anotado lá, ignorar este arquivo. Estas regras acrescentam, não afrouxam nenhuma do `SKILL.md`: aprovar antes de escrever continua valendo, com as exceções declaradas aqui.

## 1. Cobrança de prazo por WhatsApp

Vale quando `equipe.md` diz por onde o Claude da pessoa manda WhatsApp (uma skill de envio ou um conector).

- **Quando:** na conferência do fim do dia, na leitura do `resumo_clickup.json` e quando a pessoa pedir. Tarefa de outro dono, com prazo vencido e ainda aberta: mandar um lembrete ao responsável (ou ao grupo dele) perguntando se foi feito. Tarefa da própria pessoa não gera cobrança, só reprogramação.
- **O texto:** curto, cita a tarefa pelo nome e o prazo que venceu, pergunta se foi feita ou qual a nova data. Sem inventar contexto que não está na tarefa.
- **Segurança:** na 1ª cobrança para um responsável ou grupo, mostrar destino e texto e esperar o ok. Depois que a pessoa autorizar o padrão para aquele responsável ou grupo, seguir sem pedir de novo. Registrar a autorização na linha do dono em `equipe.md`.
- **Contatos:** o mapa responsável e contato fica em `equipe.md` e é preenchido na 1ª cobrança real. Antes de cadastrar um contato novo, conferir o que a skill ou o conector de envio já conhece.

## 2. Delegar etapa a agente de IA

Vale quando a pessoa tem agentes no Claude Code dela (a pasta `.claude\agents` de onde ela trabalha, ou a lista em `equipe.md`).

- Ao decidir o dono de uma etapa, além das pessoas de `equipe.md`, olhar os agentes. Se um agente já cobre a etapa, o veredito é "delegar para <Agente> (a confirmar)" e a pessoa confirma antes. Nunca delegar direto.
- Etapa que vai para agente: o briefing do guardião vira o pedido de handoff para ele, com o mesmo padrão (o que fazer, como, critério de pronto, prazo-limite).
- Registrar na descrição da subtarefa no ClickUp quem executa: `Executor: agente <Nome> (IA)`.
- Etapa que nenhum agente cobre e que não é da pessoa nem da equipe: sinalizar que falta quem faça. Dizer que tipo de agente resolveria e de quais skills e conectores ele precisaria. Só sugerir. Nunca criar o agente sozinho: quem aprova é a pessoa.
