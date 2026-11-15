import json
import logging
import os
import re
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from reviews import get_review_list, reply_to_review

# Na nuvem, VICA_DATA_DIR aponta para uma pasta temporária.
DATA_DIR = Path(
    os.environ.get("VICA_DATA_DIR")
    or r"G:\Meu Drive\Adote Vi.Ca - Automação de Avaliações"
)
REVIEWS_FILE = DATA_DIR / "reviews_to_process.json"
SUGGESTIONS_FILE = DATA_DIR / "suggestions.json"
HISTORY_DIR = DATA_DIR / "historico"

LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "automacao.log"

STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

NOT_PUBLISHED = "Nenhuma resposta foi publicada."

# No modo --ciclo, avisa no log se o Cowork demorar mais que isso.
COWORK_WAIT_WARNING = 2 * 3600  # segundos

log = logging.getLogger("vica")


class ValidationError(Exception):
    """Erro de validação dos arquivos de entrada."""


class ConsoleFormatter(logging.Formatter):
    """Só a mensagem; o traceback fica apenas no arquivo de log."""

    def format(self, record):
        return record.getMessage()


def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter())

    log.setLevel(logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console_handler)


def to_export(review):
    return {
        "review_id": review.get("reviewId"),
        "reviewer_name": review.get("reviewer", {}).get("displayName"),
        "rating": STARS.get(review.get("starRating")),
        "comment": review.get("comment", ""),
        "create_time": review.get("createTime"),
        "has_reply": "reviewReply" in review,
    }


# ---------------------------------------------------------------------------
# Histórico por avaliação
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def history_folder(review):
    """Pasta da avaliação: <data da avaliação>_<primeiro nome>_<fim do id>.

    O nome depende só dos dados da avaliação, então a exportação e a
    publicação (que podem rodar em dias diferentes) chegam à mesma pasta.
    """

    date = (review.get("create_time") or "")[:10] or "sem-data"
    first_name = (review.get("reviewer_name") or "").split(" ")[0]
    first_name = re.sub(r'[<>:"/\\|?*\s.]', "", first_name) or "Anonimo"
    suffix = re.sub(r"[^A-Za-z0-9]", "", review["review_id"])[-8:]

    return HISTORY_DIR / f"{date}_{first_name}_{suffix}"


def save_history_file(folder, name, data):
    """Grava um JSON no histórico sem nunca apagar o que já existe.

    Se o arquivo já existir com o mesmo conteúdo, nada é feito; se
    existir com conteúdo diferente, a nova versão recebe a data e a hora
    no nome.
    """

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    content = json.dumps(data, ensure_ascii=False, indent=2)

    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return path
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = folder / f"{name}_{stamp}.json"

    with path.open("x", encoding="utf-8") as f:
        f.write(content)

    log.info(f"Histórico: {path.relative_to(DATA_DIR)} gravado.")
    return path


# ---------------------------------------------------------------------------
# Etapa 1: exportação de todas as avaliações pendentes
# ---------------------------------------------------------------------------

