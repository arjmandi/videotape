import Foundation
import TapeKit

enum Fixture {
    static let root = Bundle.module.url(forResource: "Fixtures", withExtension: nil)!

    static func url(_ path: String) -> URL { root.appending(path: path) }

    static func tape(_ path: String) throws -> Tape { try Tape.load(url(path)) }
}

extension Player {
    /// The resting scene's name, or nil while a clip plays.
    var resting: String? { scene?.name }

    /// The path inside the tape of the clip playing forward, or nil otherwise.
    var playing: String? {
        guard case .playing(let clip) = playback else { return nil }
        return clip.path
    }

    /// The path inside the tape of the clip playing backward, with the scene it rewinds to, or nil otherwise.
    var rewinding: (clip: String, to: String)? {
        guard case .rewinding(let clip, let scene) = playback else { return nil }
        return (clip.path, scene.name)
    }

    /// Presses the middle of the resting scene's hotspot with this label.
    @discardableResult
    mutating func click(_ label: String) -> Pressed {
        guard let box = scene?.hotspots.first(where: { $0.label == label })?.box else { return .nothing }
        return press(CGPoint(x: box.x + box.w / 2, y: box.y + box.h / 2))
    }
}

extension Clip {
    var path: String { url.pathComponents.suffix(2).joined(separator: "/") }
}
