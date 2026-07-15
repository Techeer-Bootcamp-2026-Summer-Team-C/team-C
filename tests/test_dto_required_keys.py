import inspect

from pydantic import BaseModel

from backend.contracts import (
    alerts,
    archives,
    auth,
    collector,
    dashboard,
    endpoints,
    events,
    incidents,
    investigations,
    operations,
)
from backend.contracts.common import ErrorBody, ErrorDetail, ErrorEnvelope, RequestMeta

RESPONSE_MODULES = (
    auth,
    collector,
    endpoints,
    events,
    archives,
    alerts,
    incidents,
    dashboard,
    investigations,
    operations,
)
COMMON_RESPONSE_MODELS = (RequestMeta, ErrorDetail, ErrorBody, ErrorEnvelope)


def response_models() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = list(COMMON_RESPONSE_MODELS)
    for module in RESPONSE_MODULES:
        for name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate.__module__ != module.__name__:
                continue
            if not issubclass(candidate, BaseModel):
                continue
            if name.endswith(("Dto", "Data")):
                models.append(candidate)
    return models


def test_every_documented_response_field_is_a_required_key() -> None:
    optional_keys: list[str] = []
    for model in response_models():
        for field_name, field in model.model_fields.items():
            if not field.is_required():
                optional_keys.append(f"{model.__name__}.{field_name}")
    assert optional_keys == []


def test_external_response_aliases_are_camel_case_without_snake_case() -> None:
    invalid_aliases: list[str] = []
    for model in response_models():
        for field_name, field in model.model_fields.items():
            alias = field.alias or field_name
            if "_" in alias:
                invalid_aliases.append(f"{model.__name__}.{alias}")
    assert invalid_aliases == []
