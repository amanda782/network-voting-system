# Sistema de votação em rede

## Tema
Trabalho Prático 2 — Redes de Computadores: Aplicação e Transporte. Opção 6: Sistema de votação em rede.

## Linguagem e versão
Python 3.10 ou superior. O projeto usa somente bibliotecas padrão do Python.

## Arquivos
- `servidor.py`: servidor TCP e envio de avisos UDP.
- `cliente.py`: menu do participante e recebimento de avisos UDP.
- `opcoes.json`: pergunta e opções da votação.
- `logs/eventos.log`: eventos registrados pelo servidor durante a execução.
- `relatorio.txt`: modelo para anotar os testes executados.

## Endereços e portas
- TCP: porta `5000` no servidor — cadastro, comandos, votos, consultas e resultados.
- UDP: porta `5001` reservada/vinculada no servidor; os avisos são enviados por unicast às portas UDP informadas pelos clientes.
- Cada cliente escolhe automaticamente uma porta UDP livre. O número é informado ao servidor no cadastro.
- Para executar todos os programas no mesmo computador, informe `127.0.0.1` no cliente.
- Para executar em computadores diferentes, informe no cliente o IPv4 do computador servidor. Permita as portas TCP 5000 e UDP 5001/portas de clientes no firewall, conforme as regras da rede.

## Como executar no Windows (VS Code)
1. Extraia a pasta `sistema_votacao`.
2. Abra a pasta no VS Code.
3. Abra um terminal e inicie o servidor:

   ```powershell
   python servidor.py
   ```

4. Abra três terminais separados (ou janelas separadas) e execute em cada um:

   ```powershell
   python cliente.py
   ```

5. Para testar no mesmo computador, informe `127.0.0.1` em cada cliente. Use nomes diferentes.
6. O primeiro cliente cadastrado é o organizador e pode abrir/encerrar a votação.
7. Encerre os clientes com a opção `0`. Para encerrar o servidor, use `Ctrl+C`.

Se o comando `python` não funcionar, tente `py servidor.py` e `py cliente.py`.

## Protocolo de aplicação
Todas as mensagens TCP são objetos JSON codificados em UTF-8, terminados por `\n`. O cliente e o servidor usam `readline()` para acumular bytes até o fim da linha, em vez de presumir que uma chamada `recv()` contém uma mensagem inteira.

### Requisições TCP
Cadastro:
```json
{"tipo":"cadastro","nome":"Ana","porta_udp":53001}
```
Abrir votação (organizador):
```json
{"tipo":"abrir"}
```
Votar:
```json
{"tipo":"votar","opcao":2}
```
Consultar situação e registro do próprio voto:
```json
{"tipo":"consultar"}
```
Encerrar votação (organizador):
```json
{"tipo":"encerrar"}
```
Consultar resultado após encerramento:
```json
{"tipo":"resultado"}
```

### Respostas TCP
Sucesso:
```json
{"ok":true,"mensagem":"Voto registrado","total_votos":1,"atualizacao":2}
```
Erro:
```json
{"ok":false,"erro":"Você já votou; votos duplicados são rejeitados."}
```

### Avisos UDP
Abertura:
```json
{"tipo":"votacao_aberta","atualizacao":1,"mensagem":"A votação foi aberta"}
```
Atualização:
```json
{"tipo":"votos_atualizados","atualizacao":2,"total_votos":1}
```
Encerramento:
```json
{"tipo":"votacao_encerrada","atualizacao":4,"mensagem":"A votação foi encerrada"}
```

Os avisos UDP são informativos e podem se perder. Para confirmar o estado oficial, o participante consulta o servidor por TCP.

## Regras e limitações
- O identificador é atribuído pelo servidor e é diferente para cada conexão cadastrada.
- O primeiro cliente cadastrado é o organizador de teste.
- Cada identificador pode registrar um voto.
- A apuração por opção fica oculta enquanto a votação está aberta.
- O cadastro e o voto permanecem na sessão mesmo se a conexão do cliente fechar.
- Não há autenticação real, persistência após reiniciar o servidor, reconexão automática ou garantia de uma pessoa física por voto.
