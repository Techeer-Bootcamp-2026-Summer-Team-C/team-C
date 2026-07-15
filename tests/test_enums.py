from backend.contracts.enums import (
    EdrStateReasonCode,
    EndpointStatus,
    EventType,
    StorageStatus,
    TimePreset,
    UserLocale,
)


def values(enum_type: type) -> list[str]:
    return [item.value for item in enum_type]


def test_contract_enum_literals_are_exact() -> None:
    assert values(EndpointStatus) == ["ONLINE", "OFFLINE", "RETIRED"]
    assert values(EventType) == ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY", "L7_EVENT"]
    assert values(StorageStatus) == ["HOT", "ARCHIVED", "RESTORE_REQUESTED", "RESTORED", "RESTORE_FAILED", "EXPIRED"]
    assert values(TimePreset) == ["LATEST_15M", "LATEST_1H", "LATEST_24H", "LATEST_7D", "CUSTOM"]
    assert values(UserLocale) == ["EN", "KO"]
    assert values(EdrStateReasonCode) == [
        "MEDIUM_ENDPOINT_RISK",
        "HIGH_ENDPOINT_RISK",
        "CRITICAL_ENDPOINT_RISK",
        "OPEN_INCIDENT",
        "CRITICAL_ALERT",
        "OFFLINE_ENDPOINT",
        "STALE_ENDPOINT",
        "DEGRADED_SENSOR",
        "UNAVAILABLE_SENSOR",
        "INGEST_FAILURE",
        "INGEST_DELAYED",
        "STORAGE_FAILURE",
    ]
