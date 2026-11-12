import Foundation
import TapeKit

// Loads a tape with TapePlayer's own loader and presses hotspots by label through its player, without a window.
// A label that ends in * matches the first hotspot whose label begins with the rest.

let arguments = CommandLine.arguments
guard arguments.count >= 2 else {
    print("usage: player-press <tape-dir> [<label>...]")
    exit(2)
}
let tape: Tape
do {
    tape = try Tape.load(URL(filePath: arguments[1]))
} catch {
    print("error: \(error)")
    exit(2)
}
var player = Player(tape: tape)

@MainActor
func rest() -> Scene {
    player.clipEnded()
    guard case .resting(let scene) = player.playback else { fatalError("the player is not resting after a clip ended") }
    return scene
}

var scene = rest()
print("\(tape.scenes.count) scenes at \(Int(tape.size.width))x\(Int(tape.size.height)), and the opening rests on \(scene.name)")
for wanted in arguments.dropFirst(2) {
    let hotspot = scene.hotspots.first {
        wanted.hasSuffix("*") ? $0.label.hasPrefix(String(wanted.dropLast())) : $0.label == wanted
    }
    guard let hotspot, player.press(label: hotspot.label) else {
        print("FAIL \(scene.name) offers no \"\(wanted)\"; it offers \(scene.hotspots.map(\.label))")
        exit(1)
    }
    scene = rest()
    print("press \"\(hotspot.label)\" -> \(scene.name)")
}
print("rests on \(scene.name), which offers \(scene.hotspots.map(\.label))")
