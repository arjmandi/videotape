import AVFoundation
import Combine

/// Shows one clip at a time and cuts between clips without a gap. Each clip loads into a new player layer behind the
/// one on screen, and the cut happens once its first frame is ready. A move's first frame is the key the previous clip
/// rested on, so the cut is invisible. A rewind cuts to its clip's last frame, which is the key on screen, for the same
/// reason.
@MainActor
final class Projector {
    let layer = CALayer()
    private var onScreen: AVPlayerLayer?
    private var incoming: AVPlayerLayer?
    private var readiness: AnyCancellable?
    private var loading: AnyCancellable?
    private var endObserver: (any NSObjectProtocol)?
    private var stepper: Timer?

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
        let player = load(url)
        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification, object: player.currentItem, queue: .main
        ) { _ in
            MainActor.assumeIsolated { ended() }
        }
        show(player) {
            player.play()
            ready()
        }
    }

    /// Plays `url` backward from its last frame and pauses on its first, stepping a frame per tick. AVPlayer at rate -1
    /// drops a quarter of the frames of the stand-in's H.264 clips, while stepping shows every one.
    func rewind(_ url: URL, fps: Int, ready: @escaping @MainActor () -> Void, ended: @escaping @MainActor () -> Void) {
        let player = load(url)
        let item = player.currentItem!
        loading = item.publisher(for: \.status)
            .first { $0 == .readyToPlay }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                player.seek(to: item.duration, toleranceBefore: .zero, toleranceAfter: .zero) { _ in
                    DispatchQueue.main.async {
                        MainActor.assumeIsolated {
                            self?.show(player) {
                                self?.step(back: fps, ended: ended)
                                ready()
                            }
                        }
                    }
                }
            }
    }

    /// Stops the clip on screen and whatever was loading, and loads `url` into a paused player.
    private func load(_ url: URL) -> AVPlayer {
        onScreen?.player?.pause()
        incoming?.removeFromSuperlayer()
        incoming = nil
        readiness = nil
        loading = nil
        stepper?.invalidate()
        stepper = nil
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        endObserver = nil
        let player = AVPlayer(playerItem: AVPlayerItem(url: url))
        player.actionAtItemEnd = .pause
        return player
    }

    /// Puts the player's layer behind the one on screen, cuts to it once its first frame is ready, and then runs `then`.
    private func show(_ player: AVPlayer, then: @escaping @MainActor () -> Void) {
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
        readiness = screen.publisher(for: \.isReadyForDisplay)
            .first { $0 }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                MainActor.assumeIsolated { self?.cut(to: screen, then: then) }
            }
    }

    private func cut(to screen: AVPlayerLayer, then: @MainActor () -> Void) {
        guard screen === incoming else { return }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        onScreen?.removeFromSuperlayer()
        CATransaction.commit()
        onScreen = screen
        incoming = nil
        then()
    }

    private func step(back fps: Int, ended: @escaping @MainActor () -> Void) {
        stepper = Timer.scheduledTimer(withTimeInterval: 1 / Double(fps), repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.stepBack(ended: ended) }
        }
    }

    private func stepBack(ended: @MainActor () -> Void) {
        guard let item = onScreen?.player?.currentItem else { return }
        guard item.currentTime() > .zero else {
            stepper?.invalidate()
            stepper = nil
            return ended()
        }
        item.step(byCount: -1)
    }
}
