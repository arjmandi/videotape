import CoreGraphics
import Foundation

public struct Clip: Equatable, Sendable {
    public let url: URL
    /// The scene this clip rests on when it ends.
    public let lands: String
}

/// A rectangle in fractions of the frame, with a top-left origin.
public struct Box: Equatable, Sendable, Decodable {
    public let x, y, w, h: Double

    /// Half-open, so boxes that share an edge never both claim a point on it.
    public func contains(_ point: CGPoint) -> Bool {
        point.x >= x && point.x < x + w && point.y >= y && point.y < y + h
    }
}

public struct Hotspot: Equatable, Sendable {
    public let label: String
    public let box: Box
    public let clip: Clip
}

public struct Scene: Equatable, Sendable {
    public let name: String
    public let hotspots: [Hotspot]

    /// `point` is in fractions of the frame, with a top-left origin. Overlapping boxes resolve to the first hotspot in tape order.
    public func hotspot(at point: CGPoint) -> Hotspot? {
        hotspots.first { $0.box.contains(point) }
    }
}

public struct Tape: Equatable, Sendable {
    public let directory: URL
    public let size: CGSize
    public let opening: Clip
    public let scenes: [String: Scene]

    /// The folder the tape was rendered from, so `examples/surf_shop/tape` is named `surf_shop`.
    public var name: String { directory.deletingLastPathComponent().lastPathComponent }

    /// Reads a tape from its directory or its `tape.json`, and resolves every name it uses.
    public static func load(_ url: URL) throws(TapeError) -> Tape {
        let manifestURL = manifest(url)
        let directory = manifestURL.deletingLastPathComponent().standardizedFileURL
        guard let data = try? Data(contentsOf: manifestURL) else { throw .missingManifest(manifestURL) }
        let raw: Manifest
        do {
            raw = try JSONDecoder().decode(Manifest.self, from: data)
        } catch {
            throw .malformedManifest(manifestURL, reason: reason(error))
        }

        func resolve(_ clip: Manifest.Clip) throws(TapeError) -> Clip {
            guard raw.scenes[clip.lands] != nil else { throw .unknownScene(clip: clip.clip, lands: clip.lands) }
            let url = directory.appending(path: clip.clip)
            guard FileManager.default.fileExists(atPath: url.path(percentEncoded: false)) else {
                throw .missingClip(clip.clip, in: directory)
            }
            return Clip(url: url, lands: clip.lands)
        }

        let opening = try resolve(raw.opening)
        var moves: [String: Clip] = [:]
        for name in raw.moves.keys.sorted() {
            moves[name] = try resolve(raw.moves[name]!)
        }
        var scenes: [String: Scene] = [:]
        for name in raw.scenes.keys.sorted() {
            var hotspots: [Hotspot] = []
            for hotspot in raw.scenes[name]!.hotspots {
                guard let clip = moves[hotspot.move] else {
                    throw .unknownMove(scene: name, label: hotspot.label, move: hotspot.move)
                }
                hotspots.append(Hotspot(label: hotspot.label, box: hotspot.box, clip: clip))
            }
            scenes[name] = Scene(name: name, hotspots: hotspots)
        }
        return Tape(
            directory: directory,
            size: CGSize(width: raw.size.width, height: raw.size.height),
            opening: opening,
            scenes: scenes
        )
    }

    /// Finds the tape a launch argument names. A relative path tries the working directory first, then each folder
    /// above the app bundle, because `open` launches an app with `/` as its working directory.
    public static func locate(_ path: String, cwd: URL, app: URL) throws(TapeError) -> URL {
        if path.hasPrefix("/") { return URL(filePath: path) }
        let ancestors = sequence(first: app.deletingLastPathComponent()) {
            $0.path(percentEncoded: false) == "/" ? nil : $0.deletingLastPathComponent()
        }
        for base in [cwd] + ancestors {
            let candidate = base.appending(path: path).standardizedFileURL
            if FileManager.default.fileExists(atPath: manifest(candidate).path(percentEncoded: false)) {
                return candidate
            }
        }
        throw .notFound(path, cwd: cwd, app: app)
    }

    private static func manifest(_ url: URL) -> URL {
        url.lastPathComponent == "tape.json" ? url : url.appending(path: "tape.json")
    }
}

private struct Manifest: Decodable {
    struct Size: Decodable { let width, height: Double }
    struct Clip: Decodable { let clip, lands: String }
    struct Hotspot: Decodable { let label: String; let box: Box; let move: String }
    struct Scene: Decodable { let hotspots: [Hotspot] }

    let size: Size
    let opening: Clip
    let scenes: [String: Scene]
    let moves: [String: Clip]
}

private func reason(_ error: any Error) -> String {
    func path(_ keys: [any CodingKey]) -> String {
        keys.map { $0.intValue.map(String.init) ?? $0.stringValue }.joined(separator: ".")
    }
    switch error as? DecodingError {
    case .keyNotFound(let key, let context): return "missing \"\(path(context.codingPath + [key]))\""
    case .typeMismatch(_, let context), .valueNotFound(_, let context):
        return "\"\(path(context.codingPath))\" has the wrong type"
    case .dataCorrupted(let context) where context.codingPath.isEmpty: return "not valid JSON"
    case .dataCorrupted(let context): return "\"\(path(context.codingPath))\" is invalid"
    default: return error.localizedDescription
    }
}
