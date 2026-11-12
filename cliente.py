import json
import socket
import threading

IP_SERVIDOR_PADRAO = "127.0.0.1"
PORTA_TCP = 5000


def enviar_json(conexao, dados):
    mensagem = json.dumps(dados, ensure_ascii=False) + "\n"
    conexao.sendall(mensagem.encode("utf-8"))


def receber_json(arquivo_socket):
    linha = arquivo_socket.readline()
    if not linha:
        return None
    try:
        return json.loads(linha.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "erro": "Resposta inválida recebida do servidor."}


def ouvir_udp(udp_cliente, parar):
    while not parar.is_set():
        try:
            dados, origem = udp_cliente.recvfrom(4096)
            aviso = json.loads(dados.decode("utf-8"))
            print(
                "\n[AVISO UDP] {} | atualização {} | {}\n".format(
                    aviso.get("tipo", "?"),
                    aviso.get("atualizacao", "?"),
                    aviso.get("mensagem", "Votos registrados: {}".format(
                        aviso.get("total_votos", "?")
                    ))
                )
            )
        except socket.timeout:
            continue
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            break


def mostrar_perguntas(perguntas):
    print("\n========== PERGUNTAS ==========")
    for i, pergunta in enumerate(perguntas, start=1):
        print("{}. {}".format(i, pergunta["pergunta"]))
        for opcao in pergunta["opcoes"]:
            print("   {} - {}".format(opcao["id"], opcao["texto"]))


def mostrar_resultados(resultados):
    print("\n========== RESULTADOS FINAIS ==========")
    for i, resultado in enumerate(resultados, start=1):
        print("\n{}. {}".format(i, resultado["pergunta"]))
        print("Total de votos:", resultado["total_votos"])
        if resultado["sem_votos"]:
            print("Nenhum voto foi registrado nesta pergunta.")
        else:
            for opcao in resultado["opcoes"]:
                print("{}: {} voto(s) — {}%".format(
                    opcao["texto"], opcao["votos"], opcao["percentual"]
                ))
            if len(resultado["vencedoras"]) == 1:
                print("Opção vencedora:", resultado["vencedoras"][0])
            else:
                print("Empate entre:", ", ".join(resultado["vencedoras"]))


def main():
    ip_servidor = input(
        "IP do servidor [127.0.0.1 para o mesmo computador]: "
    ).strip() or IP_SERVIDOR_PADRAO

    nome = input("Seu nome: ").strip()
    while not nome:
        nome = input("O nome não pode ficar vazio. Digite seu nome: ").strip()

    udp_cliente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_cliente.bind(("0.0.0.0", 0))
    udp_cliente.settimeout(1.0)
    porta_udp = udp_cliente.getsockname()[1]

    parar = threading.Event()
    thread_udp = threading.Thread(
        target=ouvir_udp,
        args=(udp_cliente, parar),
        daemon=True
    )
    thread_udp.start()

    conexao = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    arquivo_socket = None

    try:
        conexao.connect((ip_servidor, PORTA_TCP))
        arquivo_socket = conexao.makefile("rb")

        enviar_json(conexao, {
            "tipo": "cadastro",
            "nome": nome,
            "porta_udp": porta_udp
        })
        cadastro = receber_json(arquivo_socket)

        if not cadastro or not cadastro.get("ok"):
            print("Falha no cadastro:", (cadastro or {}).get("erro", "sem resposta"))
            return

        id_cliente = cadastro["id_cliente"]
        organizador = cadastro.get("organizador", False)
        perguntas = cadastro["perguntas"]

        print("\nCadastro concluído!")
        print("Seu identificador nesta sessão:", id_cliente)
        print("Sua porta UDP:", porta_udp)
        if organizador:
            print("Você é o organizador (primeiro cliente conectado).")


        while True:
            print("\n========== MENU ==========")
            if organizador:
                print("1 - Abrir votação")
                print("2 - Encerrar votação")
            print("3 - Votar em uma pergunta")
            print("4 - Consultar meus votos e situação")
            print("5 - Ver resultado final")
            print("0 - Sair")

            escolha = input("Escolha: ").strip()

            if escolha == "0":
                break
            elif escolha == "1" and organizador:
                requisicao = {"tipo": "abrir"}
            elif escolha == "2" and organizador:
                requisicao = {"tipo": "encerrar"}
            elif escolha == "3":
                mostrar_perguntas(perguntas)
                try:
                    numero_pergunta = int(input("Número da pergunta: ").strip())
                    if not 1 <= numero_pergunta <= len(perguntas):
                        print("Número de pergunta inválido.")
                        continue

                    pergunta = perguntas[numero_pergunta - 1]
                    print("\n" + pergunta["pergunta"])
                    for opcao in pergunta["opcoes"]:
                        print("{} - {}".format(opcao["id"], opcao["texto"]))

                    id_opcao = int(input("Número da opção: ").strip())
                except ValueError:
                    print("Entrada inválida: digite um número inteiro.")
                    continue

                requisicao = {
                    "tipo": "votar",
                    "pergunta": numero_pergunta,
                    "opcao": id_opcao
                }
            elif escolha == "4":
                requisicao = {"tipo": "consultar"}
            elif escolha == "5":
                requisicao = {"tipo": "resultado"}
            else:
                print("Opção de menu inválida.")
                continue

            try:
                enviar_json(conexao, requisicao)
                resposta = receber_json(arquivo_socket)
            except (OSError, ConnectionError):
                print("A conexão com o servidor foi encerrada.")
                break

            if resposta is None:
                print("O servidor encerrou a conexão.")
                break

            if not resposta.get("ok"):
                print("Operação rejeitada:", resposta.get("erro", "erro desconhecido"))
                continue

            tipo = requisicao["tipo"]

            if tipo == "consultar":
                print("\nVotação:", "ABERTA" if resposta["aberta"] else "ENCERRADA")
                registrados = resposta["votos_registrados"]
                print("Perguntas em que você já votou:",
                      ", ".join(map(str, registrados)) if registrados else "Nenhuma")
                for i, total in enumerate(resposta["totais_por_pergunta"], start=1):
                    print("Pergunta {}: {} voto(s)".format(i, total))
                if not resposta["aberta"]:
                    mostrar_resultados(resposta["resultados"])

            elif tipo == "resultado":
                mostrar_resultados(resposta["resultados"])

            else:
                print(resposta.get("mensagem", "Operação concluída."))
                if "total_votos" in resposta:
                    print("Total de votos nesta pergunta:", resposta["total_votos"])
                if tipo == "encerrar":
                    mostrar_resultados(resposta["resultados"])

    except (ConnectionRefusedError, TimeoutError, OSError) as erro:
        print("Não foi possível conectar ao servidor:", erro)
    finally:
        parar.set()
        udp_cliente.close()
        if arquivo_socket is not None:
            try:
                arquivo_socket.close()
            except OSError:
                pass
        conexao.close()


if __name__ == "__main__":
    main()
