import Foundation
import Testing

@testable import EDRAgentCore

private func fileAttributes(owner: UInt32 = 0, permissions: UInt16) -> [FileAttributeKey: Any] {
    [
        .type: FileAttributeType.typeRegular,
        .ownerAccountID: NSNumber(value: owner),
        .posixPermissions: NSNumber(value: permissions),
    ]
}

private func directoryAttributes(owner: UInt32 = 0, permissions: UInt16) -> [FileAttributeKey: Any] {
    [
        .type: FileAttributeType.typeDirectory,
        .ownerAccountID: NSNumber(value: owner),
        .posixPermissions: NSNumber(value: permissions),
    ]
}

@Test func privilegedPrivateFilesRequireRootOwnershipAndRootOnlyPermissions() throws {
    try PrivilegedFileSecurity.validateRegularFile(
        path: "/ignored/config.json",
        label: "configuration file",
        privatePermissions: true,
        attributes: fileAttributes(permissions: 0o600),
        parentAttributes: directoryAttributes(permissions: 0o755)
    )

    #expect(throws: AgentError.self) {
        try PrivilegedFileSecurity.validateRegularFile(
            path: "/ignored/config.json",
            label: "configuration file",
            privatePermissions: true,
            attributes: fileAttributes(owner: 501, permissions: 0o600),
            parentAttributes: directoryAttributes(permissions: 0o755)
        )
    }
    #expect(throws: AgentError.self) {
        try PrivilegedFileSecurity.validateRegularFile(
            path: "/ignored/config.json",
            label: "configuration file",
            privatePermissions: true,
            attributes: fileAttributes(permissions: 0o640),
            parentAttributes: directoryAttributes(permissions: 0o755)
        )
    }
}

@Test func privilegedStateDirectoryRejectsGroupOrWorldAccess() throws {
    try PrivilegedFileSecurity.validateDirectory(
        path: "/ignored/state",
        label: "state directory",
        attributes: directoryAttributes(permissions: 0o700)
    )
    #expect(throws: AgentError.self) {
        try PrivilegedFileSecurity.validateDirectory(
            path: "/ignored/state",
            label: "state directory",
            attributes: directoryAttributes(permissions: 0o750)
        )
    }
}
