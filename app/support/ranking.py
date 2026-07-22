def compatibility(candidate: dict, version: str | None, environment: str | None) -> float:
    values = [candidate.get("version") in (None, "", version), candidate.get("environment") in (None, "", environment)]
    return sum(values) / len(values)

def effectiveness(success: int, partial: int, failure: int) -> float:
    # Bayesian prior prevents a single success from dominating proven solutions.
    return (success + .5 * partial + 1) / (success + partial + failure + 2)

def total(rerank: float, compatible: float, effective: float) -> float:
    return round(.55 * rerank + .20 * compatible + .25 * effective, 6)
