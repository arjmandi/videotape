import Foundation

public enum TapeError: Error, Equatable, CustomStringConvertible, LocalizedError {
    case notFound(String, cwd: URL, app: URL)
    case missingManifest(URL)
    case malformedManifest(URL, reason: String)
    case unknownMove(scene: String, label: String, move: String)
    case unknownScene(clip: String, lands: String)
    case missingClip(String, in: URL)

    public var description: String {
        switch self {
        case .notFound(let path, let cwd, let app):
            "No tape.json at \(path) in \(cwd.shown) or in any folder above \(app.shown)."
        case .missingManifest(let manifest):
            "No tape.json at \(manifest.shown)."
        case .malformedManifest(let manifest, let reason):
            "\(manifest.shown) is not a tape: \(reason)."
        case .unknownMove(let scene, let label, let move):
            "\"\(label)\" in scene \"\(scene)\" plays move \"\(move)\", which tape.json does not define."
        case .unknownScene(let clip, let lands):
            "\(clip) lands on scene \"\(lands)\", which tape.json does not define."
        case .missingClip(let clip, let directory):
            "Clip \(clip) is missing from \(directory.shown)."
        }
    }

    public var errorDescription: String? { description }
}

private extension URL {
    /// The path as a person reads it, without the trailing slash a directory URL carries.
    var shown: String {
        let path = path(percentEncoded: false)
        return path.count > 1 && path.hasSuffix("/") ? String(path.dropLast()) : path
    }
}
