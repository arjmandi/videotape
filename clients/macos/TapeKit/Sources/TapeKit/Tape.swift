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

/// One option of a search bar. Typing its label plays its clip, and so does its hotspot when the checks found its box.
public struct Option: Equatable, Sendable {
    public let label: String
    public let clip: Clip
}

/// A search bar with options.
public struct Search: Equatable, Sendable {
    /// The bar's placeholder, which is also its hotspot's label when the checks found its box.
    public let bar: String
    public let options: [Option]
    /// The clip the bar plays when the typed text picks no option.
    public let noMatch: Clip

    /// The one option whose label the text names, ignoring case: the whole label, or a prefix that starts at the label's
    /// start or after a character that is not a letter or digit. Nil when no option matches, or more than one does.
    public func option(matching text: String) -> Option? {
        let text = text.lowercased()
        guard !text.isEmpty else { return nil }
        let matches = options.filter { Self.startsAWord(of: $0.label.lowercased(), with: text) }
        return matches.count == 1 ? matches[0] : nil
    }

    private static func startsAWord(of label: String, with text: String) -> Bool {
        var previous: Character?
        for index in label.indices {
            defer { previous = label[index] }
            guard previous.map({ !$0.isLetter && !$0.isNumber }) ?? true else { continue }
            if label[index...].hasPrefix(text) { return true }
        }
        return false
    }
}

public struct Scene: Equatable, Sendable {
    public let name: String
    /// Every string on screen in reading order, which is what a screen reader reads.
    public let words: [String]
    public let hotspots: [Hotspot]
    /// The search bar with options, on a state that shows one.
    public let search: Search?

    /// `point` is in fractions of the frame, with a top-left origin. Overlapping boxes resolve to the first hotspot in tape order.
    public func hotspot(at point: CGPoint) -> Hotspot? {
        hotspots.first { $0.box.contains(point) }
    }
}

/// What made the tape, from the `made` block of `tape.json`.
public struct Made: Equatable, Sendable {
    /// The app and the story, each by name and version, such as `contrail 0.1.0 + terminal 1.0.0`.
    public let label: String
    public let id: String
}

public struct Tape: Equatable, Sendable {
    public let directory: URL
    public let size: CGSize
    public let fps: Int
    public let opening: Clip
    public let scenes: [String: Scene]
    public let made: Made

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
        func clip(_ move: String, played label: String, in scene: String) throws(TapeError) -> Clip {
            guard let clip = moves[move] else { throw .unknownMove(scene: scene, label: label, move: move) }
            return clip
        }

        var scenes: [String: Scene] = [:]
        for name in raw.scenes.keys.sorted() {
            let scene = raw.scenes[name]!
            var hotspots: [Hotspot] = []
            for hotspot in scene.hotspots {
                hotspots.append(Hotspot(label: hotspot.label, box: hotspot.box, clip: try clip(hotspot.move, played: hotspot.label, in: name)))
            }
            var search: Search?
            if let bar = scene.search {
                var options: [Option] = []
                for option in bar.options {
                    options.append(Option(label: option.label, clip: try clip(option.move, played: option.label, in: name)))
                }
                search = Search(bar: bar.bar, options: options, noMatch: try clip(bar.noMatch.move, played: "no_match", in: name))
            }
            scenes[name] = Scene(name: name, words: scene.words, hotspots: hotspots, search: search)
        }
        return Tape(
            directory: directory,
            size: CGSize(width: raw.size.width, height: raw.size.height),
            fps: raw.fps,
            opening: opening,
            scenes: scenes,
            made: Made(label: raw.made.label, id: raw.made.id)
        )
    }

    /// The tape path among an app's launch arguments, after the executable. AppKit reads `-Key value` pairs as user
    /// defaults, and Xcode adds some, so a flag and the value after it are skipped.
    public static func path(inArguments arguments: some Sequence<String>) -> String? {
        var rest = arguments.makeIterator()
        while let argument = rest.next() {
            guard argument.hasPrefix("-") else { return argument }
            _ = rest.next()
        }
        return nil
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
    struct Option: Decodable { let label, move: String }
    struct NoMatch: Decodable { let move: String }
    struct Search: Decodable {
        let bar: String
        let options: [Option]
        let noMatch: NoMatch
        enum CodingKeys: String, CodingKey { case bar, options, noMatch = "no_match" }
    }
    struct Scene: Decodable { let words: [String]; let hotspots: [Hotspot]; let search: Search? }
    struct Made: Decodable { let label, id: String }

    let size: Size
    let fps: Int
    let opening: Clip
    let scenes: [String: Scene]
    let moves: [String: Clip]
    let made: Made
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
