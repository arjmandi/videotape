import AVFoundation
import Combine

/// Shows one clip at a time and cuts between clips without a gap. Each clip loads into a new player layer behind the
/// one on screen, and the cut happens once its first frame is ready. A move's first frame is the key the previous clip
/// rested on, so the cut is invisible.
@MainActor
final class Projector {
    let layer = CALayer()
    private var onScreen: AVPlayerLayer?
    private var incoming: AVPlayerLayer?
    private var readiness: AnyCancellable?
    private var endObserver: (any NSObjectProtocol)?

    var frame: CGRect {
        get { layer.frame }
        set {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            layer.frame = newValue
            layer.sublayers?.forEach { $0.frame = layer.bounds }
            CATransaction.commit()
        }
    }

    /// Plays `url` from its first frame and pauses on its last. `ready` runs when the clip is on screen, `ended` when
    /// it reaches its last frame. Playing another clip first cancels both.
    func play(_ url: URL, ready: @escaping @MainActor () -> Void, ended: @escaping @MainActor () -> Void) {
        onScreen?.player?.pause()
        incoming?.removeFromSuperlayer()
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }

        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        player.actionAtItemEnd = .pause
        let screen = AVPlayerLayer(player: player)
        screen.videoGravity = .resizeAspectFill
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        screen.frame = layer.bounds
        if let onScreen {
            layer.insertSublayer(screen, below: onScreen)
        } else {
            layer.addSublayer(screen)
        }
        CATransaction.commit()
        incoming = screen

        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main
        ) { _ in
            MainActor.assumeIsolated { ended() }
        }
        readiness = screen.publisher(for: \.isReadyForDisplay)
            .first { $0 }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                MainActor.assumeIsolated { self?.cut(to: screen, ready: ready) }
            }
    }

    private func cut(to screen: AVPlayerLayer, ready: @MainActor () -> Void) {
        guard screen === incoming else { return }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        onScreen?.removeFromSuperlayer()
        CATransaction.commit()
        onScreen = screen
        incoming = nil
        screen.player?.play()
        ready()
    }
}
