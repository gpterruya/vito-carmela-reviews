import requests

from google_business import (
    ACCOUNT_ID,
    LOCATION_ID,
    REVIEWS_API,
    get,
    get_headers,
)


def get_reviews_url():
    """Endpoint de listagem de avaliações do local."""

    return (
        f"{REVIEWS_API}"
        f"/accounts/{ACCOUNT_ID}"
        f"/locations/{LOCATION_ID}"
        f"/reviews"
    )


def get_reviews():
    """Busca a primeira página de avaliações do local."""

    return get(get_reviews_url())


def get_review_list():
    """Retorna as avaliações de todas as páginas em uma única lista.

    Qualquer erro da API é propagado por get(); nesse caso nenhuma
    lista (nem parcial) é retornada.
    """

    url = get_reviews_url()

    data = get_reviews()
    reviews = list(data.get("reviews", []))
    next_token = data.get("nextPageToken")

    seen_tokens = set()

    while next_token:
        if next_token in seen_tokens:
            raise RuntimeError(
                "A API retornou um nextPageToken repetido; "
                "paginação interrompida para evitar um loop infinito."
            )

        seen_tokens.add(next_token)

        data = get(url, params={"pageToken": next_token})
        reviews.extend(data.get("reviews", []))
        next_token = data.get("nextPageToken")

    return reviews


def reply_to_review(review_id, comment):
    """Publica ou atualiza a resposta de uma avaliação."""

    url = (
        f"{REVIEWS_API}"
        f"/accounts/{ACCOUNT_ID}"
        f"/locations/{LOCATION_ID}"
        f"/reviews/{review_id}/reply"
    )

    payload = {
        "comment": comment
    }

    response = requests.put(
        url,
        headers=get_headers(),
        json=payload,
    )

    response.raise_for_status()

    return response.json()
