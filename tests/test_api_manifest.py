from backend.contracts.api_manifest import PRODUCT_API_CONTRACTS


def test_product_api_manifest_contains_exactly_26_unique_contracts() -> None:
    assert len(PRODUCT_API_CONTRACTS) == 26
    method_paths = {(contract.method, contract.path) for contract in PRODUCT_API_CONTRACTS}
    assert len(method_paths) == 26
    assert sum(contract.path.startswith("/collector/") for contract in PRODUCT_API_CONTRACTS) == 3
    assert sum(not contract.path.startswith("/collector/") for contract in PRODUCT_API_CONTRACTS) == 23


def test_manifest_contains_no_excluded_product_paths() -> None:
    paths = [contract.path for contract in PRODUCT_API_CONTRACTS]
    excluded_terms = ("report", "replay", "command")
    assert all(term not in path for path in paths for term in excluded_terms)
