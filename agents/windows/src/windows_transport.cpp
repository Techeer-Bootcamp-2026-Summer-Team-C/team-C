#ifdef _WIN32

#include "edr_agent/windows_agent.hpp"

#include <Windows.h>
#include <ncrypt.h>
#include <wincrypt.h>
#include <winhttp.h>

#include <fstream>
#include <iostream>
#include <regex>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace edr {
namespace {

std::string read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("configuration or certificate file is unavailable");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

std::string string_field(const std::string& json, const std::string& key, bool optional = false) {
    const std::regex expression("\\\"" + key + "\\\"\\s*:\\s*(null|\\\"((?:\\\\.|[^\\\"])*)\\\")");
    std::smatch match;
    if (!std::regex_search(json, match, expression)) throw std::runtime_error("missing configuration field");
    if (match[1] == "null") { if (optional) return {}; throw std::runtime_error("required configuration field is null"); }
    std::string value = match[2];
    value = std::regex_replace(value, std::regex("\\\\\\\\"), "\\");
    return value;
}

int integer_field(const std::string& json, const std::string& key, int fallback) {
    std::smatch match;
    if (!std::regex_search(json, match, std::regex("\\\"" + key + "\\\"\\s*:\\s*([0-9]+)"))) return fallback;
    return std::stoi(match[1]);
}

std::wstring widen(const std::string& value) {
    const int size = MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0);
    std::wstring output(size, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), output.data(), size);
    return output;
}

struct InternetHandle {
    HINTERNET value{};
    ~InternetHandle() { if (value) WinHttpCloseHandle(value); }
};

std::runtime_error win32_failure(std::string_view operation, DWORD error = GetLastError()) {
    return std::runtime_error(std::string(operation) + " win32=" + std::to_string(error));
}

std::runtime_error ncrypt_failure(std::string_view operation, SECURITY_STATUS status) {
    return std::runtime_error(std::string(operation) + " ncrypt=" + std::to_string(status));
}

struct CertificateStore {
    HCERTSTORE value{};
    CertificateStore(const CertificateStore&) = delete;
    CertificateStore& operator=(const CertificateStore&) = delete;
    CertificateStore() = default;
    ~CertificateStore() { if (value) CertCloseStore(value, 0); }
};

struct CertificateContext {
    PCCERT_CONTEXT value{};
    CertificateContext(const CertificateContext&) = delete;
    CertificateContext& operator=(const CertificateContext&) = delete;
    CertificateContext() = default;
    ~CertificateContext() { if (value) CertFreeCertificateContext(value); }
};

struct PersistedPrivateKey {
    NCRYPT_PROV_HANDLE provider{};
    NCRYPT_KEY_HANDLE key{};

    PersistedPrivateKey() = default;
    PersistedPrivateKey(const PersistedPrivateKey&) = delete;
    PersistedPrivateKey& operator=(const PersistedPrivateKey&) = delete;
    PersistedPrivateKey(PersistedPrivateKey&& other) noexcept
        : provider(std::exchange(other.provider, 0)), key(std::exchange(other.key, 0)) {}
    PersistedPrivateKey& operator=(PersistedPrivateKey&& other) noexcept {
        if (this != &other) {
            cleanup();
            provider = std::exchange(other.provider, 0);
            key = std::exchange(other.key, 0);
        }
        return *this;
    }
    ~PersistedPrivateKey() { cleanup(); }

    void cleanup() noexcept {
        if (key) {
            const auto status = NCryptDeleteKey(key, 0);
            if (status != ERROR_SUCCESS) {
                std::cerr << "certificate_private_key_cleanup_failed ncrypt=" << status << '\n';
                NCryptFreeObject(key);
            }
            key = 0;
        }
        if (provider) {
            NCryptFreeObject(provider);
            provider = 0;
        }
    }
};

PersistedPrivateKey open_private_key_container(PCCERT_CONTEXT certificate) {
    DWORD size{};
    if (!CertGetCertificateContextProperty(certificate, CERT_KEY_PROV_INFO_PROP_ID, nullptr, &size)) {
        throw win32_failure("client private key metadata failed");
    }
    std::vector<BYTE> buffer(size);
    if (!CertGetCertificateContextProperty(certificate, CERT_KEY_PROV_INFO_PROP_ID, buffer.data(), &size)) {
        throw win32_failure("client private key metadata failed");
    }
    const auto* info = reinterpret_cast<const CRYPT_KEY_PROV_INFO*>(buffer.data());
    if (info->dwProvType != 0 || !info->pwszProvName || !info->pwszContainerName) {
        throw std::runtime_error("client private key provider is not CNG");
    }
    PersistedPrivateKey result;
    auto status = NCryptOpenStorageProvider(&result.provider, info->pwszProvName, 0);
    if (status != ERROR_SUCCESS) throw ncrypt_failure("client private key provider open failed", status);
    const DWORD flags = (info->dwFlags & CRYPT_MACHINE_KEYSET) ? NCRYPT_MACHINE_KEY_FLAG : 0;
    status = NCryptOpenKey(result.provider, &result.key, info->pwszContainerName, 0, flags);
    if (status != ERROR_SUCCESS) throw ncrypt_failure("client private key container open failed", status);
    return result;
}

struct SensitiveBytes {
    std::string value;
    explicit SensitiveBytes(std::string bytes) : value(std::move(bytes)) {}
    ~SensitiveBytes() { if (!value.empty()) SecureZeroMemory(value.data(), value.size()); }
};

}  // namespace

struct WinHttpCollectorClient::CertificateState {
    // 소멸 시 영구 key를 삭제하기 전에 certificate와 store를 해제하도록 member 순서를 유지한다.
    std::vector<PersistedPrivateKey> private_keys;
    CertificateStore store;
    CertificateContext certificate;

