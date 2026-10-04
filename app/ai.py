def generate_reply(review):
    """
    Gera uma sugestão de resposta para uma avaliação.

    Por enquanto, apenas estrutura a entrada.
    A integração com o modelo de IA será adicionada posteriormente.
    """

    reviewer = review.get("reviewer", {})
    reviewer_name = reviewer.get("displayName", "cliente")

    rating = review.get("starRating", "UNKNOWN")
    comment = review.get("comment", "")

    return (
        f"[SUGESTÃO DE IA]\n\n"
        f"Olá, {reviewer_name}! Obrigado por compartilhar sua experiência.\n\n"
        f"Rating: {rating}\n"
        f"Comentário recebido: {comment}"
    )