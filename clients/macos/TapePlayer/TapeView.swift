import AppKit
import TapeKit

/// The whole window: the tape's frames and nothing else. While a scene rests, its hotspots take clicks, show a
/// pointing hand, and appear to accessibility as buttons, followed by each of the scene's words as static text. A
/// search bar takes typed text through the platform's sheet.
@MainActor
final class TapeView: NSView, NSMenuItemValidation {
    private var player: Player
    private let projector = Projector()
    private var buttons: [HotspotButton] = []
    private var words: [WordText] = []
    private var firstFrame: (() -> Void)?

    var tape: Tape { player.tape }

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

    @objc func back(_ sender: Any?) {
        guard player.back() != nil else { return }
        render()
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        item.action == #selector(back(_:)) ? player.canGoBack : true
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let video = videoRect
        let fraction = CGPoint(x: (point.x - video.minX) / video.width, y: (point.y - video.minY) / video.height)
        pressed(player.press(fraction))
    }

    fileprivate func press(_ label: String) -> Bool {
        pressed(player.press(label: label))
    }

    @discardableResult
    private func pressed(_ outcome: Pressed) -> Bool {
        switch outcome {
        case .move: render()
        case .bar: ask(text: "")
        case .nothing: return false
        }
        return true
    }

    /// A printable key on a scene with a search bar opens the sheet with that key in the field.
    override func keyDown(with event: NSEvent) {
        guard player.scene?.search != nil, let text = event.characters, !text.isEmpty,
              event.modifierFlags.isDisjoint(with: [.command, .control]), text.unicodeScalars.allSatisfy(\.isPrintable) else {
            return super.keyDown(with: event)
        }
        ask(text: text)
    }

    /// The platform's text sheet: the bar's placeholder over one text field. Return types the field into the bar, and
    /// Escape closes the sheet and stays.
    private func ask(text: String) {
        guard let window, let search = player.scene?.search else { return }
        let alert = NSAlert()
        alert.messageText = search.bar
        alert.addButton(withTitle: "Search")
        alert.addButton(withTitle: "Cancel")
        let field = NSTextField(string: text)
        field.frame = NSRect(x: 0, y: 0, width: 240, height: 24)
        alert.accessoryView = field
        alert.beginSheetModal(for: window) { [weak self] response in
            guard response == .alertFirstButtonReturn, let self, player.type(field.stringValue) else { return }
            render()
        }
        // The field selects all its text on focus, so the next typed key would replace the first.
        alert.window.makeFirstResponder(field)
        field.currentEditor()?.selectedRange = NSRange(location: (text as NSString).length, length: 0)
    }

    private func render() {
        let shown: @MainActor () -> Void = { [weak self] in
            self?.firstFrame?()
            self?.firstFrame = nil
        }
        let ended: @MainActor () -> Void = { [weak self] in
            self?.player.clipEnded()
            self?.render()
        }
        switch player.playback {
        case .playing(let clip): projector.play(clip.url, ready: shown, ended: ended)
        case .rewinding(let clip, _): projector.rewind(clip.url, fps: player.tape.fps, ready: shown, ended: ended)
        case .resting: break
        }
        buttons = hotspots.map { HotspotButton(hotspot: $0, view: self) }
        words = (player.scene?.words ?? []).map { WordText(word: $0, view: self) }
        window?.invalidateCursorRects(for: self)
        updateCursor()
        NSAccessibility.post(element: self, notification: .layoutChanged)
    }

    /// Cursor rects only change the cursor when the pointer crosses their edge, so a hotspot that vanishes under a
    /// resting pointer would leave the hand showing for the whole clip.
    private func updateCursor() {
        guard let window else { return }
        let point = convert(window.mouseLocationOutsideOfEventStream, from: nil)
        guard bounds.contains(point) else { return }
        let overHotspot = hotspots.contains { rect(for: $0.box).contains(point) }
        (overHotspot ? NSCursor.pointingHand : NSCursor.arrow).set()
    }

    private var hotspots: [Hotspot] { player.scene?.hotspots ?? [] }

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

    override func accessibilityLabel() -> String? { player.scene?.name ?? "" }

    override func accessibilityChildren() -> [Any]? { buttons + words }

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

/// One of the resting scene's words as a screen reader reads it: static text that spans the tape.
private final class WordText: NSAccessibilityElement {
    private weak var view: TapeView?

    init(word: String, view: TapeView) {
        self.view = view
        super.init()
        setAccessibilityRole(.staticText)
        setAccessibilityValue(word)
        setAccessibilityParent(view)
    }

    override func isAccessibilityElement() -> Bool { true }

    override func accessibilityFrame() -> NSRect {
        guard let view else { return .zero }
        return MainActor.assumeIsolated { NSAccessibility.screenRect(fromView: view, rect: view.bounds) }
    }
}

private extension Unicode.Scalar {
    /// A character a person types into a field, as opposed to a control, function or arrow key.
    var isPrintable: Bool { ![.control, .privateUse, .format].contains(properties.generalCategory) }
}
