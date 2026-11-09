import AppKit
import TapeKit

/// The whole window: the tape's frames and nothing else. While a scene rests, its hotspots take clicks, show a
/// pointing hand, and appear to accessibility as buttons.
@MainActor
final class TapeView: NSView {
    private var player: Player
    private let projector = Projector()
    private var buttons: [HotspotButton] = []
    private var firstFrame: (() -> Void)?

    init(tape: Tape, firstFrame: @escaping () -> Void) {
        player = Player(tape: tape)
        self.firstFrame = firstFrame
        super.init(frame: NSRect(origin: .zero, size: tape.size))
        wantsLayer = true
        layer!.addSublayer(projector.layer)
        projector.frame = bounds
        render()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    /// Resizes the video in step with the view, so a live resize never shows a stale layer frame.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        projector.frame = bounds
    }

    @objc func startOver(_ sender: Any?) {
        player.startOver()
        render()
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let video = videoRect
        let fraction = CGPoint(x: (point.x - video.minX) / video.width, y: (point.y - video.minY) / video.height)
        if player.press(fraction) { render() }
    }

    fileprivate func press(_ label: String) -> Bool {
        guard player.press(label: label) else { return false }
        render()
        return true
    }

    private func render() {
        if case .playing(let clip) = player.playback {
            projector.play(clip.url, ready: { [weak self] in
                self?.firstFrame?()
                self?.firstFrame = nil
            }, ended: { [weak self] in
                self?.player.clipEnded()
                self?.render()
            })
        }
        buttons = hotspots.map { HotspotButton(hotspot: $0, view: self) }
        window?.invalidateCursorRects(for: self)
        NSAccessibility.post(element: self, notification: .layoutChanged)
    }

    private var hotspots: [Hotspot] {
        guard case .resting(let scene) = player.playback else { return [] }
        return scene.hotspots
    }

    /// Where the tape's frame lies in the view. Like the projector's video, it covers the view and crops what overhangs,
    /// so a window a fraction of a point off the tape's aspect ratio never shows its background at an edge.
    private var videoRect: NSRect {
        let size = player.tape.size
        let scale = max(bounds.width / size.width, bounds.height / size.height)
        let width = size.width * scale, height = size.height * scale
        return NSRect(x: bounds.midX - width / 2, y: bounds.midY - height / 2, width: width, height: height)
    }

    fileprivate func rect(for box: Box) -> NSRect {
        let video = videoRect
        return NSRect(
            x: video.minX + box.x * video.width, y: video.minY + box.y * video.height,
            width: box.w * video.width, height: box.h * video.height
        )
    }

    override func resetCursorRects() {
        for hotspot in hotspots {
            addCursorRect(rect(for: hotspot.box), cursor: .pointingHand)
        }
    }

    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .image }
    override func accessibilityIdentifier() -> String { "tape" }

    override func accessibilityLabel() -> String? {
        guard case .resting(let scene) = player.playback else { return "" }
        return scene.name
    }

    override func accessibilityChildren() -> [Any]? { buttons }

    override func accessibilityHitTest(_ point: NSPoint) -> Any? {
        // The closure runs synchronously on this thread, so carrying its non-Sendable result out is safe.
        nonisolated(unsafe) var hit: Any = self
        MainActor.assumeIsolated {
            if let button = buttons.first(where: { $0.accessibilityFrame().contains(point) }) { hit = button }
        }
        return hit
    }
}

/// One hotspot as VoiceOver and UI tests see it: a button with the hotspot's label over the hotspot's box.
private final class HotspotButton: NSAccessibilityElement {
    private let hotspot: Hotspot
    private weak var view: TapeView?

    init(hotspot: Hotspot, view: TapeView) {
        self.hotspot = hotspot
        self.view = view
        super.init()
        setAccessibilityRole(.button)
        setAccessibilityLabel(hotspot.label)
        setAccessibilityParent(view)
    }

    override func isAccessibilityElement() -> Bool { true }

    override func accessibilityFrame() -> NSRect {
        guard let view else { return .zero }
        let box = hotspot.box
        return MainActor.assumeIsolated { NSAccessibility.screenRect(fromView: view, rect: view.rect(for: box)) }
    }

    override func accessibilityPerformPress() -> Bool {
        guard let view else { return false }
        let label = hotspot.label
        return MainActor.assumeIsolated { view.press(label) }
    }
}
