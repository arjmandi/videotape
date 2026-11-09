import CoreGraphics

public enum Playback: Equatable, Sendable {
    case playing(Clip)
    case resting(Scene)
}

/// Where a viewer is in a tape. The app shell plays whatever `playback` says and reports back when a clip ends.
public struct Player: Sendable {
    public let tape: Tape
    public private(set) var playback: Playback

    public init(tape: Tape) {
        self.tape = tape
        playback = .playing(tape.opening)
    }

    public mutating func clipEnded() {
        guard case .playing(let clip) = playback else { return }
        playback = .resting(tape.scenes[clip.lands]!)
    }

    /// `point` is in fractions of the frame, with a top-left origin. Returns whether a move started.
    @discardableResult
    public mutating func press(_ point: CGPoint) -> Bool {
        guard case .resting(let scene) = playback, let hotspot = scene.hotspot(at: point) else { return false }
        playback = .playing(hotspot.clip)
        return true
    }

    @discardableResult
    public mutating func press(label: String) -> Bool {
        guard case .resting(let scene) = playback, let hotspot = scene.hotspots.first(where: { $0.label == label }) else {
            return false
        }
        playback = .playing(hotspot.clip)
        return true
    }

    public mutating func startOver() {
        playback = .playing(tape.opening)
    }
}
