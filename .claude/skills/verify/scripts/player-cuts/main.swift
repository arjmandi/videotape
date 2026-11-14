import AppKit
import TapeKit

// Plays a tape through TapePlayer's own TapeView in a borderless window and presses the next hotspot the moment a
// scene rests, starting over at scenes with none. Every tick it captures the window, which needs no Screen Recording
// permission because the window is this process's own. A cut that shows anything but the tape moves the window's
// edges away from the colour they had in the first frame.

let arguments = CommandLine.arguments
guard arguments.count == 3, let wanted = Int(arguments[2]), wanted > 0 else {
    print("usage: \(arguments[0]) <tape-dir> <cuts>")
    exit(2)
}
let tape: Tape
do {
    tape = try Tape.load(URL(filePath: arguments[1]))
} catch {
    print("error: \(error)")
    exit(2)
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let window = NSWindow(
    contentRect: NSRect(origin: CGPoint(x: 100, y: 100), size: tape.size),
    styleMask: [.borderless], backing: .buffered, defer: false
)
var start: CFTimeInterval?
let view = TapeView(tape: tape) {
    window.orderFrontRegardless()
    start = CACurrentMediaTime()
}
window.contentView = view

var captures: [(time: Double, change: Double)] = []
var cuts: [Double] = []
var firstFrame: [Double]?
var presses: [String: Int] = [:]

/// The sRGB colour of six points along the window's edges.
@MainActor
func edges(_ image: CGImage) -> [Double] {
    let bitmap = NSBitmapImageRep(cgImage: image)
    let w = image.width, h = image.height
    let points: [(Int, Int)] = [(6, 6), (w - 7, 6), (6, h - 7), (w - 7, h - 7), (6, h / 2), (w - 7, h / 2)]
    var colours: [Double] = []
    for (x, y) in points {
        let colour = bitmap.colorAt(x: x, y: y)!.usingColorSpace(.sRGB)!
        colours += [colour.redComponent * 255, colour.greenComponent * 255, colour.blueComponent * 255]
    }
    return colours
}

@MainActor
func report(after seconds: Double) -> Never {
    let gaps = zip(captures.dropFirst(), captures).map { ($0.time - $1.time) * 1000 }.sorted()
    let afterCut = cuts.map { cut in captures.filter { $0.time >= cut && $0.time < cut + 0.2 }.count }
    let flashes = captures.filter { $0.change > 40 }
    print(String(
        format: "cuts %d, captures %d over %.1f s, interval median %.1f ms, p95 %.1f ms, max %.1f ms",
        cuts.count, captures.count, seconds, gaps[gaps.count / 2], gaps[gaps.count * 95 / 100], gaps.last!
    ))
    print("fewest captures in the 200 ms after a cut: \(afterCut.min()!)")
    print(String(
        format: "largest edge change from the first frame: %.1f of 255; captures over 40: %d",
        captures.map(\.change).max()!, flashes.count
    ))
    for flash in flashes.prefix(5) {
        let since = (flash.time - (cuts.last { $0 <= flash.time } ?? 0)) * 1000
        print(String(format: "  flash at %.3f s, %.0f ms after a cut, change %.0f", flash.time, since, flash.change))
    }
    if !flashes.isEmpty { exit(1) }
    // A flash seen is proof on its own; only a clean verdict needs every cut sampled densely.
    guard afterCut.min()! >= 5 else {
        print("too few captures after a cut to judge")
        exit(3)
    }
    exit(0)
}

Timer.scheduledTimer(withTimeInterval: 1.0 / 240, repeats: true) { _ in
    MainActor.assumeIsolated {
        guard let start else { return }
        let now = CACurrentMediaTime() - start
        let options: CGWindowImageOption = [.boundsIgnoreFraming, .nominalResolution]
        if let image = CGWindowListCreateImage(.null, .optionIncludingWindow, CGWindowID(window.windowNumber), options) {
            let colours = edges(image)
            firstFrame = firstFrame ?? colours
            captures.append((now, zip(colours, firstFrame!).map { abs($0 - $1) }.max()!))
        }
        guard let scene = view.accessibilityLabel(), !scene.isEmpty else { return }
        guard cuts.count < wanted else { report(after: now) }
        // The children are the hotspots' buttons, then the scene's words. The search bar's button opens a sheet rather
        // than a clip, so it is skipped.
        let bar = tape.scenes[scene]?.search?.bar
        let buttons = (view.accessibilityChildren() as? [NSAccessibilityElement] ?? []).filter {
            $0.accessibilityRole() == .button && $0.accessibilityLabel() != bar
        }
        if buttons.isEmpty {
            view.startOver(nil)
        } else {
            let pressed = presses[scene, default: 0]
            presses[scene] = pressed + 1
            _ = buttons[pressed % buttons.count].accessibilityPerformPress()
        }
        cuts.append(now)
    }
}
app.run()
