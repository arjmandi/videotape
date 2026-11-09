import Foundation
import TapeKit

enum Fixture {
    static let root = Bundle.module.url(forResource: "Fixtures", withExtension: nil)!

    static func url(_ path: String) -> URL { root.appending(path: path) }

    static func tape(_ path: String) throws -> Tape { try Tape.load(url(path)) }
}

extension Player {
    /// The resting scene's name, or nil while a clip plays.
    var resting: String? {
        guard case .resting(let scene) = playback else { return nil }
        return scene.name
    }

    /// The playing clip's path inside the tape, or nil while resting.
    var playing: String? {
        guard case .playing(let clip) = playback else { return nil }
        return clip.url.pathComponents.suffix(2).joined(separator: "/")
    }

    /// Presses the middle of the resting scene's hotspot with this label.
    @discardableResult
    mutating func click(_ label: String) -> Bool {
        guard case .resting(let scene) = playback, let box = scene.hotspots.first(where: { $0.label == label })?.box else {
            return false
        }
        return press(CGPoint(x: box.x + box.w / 2, y: box.y + box.h / 2))
    }
}
