import AVFoundation

/// The control for player-cuts: one player layer that swaps clips with replaceCurrentItem, which shows a gap at every
/// cut. It has TapePlayer's Projector API, so the harness builds against either.
@MainActor
final class Projector {
    let layer = CALayer()
    private let screen = AVPlayerLayer(player: AVPlayer())
    private var endObserver: (any NSObjectProtocol)?
    private var shown = false

    init() {
        screen.videoGravity = .resizeAspectFill
        screen.player!.actionAtItemEnd = .pause
        layer.addSublayer(screen)
    }

    var frame: CGRect {
        get { layer.frame }
        set {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.frame = newValue
            screen.frame = layer.bounds
            CATransaction.commit()
        }
    }

    func play(_ url: URL, ready: @escaping @MainActor () -> Void, ended: @escaping @MainActor () -> Void) {
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        let item = AVPlayerItem(url: url)
        screen.player!.replaceCurrentItem(with: item)
        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main
        ) { _ in
            MainActor.assumeIsolated { ended() }
        }
        screen.player!.play()
        guard !shown else { return }
        shown = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            MainActor.assumeIsolated { ready() }
        }
    }
}
