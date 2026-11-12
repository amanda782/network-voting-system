import json
import logging
import socket
import threading
from pathlib import Path

HOST = "0.0.0.0"
PORTA_TCP = 5000
PORTA_UDP = 5001

BASE = Path(__file__).resolve().parent
ARQUIVO_OPCOES = BASE / "opcoes.json"
PASTA_LOGS = BASE / "logs"
ARQUIVO_LOG = PASTA_LOGS / "eventos.log"

with open(ARQUIVO_OPCOES, "r", encoding="utf-8") as arquivo:
    PERGUNTAS = json.load(arquivo)

if not isinstance(PERGUNTAS, list) or not PERGUNTAS:
    raise ValueError("opcoes.json deve conter uma lista de perguntas.")

for pergunta in PERGUNTAS:
    if not isinstance(pergunta, dict) or not pergunta.get("pergunta") or not pergunta.get("opcoes"):
        raise ValueError("Cada pergunta precisa ter 'pergunta' e 'opcoes'.")

participantes = {}       # id_cliente -> dados do participante
votos = {}               # id_cliente -> {indice_pergunta: id_opcao}
proxima_id = 1
votacao_aberta = False
numero_atualizacao = 0
trava = threading.Lock()
udp_envio = None


def preparar_logs():
    PASTA_LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        handlers=[
            logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


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
        return {"tipo": "__invalido__"}


def enviar_aviso(tipo, dados=None):
    mensagem = {
        "tipo": tipo,
        "atualizacao": numero_atualizacao,
        **(dados or {})
    }
    conteudo = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")

    with trava:
        destinos = [
            (p["ip"], p["porta_udp"], p["id"])
            for p in participantes.values()
        ]

    for ip, porta, id_cliente in destinos:
        try:
            udp_envio.sendto(conteudo, (ip, porta))
            logging.info("UDP | aviso=%s | destino=%s:%s | cliente=%s",
                         tipo, ip, porta, id_cliente)
        except OSError as erro:
            logging.warning("UDP | erro de envio para %s:%s | %s", ip, porta, erro)


def calcular_resultado_pergunta(indice):
    pergunta = PERGUNTAS[indice]
    contagens = {opcao["id"]: 0 for opcao in pergunta["opcoes"]}

    for votos_participante in votos.values():
        if indice in votos_participante:
            id_opcao = votos_participante[indice]
            contagens[id_opcao] += 1

    total = sum(contagens.values())
    detalhes = []
    for opcao in pergunta["opcoes"]:
        quantidade = contagens[opcao["id"]]
        detalhes.append({
            "id": opcao["id"],
            "texto": opcao["texto"],
            "votos": quantidade,
            "percentual": round(quantidade * 100 / total, 2) if total else 0
        })

    maior = max(contagens.values(), default=0)
    vencedoras = (
        [o["texto"] for o in pergunta["opcoes"] if contagens[o["id"]] == maior]
        if total else []
    )

    return {
        "pergunta": pergunta["pergunta"],
        "total_votos": total,
        "opcoes": detalhes,
        "vencedoras": vencedoras,
        "sem_votos": total == 0
    }


def calcular_resultados():
    return [
        calcular_resultado_pergunta(i)
        for i in range(len(PERGUNTAS))
    ]


def processar(requisicao, id_cliente):
    global votacao_aberta, numero_atualizacao

    if not isinstance(requisicao, dict):
        return {"ok": False, "erro": "A mensagem deve ser um objeto JSON."}

    tipo = requisicao.get("tipo")

    if tipo == "abrir":
        with trava:
            if id_cliente != "1":
                return {"ok": False, "erro": "Somente o organizador pode abrir a votação."}
            if votacao_aberta:
                return {"ok": False, "erro": "A votação já está aberta."}
            votacao_aberta = True
            numero_atualizacao += 1
            atualizacao = numero_atualizacao

        logging.info("ESTADO | votação aberta | atualização=%s", atualizacao)
        enviar_aviso("votacao_aberta", {"mensagem": "A votação foi aberta."})
        return {"ok": True, "mensagem": "Votação aberta.", "atualizacao": atualizacao}

    if tipo == "encerrar":
        with trava:
            if id_cliente != "1":
                return {"ok": False, "erro": "Somente o organizador pode encerrar a votação."}
            if not votacao_aberta:
                return {"ok": False, "erro": "A votação não está aberta."}
            votacao_aberta = False
            numero_atualizacao += 1
            atualizacao = numero_atualizacao

        logging.info("ESTADO | votação encerrada | atualização=%s", atualizacao)
        enviar_aviso("votacao_encerrada", {"mensagem": "A votação foi encerrada."})
        return {
            "ok": True,
            "mensagem": "Votação encerrada.",
            "resultados": calcular_resultados(),
            "atualizacao": atualizacao
        }

    if tipo == "votar":
        indice = requisicao.get("pergunta")
        id_opcao = requisicao.get("opcao")

        if not isinstance(indice, int) or isinstance(indice, bool) or not 1 <= indice <= len(PERGUNTAS):
            return {"ok": False, "erro": "Número de pergunta inválido."}

        pergunta_index = indice - 1
        ids_validos = [o["id"] for o in PERGUNTAS[pergunta_index]["opcoes"]]

        with trava:
            if not votacao_aberta:
                return {"ok": False, "erro": "A votação está fechada."}
            votos_cliente = votos.setdefault(id_cliente, {})
            if pergunta_index in votos_cliente:
                return {"ok": False, "erro": "Você já votou nesta pergunta."}
            if not isinstance(id_opcao, int) or isinstance(id_opcao, bool) or id_opcao not in ids_validos:
                return {"ok": False, "erro": "Opção inexistente."}

            votos_cliente[pergunta_index] = id_opcao
            numero_atualizacao += 1
            atualizacao = numero_atualizacao
            total = sum(1 for v in votos.values() if pergunta_index in v)

        logging.info("VOTO | cliente=%s | pergunta=%s | opção=%s | total=%s",
                     id_cliente, indice, id_opcao, total)
        enviar_aviso("votos_atualizados", {
            "pergunta": indice,
            "total_votos": total
        })
        return {
            "ok": True,
            "mensagem": "Voto registrado com sucesso!",
            "pergunta": indice,
            "total_votos": total,
            "atualizacao": atualizacao
        }

    if tipo == "consultar":
        with trava:
            aberta = votacao_aberta
            votos_cliente = dict(votos.get(id_cliente, {}))
            totais = [
                sum(1 for v in votos.values() if i in v)
                for i in range(len(PERGUNTAS))
            ]

        resposta = {
            "ok": True,
            "aberta": aberta,
            "votos_registrados": sorted(i + 1 for i in votos_cliente),
            "totais_por_pergunta": totais
        }
        if not aberta:
            resposta["resultados"] = calcular_resultados()
        return resposta

    if tipo == "resultado":
        with trava:
            aberta = votacao_aberta
        if aberta:
            return {"ok": False, "erro": "A apuração fica oculta até o encerramento."}
        return {"ok": True, "resultados": calcular_resultados()}

    return {"ok": False, "erro": "Tipo de mensagem desconhecido."}


def atender_cliente(conexao, endereco):
    global proxima_id
    id_cliente = None
    arquivo_socket = None

    try:
        arquivo_socket = conexao.makefile("rb")
        cadastro = receber_json(arquivo_socket)

        if not isinstance(cadastro, dict) or cadastro.get("tipo") != "cadastro":
            enviar_json(conexao, {"ok": False, "erro": "A primeira mensagem deve ser o cadastro."})
            return

        nome = cadastro.get("nome")
        porta_udp = cadastro.get("porta_udp")

        if not isinstance(nome, str) or not nome.strip():
            enviar_json(conexao, {"ok": False, "erro": "Nome inválido."})
            return
        if not isinstance(porta_udp, int) or isinstance(porta_udp, bool) or not 1 <= porta_udp <= 65535:
            enviar_json(conexao, {"ok": False, "erro": "Porta UDP inválida."})
            return

        with trava:
            id_cliente = str(proxima_id)
            proxima_id += 1
            participantes[id_cliente] = {
                "id": id_cliente,
                "nome": nome.strip(),
                "ip": endereco[0],
                "porta_udp": porta_udp
            }

        logging.info("CADASTRO | cliente=%s | nome=%s | origem=%s:%s",
                     id_cliente, nome.strip(), endereco[0], endereco[1])

        enviar_json(conexao, {
            "ok": True,
            "mensagem": "Cadastro realizado.",
            "id_cliente": id_cliente,
            "perguntas": PERGUNTAS,
            "aberta": votacao_aberta,
            "organizador": id_cliente == "1"
        })

        while True:
            requisicao = receber_json(arquivo_socket)
            if requisicao is None:
                break
            resposta = processar(requisicao, id_cliente)
            enviar_json(conexao, resposta)

    except (ConnectionError, OSError) as erro:
        logging.info("TCP | desconexão | %s", erro)
    finally:
        if arquivo_socket is not None:
            try:
                arquivo_socket.close()
            except OSError:
                pass
        conexao.close()
        if id_cliente is not None:
            logging.info("CONEXÃO | encerrada | cliente=%s", id_cliente)


def main():
    global udp_envio
    preparar_logs()
    udp_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tcp_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        tcp_servidor.bind((HOST, PORTA_TCP))
        tcp_servidor.listen(10)
        logging.info("Servidor iniciado | TCP=%s", PORTA_TCP)

        while True:
            conexao, endereco = tcp_servidor.accept()
            threading.Thread(
                target=atender_cliente,
                args=(conexao, endereco),
                daemon=True
            ).start()

    except KeyboardInterrupt:
        logging.info("Servidor encerrado pelo teclado.")
    finally:
        tcp_servidor.close()
        udp_envio.close()


if __name__ == "__main__":
    main()
