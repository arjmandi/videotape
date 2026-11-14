import CoreGraphics

public enum Playback: Equatable, Sendable {
    /// A clip rolls forward and rests on the scene it lands on.
    case playing(Clip)
    /// A clip that arrived rolls backward and rests on the scene it left.
    case rewinding(Clip, to: Scene)
    case resting(Scene)
}

/// What a press did.
public enum Pressed: Equatable, Sendable {
    /// A hotspot started its move.
    case move
    /// The search bar was pressed, and the app shell asks for text to `type`.
    case bar
    /// Nothing was there, or a clip was rolling.
    case nothing
}

/// Where a viewer is in a tape. The app shell plays whatever `playback` says and reports back when a clip ends.
public struct Player: Sendable {
    public let tape: Tape
    public private(set) var playback: Playback
    /// The moves that arrived since the opening, each with the scene it left, newest last.
    private var history: [(clip: Clip, from: Scene)] = []

    public init(tape: Tape) {
        self.tape = tape
        playback = .playing(tape.opening)
    }

    /// The resting scene, or nil while a clip rolls.
    public var scene: Scene? {
        guard case .resting(let scene) = playback else { return nil }
        return scene
    }

    public var canGoBack: Bool { scene != nil && !history.isEmpty }

    public mutating func clipEnded() {
        switch playback {
        case .playing(let clip): playback = .resting(tape.scenes[clip.lands]!)
        case .rewinding(_, let scene): playback = .resting(scene)
        case .resting: break
        }
    }

    /// `point` is in fractions of the frame, with a top-left origin.
    @discardableResult
    public mutating func press(_ point: CGPoint) -> Pressed {
        press(scene?.hotspot(at: point))
    }

    @discardableResult
    public mutating func press(label: String) -> Pressed {
        press(scene?.hotspots.first { $0.label == label })
    }

    private mutating func press(_ hotspot: Hotspot?) -> Pressed {
        guard let scene, let hotspot else { return .nothing }
        if scene.search?.bar == hotspot.label { return .bar }
        move(hotspot.clip, from: scene)
        return .move
    }

    /// Types into the resting scene's search bar, which plays the one option the text names or the bar's no-match
    /// move. Returns whether a move started, which it does not without a bar.
    @discardableResult
    public mutating func type(_ text: String) -> Bool {
        guard let scene, let search = scene.search else { return false }
        move(search.option(matching: text)?.clip ?? search.noMatch, from: scene)
        return true
    }

    /// Rewinds the move that arrived. Returns the clip to play backward, or nil at the entry or while a clip rolls.
    @discardableResult
    public mutating func back() -> Clip? {
        guard scene != nil, let last = history.popLast() else { return nil }
        playback = .rewinding(last.clip, to: last.from)
        return last.clip
    }

    public mutating func startOver() {
        history = []
        playback = .playing(tape.opening)
    }

    private mutating func move(_ clip: Clip, from scene: Scene) {
        history.append((clip, scene))
        playback = .playing(clip)
    }
}
