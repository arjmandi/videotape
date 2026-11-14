import Foundation
import TapeKit

// Loads a tape with TapePlayer's own loader and drives its player without a window: presses hotspots by label, types
// into the search bar with `--type <text>`, and goes back with `--back`. A label that ends in * matches the first
// hotspot whose label begins with the rest.

let arguments = CommandLine.arguments
guard arguments.count >= 2 else {
    print("usage: player-press <tape-dir> [<label> | --type <text> | --back ...]")
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
    guard let scene = player.scene else { fatalError("the player is not resting after a clip ended") }
    return scene
}

@MainActor
func fail(_ message: String) -> Never {
    print("FAIL \(message)")
    exit(1)
}

var scene = rest()
print("\(tape.made.label): \(tape.scenes.count) scenes at \(Int(tape.size.width))x\(Int(tape.size.height)), and the opening rests on \(scene.name)")
var todo = arguments.dropFirst(2)[...]
while let wanted = todo.popFirst() {
    switch wanted {
    case "--type":
        guard let text = todo.popFirst() else { fail("--type needs the text to type") }
        guard player.type(text) else { fail("\(scene.name) has no search bar to type into") }
        scene = rest()
        print("type \"\(text)\" -> \(scene.name)")
    case "--back":
        guard player.back() != nil else { fail("\(scene.name) has nothing to go back to") }
        scene = rest()
        print("back -> \(scene.name)")
    default:
        let hotspot = scene.hotspots.first {
            wanted.hasSuffix("*") ? $0.label.hasPrefix(String(wanted.dropLast())) : $0.label == wanted
        }
        guard let hotspot else { fail("\(scene.name) offers no \"\(wanted)\"; it offers \(scene.hotspots.map(\.label))") }
        switch player.press(label: hotspot.label) {
        case .move: break
        case .bar: fail("\(scene.name) asks for text at \"\(hotspot.label)\"; type into it with --type <text>")
        case .nothing: fail("\(scene.name) does not take a press while a clip plays")
        }
        scene = rest()
        print("press \"\(hotspot.label)\" -> \(scene.name)")
    }
}
print("rests on \(scene.name), which offers \(scene.hotspots.map(\.label)) and reads \(scene.words)")
