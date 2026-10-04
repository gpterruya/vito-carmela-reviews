import json
import sys
from pathlib import Path

from reviews import get_review_list, reply_to_review

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REVIEWS_FILE = DATA_DIR / "reviews_to_process.json"
SUGGESTIONS_FILE = DATA_DIR / "suggestions.json"

STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

NOT_PUBLISHED = "Nenhuma resposta foi publicada."


class ValidationError(Exception):
    """Erro de validação dos arquivos de entrada."""


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
# Etapa 1: exportação de uma avaliação pendente
# ---------------------------------------------------------------------------

def export_pending_review():
    try:
        reviews = get_review_list()
    except Exception as error:
        print(f"Erro ao consultar as avaliações no Google: {error}")
        return

    print(f"Encontradas {len(reviews)} avaliações.")

    pending = [r for r in reviews if "reviewReply" not in r]

    if not pending:
        print("Nenhuma avaliação pendente encontrada. Nenhum arquivo foi criado.")
        return

    print(f"{len(pending)} avaliação(ões) pendente(s). Exportando a primeira.")

    try:
        with REVIEWS_FILE.open("x", encoding="utf-8") as f:
            json.dump([to_export(pending[0])], f, ensure_ascii=False, indent=2)
    except FileExistsError:
        print(f"O arquivo {REVIEWS_FILE} já existe. Nada foi sobrescrito.")
        return

    print(f"Avaliação exportada para {REVIEWS_FILE}")
    print(
        "Próximo passo: peça ao Cowork para gerar "
        "data/suggestions.json a partir desse arquivo."
    )


# ---------------------------------------------------------------------------
# Etapa 2: carregamento e validação dos arquivos
# ---------------------------------------------------------------------------

def load_single_item(path):
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as error:
        raise ValidationError(f"{path.name} não é um JSON válido: {error}")
    except OSError as error:
        raise ValidationError(f"Não foi possível ler {path.name}: {error}")

    if not isinstance(data, list):
        raise ValidationError(f"{path.name} deve conter uma lista JSON.")

    if len(data) != 1:
        raise ValidationError(
            f"{path.name} deve conter exatamente 1 item, mas contém {len(data)}."
        )

    item = data[0]

    if not isinstance(item, dict):
        raise ValidationError(f"O item de {path.name} deve ser um objeto JSON.")

    return item


def require_review_id(item, filename):
    review_id = item.get("review_id")

    if not isinstance(review_id, str) or not review_id.strip():
        raise ValidationError(f"Campo review_id ausente ou vazio em {filename}.")

    return review_id


def load_and_validate():
    review = load_single_item(REVIEWS_FILE)
    suggestion = load_single_item(SUGGESTIONS_FILE)

    review_id = require_review_id(review, REVIEWS_FILE.name)
    suggestion_id = require_review_id(suggestion, SUGGESTIONS_FILE.name)

    if review_id != suggestion_id:
        raise ValidationError(
            "O review_id da sugestão é diferente do review_id da avaliação "
            f"exportada.\n  Avaliação: {review_id}\n  Sugestão:  {suggestion_id}"
        )

    reply = suggestion.get("suggested_reply")

    if not isinstance(reply, str) or not reply.strip():
        raise ValidationError(
            f"Campo suggested_reply ausente ou vazio em {SUGGESTIONS_FILE.name}."
        )

    if review.get("has_reply") is not False:
        raise ValidationError(
            f"Em {REVIEWS_FILE.name}, has_reply precisa ser false "
            f"(valor atual: {review.get('has_reply')!r})."
        )

    return review, reply.strip()


# ---------------------------------------------------------------------------
# Etapa 3: verificação atualizada no Google
# ---------------------------------------------------------------------------

def find_current_review(review_id):
    """Consulta o Google novamente. Erros da API são propagados."""

    for review in get_review_list():
        if review.get("reviewId") == review_id:
            return review

    return None


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
# Fluxo principal
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if args not in ([], ["--publish"]):
        print("Uso: python app\\main.py [--publish]")
        print(NOT_PUBLISHED)
        return

    publish_mode = args == ["--publish"]

    if not REVIEWS_FILE.exists():
        export_pending_review()
        return

    if not SUGGESTIONS_FILE.exists():
        print(f"Falta a sugestão: {SUGGESTIONS_FILE} não existe.")
        print("Peça ao Cowork para gerar data/suggestions.json.")
        print(NOT_PUBLISHED)
        return

    try:
        review, reply = load_and_validate()
    except ValidationError as error:
        print(f"Validação falhou: {error}")
        print(NOT_PUBLISHED)
        return

    review_id = review["review_id"]

    print("Verificando a avaliação no Google...")

    try:
        current = find_current_review(review_id)
    except Exception as error:
        print(f"Erro ao consultar as avaliações no Google: {error}")
        print(NOT_PUBLISHED)
        return

    if current is None:
        print(
            "A avaliação não foi encontrada na lista atual do Google "
            "(pode ter sido removida)."
        )
        print(NOT_PUBLISHED)
        return

    if "reviewReply" in current:
        print("A avaliação já possui uma resposta no Google.")
        print(NOT_PUBLISHED)
        return

    show_for_review(review, reply)

    if not publish_mode:
        print("MODO SIMULAÇÃO: nada foi enviado ao Google.")
        print(NOT_PUBLISHED)
        print("Para publicar, rode: python app\\main.py --publish")
        return

    try:
        answer = input("Publicar esta resposta no Google? [s/N]: ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
        print()

    if answer not in ("s", "S"):
        print("Publicação cancelada.")
        print(NOT_PUBLISHED)
        return

    try:
        reply_to_review(review_id, reply)
    except Exception as error:
        print(f"Erro ao publicar a resposta: {error}")
        print(
            "Não é possível confirmar se a resposta foi publicada. "
            "Verifique no Perfil da Empresa no Google antes de tentar de novo."
        )
        return

    print("Resposta publicada com sucesso no Google.")

    REVIEWS_FILE.unlink()
    SUGGESTIONS_FILE.unlink()

    print("Arquivos de trabalho removidos com sucesso.")


if __name__ == "__main__":
    main()