def export_pending_reviews():
    try:
        reviews = get_review_list()
    except Exception as error:
        log.error(f"Erro ao consultar as avaliações no Google: {error}", exc_info=True)
        return

    log.info(f"Encontradas {len(reviews)} avaliações.")

    pending = [r for r in reviews if "reviewReply" not in r]

    if not pending:
        log.info("Nenhuma avaliação pendente encontrada. Nenhum arquivo foi criado.")
        return

    exported = [to_export(r) for r in pending]

    try:
        with REVIEWS_FILE.open("x", encoding="utf-8") as f:
            json.dump(exported, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        log.warning(f"O arquivo {REVIEWS_FILE} já existe. Nada foi sobrescrito.")
        return
    except OSError as error:
        log.error(f"Não foi possível gravar {REVIEWS_FILE}: {error}", exc_info=True)
        return

    log.info(f"{len(exported)} avaliação(ões) pendente(s) exportada(s) para {REVIEWS_FILE}")

    for item, original in zip(exported, pending):
        log.info(f"  - {item['review_id']} ({item['rating']} estrela(s))")
        try:
            save_history_file(
                history_folder(item),
                "avaliacao",
                {
                    "exportada_em": now_iso(),
                    "avaliacao": item,
                    "original_google": original,
                },
            )
        except OSError as error:
            log.error(
                f"Não foi possível gravar a avaliação {item['review_id']} "
                f"no histórico: {error}",
                exc_info=True,
            )

    log.info(
        "Próximo passo: peça ao Cowork para gerar "
        "suggestions.json a partir desse arquivo."
    )


# ---------------------------------------------------------------------------
# Etapa 2: carregamento e validação dos arquivos
# ---------------------------------------------------------------------------

def load_list(path):
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as error:
        raise ValidationError(f"{path.name} não é um JSON válido: {error}")
    except OSError as error:
        raise ValidationError(f"Não foi possível ler {path.name}: {error}")

    if not isinstance(data, list) or not data:
        raise ValidationError(f"{path.name} deve conter uma lista JSON não vazia.")

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValidationError(
                f"O item {index} de {path.name} deve ser um objeto JSON."
            )
        review_id = item.get("review_id")
        if not isinstance(review_id, str) or not review_id.strip():
            raise ValidationError(
                f"Campo review_id ausente ou vazio no item {index} de {path.name}."
            )

    ids = [item["review_id"] for item in data]
    if len(ids) != len(set(ids)):
        raise ValidationError(f"{path.name} contém review_id repetido.")

    return data


def load_and_validate():
    """Retorna a lista de (avaliação, sugestão, resposta) prontas para publicar.

    Erros na estrutura dos arquivos interrompem tudo. Problemas de um item
    só (sugestão ausente ou vazia) apenas tiram aquele item da lista.
    """

    reviews = load_list(REVIEWS_FILE)
    suggestions = {s["review_id"]: s for s in load_list(SUGGESTIONS_FILE)}

    for review in reviews:
        if review.get("has_reply") is not False:
            raise ValidationError(
                f"Em {REVIEWS_FILE.name}, has_reply precisa ser false "
                f"(avaliação {review['review_id']}: {review.get('has_reply')!r})."
            )

    review_ids = {r["review_id"] for r in reviews}
    for suggestion_id in suggestions.keys() - review_ids:
        log.warning(
            f"Sugestão para uma avaliação que não foi exportada ignorada: {suggestion_id}"
        )

    items = []
    for review in reviews:
        review_id = review["review_id"]
        suggestion = suggestions.get(review_id)

        if suggestion is None:
            log.warning(f"Sem sugestão para a avaliação {review_id}; ela fica para depois.")
            continue

        reply = suggestion.get("suggested_reply")
        if not isinstance(reply, str) or not reply.strip():
            log.warning(
                f"suggested_reply vazio para a avaliação {review_id}; "
                "ela fica para depois."
            )
            continue

        items.append((review, suggestion, reply.strip()))

    return items


# ---------------------------------------------------------------------------
# Etapa 3: verificação atualizada no Google
# ---------------------------------------------------------------------------

def current_reviews_by_id():
    """Consulta o Google uma única vez. Erros da API são propagados."""

    return {r.get("reviewId"): r for r in get_review_list()}


# ---------------------------------------------------------------------------
# Etapa 4: exibição para revisão humana
# ---------------------------------------------------------------------------

def show_for_review(review, reply):
    line = "=" * 70

    print(line)
    print("AVALIAÇÃO")
    print(line)
    print(f"Avaliador: {review.get('reviewer_name') or '(sem nome)'}")
    print(f"Nota: {review.get('rating') or '(sem nota)'}")
    print("Comentário original:")
    print(review.get("comment") or "(sem comentário)")
    print()
    print(line)
    print("RESPOSTA SUGERIDA")
    print(line)
    print(reply)
    print(line)


# ---------------------------------------------------------------------------
# Etapa 5: processamento de uma avaliação
# ---------------------------------------------------------------------------

# Resultados de process_review().
PUBLISHED = "publicada"
SKIPPED = "não publicada"
FAILED = "falhou"


def process_review(review, suggestion, reply, current, publish_mode, auto_mode):
    """Publica (ou simula) uma avaliação e devolve um dos resultados acima.

    FAILED significa que os arquivos de trabalho precisam ser mantidos:
    publicação com resultado incerto ou histórico incompleto.
    """

    review_id = review["review_id"]
    folder = history_folder(review)

    log.info(f"Avaliação {review_id} ({review.get('rating')} estrela(s)):")

    # Guarda a avaliação e a sugestão antes de publicar.
    try:
        if not (folder / "avaliacao.json").exists():
            save_history_file(
                folder,
                "avaliacao",
                {"exportada_em": None, "avaliacao": review},
            )
        save_history_file(folder, "sugestao", suggestion)
        history_ok = True
    except OSError as error:
        log.error(
            f"Não foi possível gravar o histórico em {folder}: {error}",
            exc_info=True,
        )
        history_ok = False

    if current is None:
        log.warning(
            "A avaliação não foi encontrada na lista atual do Google "
            "(pode ter sido removida)."
        )
        return SKIPPED

    if "reviewReply" in current:
        log.warning("A avaliação já possui uma resposta no Google.")
        # Se fomos nós que publicamos, publicacao.json já registra isso.
        if not (folder / "publicacao.json").exists():
            try:
                save_history_file(
                    folder,
                    "resposta_existente",
                    {
                        "review_id": review_id,
                        "resposta_no_google": current["reviewReply"],
                    },
                )
            except OSError as error:
                log.error(
                    f"Não foi possível gravar a resposta existente no histórico: {error}",
                    exc_info=True,
                )
        return SKIPPED

    if not auto_mode:
        show_for_review(review, reply)

    if not publish_mode:
        return SKIPPED

    if not auto_mode:
        try:
            answer = input("Publicar esta resposta no Google? [s/N]: ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
            print()

        if answer not in ("s", "S"):
            log.info("Publicação cancelada pelo usuário.")
            return SKIPPED

    try:
        google_response = reply_to_review(review_id, reply)
    except Exception as error:
        log.error(f"Erro ao publicar a resposta: {error}", exc_info=True)
        log.error(
            "Não é possível confirmar se a resposta foi publicada. "
            "Verifique no Perfil da Empresa no Google."
        )
        return FAILED

    log.info(f"Resposta publicada com sucesso no Google (avaliação {review_id}).")
    log.info(f"Texto publicado: {reply}")

    try:
        save_history_file(
            folder,
            "publicacao",
            {
                "review_id": review_id,
                "publicada_em": now_iso(),
                "resposta_publicada": reply,
                "resposta_do_google": google_response,
            },
        )
    except OSError as error:
        log.error(
            f"Não foi possível gravar a publicação no histórico: {error}",
            exc_info=True,
        )
        history_ok = False

    if not history_ok:
        log.error(f"A resposta foi publicada, mas o histórico em {folder} ficou incompleto.")
        return FAILED

    return PUBLISHED


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if args not in ([], ["--publish"], ["--auto"], ["--ciclo"]):
        log.error(f"Argumentos inválidos: {args}")
        log.info("Uso: python app\\main.py [--publish | --auto | --ciclo]")
        log.info(NOT_PUBLISHED)
        return

    # --auto publica sem pedir confirmação. --ciclo (usado pelo Agendador
    # a cada 10 minutos) faz o mesmo e, quando não há arquivos de
    # trabalho, exporta as avaliações pendentes para o Cowork.
    cycle_mode = args == ["--ciclo"]
    auto_mode = args == ["--auto"] or cycle_mode
    publish_mode = args == ["--publish"] or auto_mode

    if not REVIEWS_FILE.exists():
        if auto_mode and not cycle_mode:
            log.info("Nenhuma avaliação exportada para publicar.")
            return
        export_pending_reviews()
        return

    if not SUGGESTIONS_FILE.exists():
        if cycle_mode:
            waiting = datetime.now().timestamp() - REVIEWS_FILE.stat().st_mtime
            if waiting > COWORK_WAIT_WARNING:
                log.warning(
                    f"O Cowork ainda não gerou suggestions.json; a exportação "
                    f"está esperando há {waiting / 3600:.1f} h."
                )
            else:
                log.info("Aguardando o Cowork gerar suggestions.json.")
            return
        log.warning(f"Falta a sugestão: {SUGGESTIONS_FILE} não existe.")
        log.info("Peça ao Cowork para gerar suggestions.json.")
        log.info(NOT_PUBLISHED)
        return

    try:
        items = load_and_validate()
    except ValidationError as error:
        log.error(f"Validação falhou: {error}")
        log.info(NOT_PUBLISHED)
        return

    if not items:
        log.warning("Nenhuma avaliação com sugestão válida.")
        log.info(NOT_PUBLISHED)
        return

    log.info(f"Verificando {len(items)} avaliação(ões) no Google...")

    try:
        current = current_reviews_by_id()
    except Exception as error:
        log.error(f"Erro ao consultar as avaliações no Google: {error}", exc_info=True)
        log.info(NOT_PUBLISHED)
        return

    if auto_mode:
        log.info("MODO AUTOMÁTICO: publicando sem confirmação.")

    results = []
    for review, suggestion, reply in items:
        results.append(
            process_review(
                review,
                suggestion,
                reply,
                current.get(review["review_id"]),
                publish_mode,
                auto_mode,
            )
        )

    log.info(
        f"Resumo: {results.count(PUBLISHED)} publicada(s), "
        f"{results.count(SKIPPED)} não publicada(s), "
        f"{results.count(FAILED)} com falha."
    )

    if not publish_mode:
        log.info("MODO SIMULAÇÃO: nada foi enviado ao Google.")
        log.info("Para publicar, rode: python app\\main.py --publish")
        return

    if FAILED in results:
        log.error(
            "Arquivos de trabalho mantidos por causa das falhas acima. "
            "Na próxima execução, as avaliações já respondidas serão puladas."
        )
        return

    # Avaliações puladas continuam pendentes no Google e voltam na
    # próxima exportação.
    REVIEWS_FILE.unlink()
    SUGGESTIONS_FILE.unlink()

    log.info("Arquivos de trabalho removidos com sucesso.")


if __name__ == "__main__":
    setup_logging()
    log.info(f"Início da execução: {' '.join(sys.argv)}")

    try:
        main()
    except Exception:
        log.critical(
            f"Erro inesperado; execução interrompida. Detalhes em {LOG_FILE}",
            exc_info=True,
        )
        sys.exit(1)
    finally:
        log.info("Fim da execução.")
