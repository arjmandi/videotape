import AppKit
import AVFoundation
import TapeKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    /// The newest tape's window. It stays hidden until its first frame is ready.
    private var window: NSWindow?

    /// The app's name as its bundle gives it: TapePlayer, or a published app's, such as `Contrail (Starter)`.
    private let name = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String
        ?? ProcessInfo.processInfo.processName

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = mainMenu()
        NSApp.activate()
        let app = Bundle.main.bundleURL
        let cwd = URL(filePath: FileManager.default.currentDirectoryPath, directoryHint: .isDirectory)
        do {
            if let path = Tape.path(inArguments: CommandLine.arguments.dropFirst()) {
                try play(Tape.locate(path, cwd: cwd, app: app))
            } else if let carried = Tape.carried(by: app) {
                try play(carried)
            } else {
                openDocument(nil)
            }
        } catch {
            show(error)
        }
    }

    @objc func openDocument(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.message = "Choose a tape folder or its tape.json."
        panel.canChooseDirectories = true
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try play(url)
        } catch {
            show(error)
        }
    }

    /// Opens the tape in a new window. The window that was showing stays until the new one has a frame to show, so
    /// switching tapes never shows an empty screen.
    private func play(_ url: URL) throws(TapeError) {
        let tape = try Tape.load(url)
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: fitted(tape.size)),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false
        )
        window.isReleasedWhenClosed = false
        window.title = tape.made.label
        window.contentAspectRatio = tape.size
        window.collectionBehavior = .fullScreenNone
        window.delegate = self
        let view = TapeView(tape: tape) { [weak self, weak window] in
            guard let self, let window, window === self.window else { return }
            window.makeKeyAndOrderFront(nil)
            for other in NSApp.windows where other !== window && other.contentView is TapeView {
                other.close()
            }
        }
        window.contentView = view
        window.makeFirstResponder(view)
        window.center()
        self.window = window
    }

    /// The tape's size in points, shrunk to fit the screen with the window's title bar.
    private func fitted(_ size: CGSize) -> CGSize {
        guard let screen = NSScreen.main else { return size }
        let room = NSWindow.contentRect(forFrameRect: screen.visibleFrame, styleMask: [.titled, .resizable]).size
        let scale = min(1, room.width / size.width, room.height / size.height)
        return CGSize(width: (size.width * scale).rounded(.down), height: (size.height * scale).rounded(.down))
    }

    /// Zoom fills the screen without breaking the tape's aspect ratio, which only binds live resizing.
    func windowWillUseStandardFrame(_ window: NSWindow, defaultFrame: NSRect) -> NSRect {
        let room = window.contentRect(forFrameRect: defaultFrame)
        return window.frameRect(forContentRect: AVMakeRect(aspectRatio: window.contentAspectRatio, insideRect: room))
    }

    /// The standard About panel, with the open tape's label and id under the app's name.
    @objc func about(_ sender: Any?) {
        var options: [NSApplication.AboutPanelOptionKey: Any] = [:]
        if let made = (window?.contentView as? TapeView)?.tape.made {
            options[.credits] = NSAttributedString(string: "\(made.label)\n\(made.id)")
        }
        NSApp.orderFrontStandardAboutPanel(options: options)
    }

    private func show(_ error: TapeError) {
        let alert = NSAlert()
        alert.messageText = "This tape cannot play."
        alert.informativeText = error.description
        alert.runModal()
    }

    private func mainMenu() -> NSMenu {
        let app = NSMenu()
        app.addItem(withTitle: "About \(name)", action: #selector(about(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Hide \(name)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        app.addItem(withTitle: "Quit \(name)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let file = NSMenu(title: "File")
        file.addItem(withTitle: "Open…", action: #selector(openDocument(_:)), keyEquivalent: "o")
        file.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")

        let playback = NSMenu(title: "Playback")
        playback.addItem(withTitle: "Back", action: #selector(TapeView.back(_:)), keyEquivalent: "[")
        playback.addItem(withTitle: "Start Over", action: #selector(TapeView.startOver(_:)), keyEquivalent: "r")

        let windows = NSMenu(title: "Window")
        windows.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        NSApp.windowsMenu = windows

        let bar = NSMenu()
        for menu in [app, file, playback, windows] {
            bar.addItem(withTitle: menu.title, action: nil, keyEquivalent: "").submenu = menu
        }
        return bar
    }
}