    explicit CertificateState(const std::filesystem::path& path) {
        SensitiveBytes bytes(read_file(path));
        CRYPT_DATA_BLOB blob{static_cast<DWORD>(bytes.value.size()), reinterpret_cast<BYTE*>(bytes.value.data())};
        store.value = PFXImportCertStore(&blob, L"", CRYPT_USER_KEYSET | PKCS12_ALWAYS_CNG_KSP);
        if (!store.value) throw win32_failure("client certificate import failed");

        PCCERT_CONTEXT current = nullptr;
        while ((current = CertEnumCertificatesInStore(store.value, current)) != nullptr) {
            DWORD size{};
            if (!CertGetCertificateContextProperty(current, CERT_KEY_PROV_INFO_PROP_ID, nullptr, &size)) {
                const DWORD error = GetLastError();
                if (error == CRYPT_E_NOT_FOUND) continue;
                throw win32_failure("client private key metadata failed", error);
            }
            private_keys.push_back(open_private_key_container(current));
            if (!certificate.value) {
                certificate.value = CertDuplicateCertificateContext(current);
                if (!certificate.value) throw win32_failure("client certificate context duplication failed");
            }
        }
        if (!certificate.value) throw std::runtime_error("client certificate with private key not found");
    }
};

AgentConfig AgentConfig::load(const std::filesystem::path& path) {
    const auto json = read_file(path);
    AgentConfig config;
    const auto id = string_field(json, "agentId", true); if (!id.empty()) config.agent_id = id;
    config.collector_base_url = string_field(json, "collectorBaseUrl");
    config.certificate_pfx_path = string_field(json, "certificatePfxPath");
    config.state_directory = string_field(json, "stateDirectory");
    config.watch_directory = string_field(json, "watchDirectory");
    config.capture_interface = string_field(json, "captureInterface");
    config.queue_max_events = integer_field(json, "queueMaxEvents", 5000);
    config.retry_base_seconds = integer_field(json, "retryBaseSeconds", 1);
    config.retry_max_seconds = integer_field(json, "retryMaxSeconds", 60);
    if (config.collector_base_url.rfind("https://", 0) != 0 || config.queue_max_events <= 0 ||
        config.retry_base_seconds <= 0 || config.retry_max_seconds < config.retry_base_seconds) {
        throw std::runtime_error("invalid Agent configuration");
    }
    return config;
}

WinHttpCollectorClient::WinHttpCollectorClient(AgentConfig config)
    : config_(std::move(config)), certificate_(std::make_unique<CertificateState>(config_.certificate_pfx_path)) {}

WinHttpCollectorClient::~WinHttpCollectorClient() = default;

HttpResponse WinHttpCollectorClient::post(const std::string& path, const std::string& body) const {
    const std::wstring url = widen(config_.collector_base_url + path);
    URL_COMPONENTS components{.dwStructSize = sizeof(components)};
    components.dwHostNameLength = static_cast<DWORD>(-1); components.dwUrlPathLength = static_cast<DWORD>(-1);
    if (!WinHttpCrackUrl(url.c_str(), 0, 0, &components) || components.nScheme != INTERNET_SCHEME_HTTPS) {
        throw std::runtime_error("invalid HTTPS Collector URL");
    }
    const std::wstring host(components.lpszHostName, components.dwHostNameLength);
    const std::wstring target(components.lpszUrlPath, components.dwUrlPathLength);
    InternetHandle session{WinHttpOpen(L"EDR-C-Agent/0.1", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, nullptr, nullptr, 0)};
    if (!session.value) throw win32_failure("WinHTTP session initialization failed");
    InternetHandle connection{WinHttpConnect(session.value, host.c_str(), components.nPort, 0)};
    if (!connection.value) throw win32_failure("WinHTTP connection initialization failed");
    InternetHandle request{WinHttpOpenRequest(connection.value, L"POST", target.c_str(), nullptr, WINHTTP_NO_REFERER,
                                               WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE)};
    if (!request.value) throw win32_failure("WinHTTP request initialization failed");
    if (!WinHttpSetOption(request.value, WINHTTP_OPTION_CLIENT_CERT_CONTEXT,
                          const_cast<CERT_CONTEXT*>(certificate_->certificate.value), sizeof(CERT_CONTEXT))) {
        throw win32_failure("mTLS client certificate setup failed");
    }
    constexpr wchar_t headers[] = L"Content-Type: application/json\r\n";
    if (!WinHttpSendRequest(request.value, headers, static_cast<DWORD>(-1L), const_cast<char*>(body.data()),
                            static_cast<DWORD>(body.size()), static_cast<DWORD>(body.size()), 0)) {
        throw win32_failure("WinHTTP send failed");
    }
    if (!WinHttpReceiveResponse(request.value, nullptr)) throw win32_failure("WinHTTP receive failed");
    DWORD status{}, status_size = sizeof(status);
    if (!WinHttpQueryHeaders(request.value, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, nullptr, &status,
                             &status_size, nullptr)) {
        throw win32_failure("WinHTTP status query failed");
    }
    std::string response;
    for (;;) {
        DWORD available{};
        if (!WinHttpQueryDataAvailable(request.value, &available)) throw win32_failure("WinHTTP body availability failed");
        if (available == 0) break;
        const auto offset = response.size(); response.resize(offset + available); DWORD read{};
        if (!WinHttpReadData(request.value, response.data() + offset, available, &read)) {
            throw win32_failure("WinHTTP body read failed");
        }
        response.resize(offset + read);
    }
    return {static_cast<int>(status), std::move(response)};
}

}  // namespace edr

#endif
