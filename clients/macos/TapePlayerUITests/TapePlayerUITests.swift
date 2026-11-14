import CoreGraphics
import ImageIO
import XCTest

/// Clicks through the Contrail tape the way a person does, then checks what the window shows.
final class TapePlayerUITests: XCTestCase {
    /// `examples/contrail/tapes/terminal` in the checkout this file lives in.
    private static let tape = URL(filePath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appending(path: "examples/contrail/tapes/terminal")

    @MainActor
    func testBookingTheMorningFlightToSeattleLandsBackOnHome() throws {
        let (app, tape) = try launch()
        let image = app.images["tape"]
        XCTAssertTrue(image.wait(for: \.label, toEqual: "home()", timeout: 30), "the opening rests on home()")
        press(app.buttons["Where to?"], "home offers its search bar")
        press(app.buttons["Seattle (SEA)"], "the search bar plays into search, which offers Seattle (SEA)")
        press(app.buttons["Saturday, December 12, $89"], "Seattle plays into its dates, which offer December 12")
        XCTAssertTrue(
            image.wait(for: \.label, toEqual: "results(SEA, 2026-12-12)", timeout: 30),
            "December 12 plays into that day's flights"
        )
        let morning = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "8:15 AM")).firstMatch
        press(morning, "the day's flights offer the 8:15 AM flight")
        press(app.buttons["Book for $89"], "the 8:15 AM flight plays into the flight, which offers Book for $89")
        XCTAssertTrue(
            image.wait(for: \.label, toEqual: "booked(CT 300, 2026-12-12)", timeout: 30),
            "Book for $89 plays into the booking"
        )
        press(app.buttons["Done"], "the booking offers Done")
        XCTAssertTrue(image.wait(for: \.label, toEqual: "home()", timeout: 30), "Done plays back into home")
        XCTAssertTrue(app.buttons["Where to?"].waitForExistence(timeout: 5), "home offers its search bar again")

        let shot = image.screenshot()
        let seen = try grid(shot.pngRepresentation)
        let home = difference(seen, try grid(Data(contentsOf: tape.appending(path: "keys/home.png"))))
        let booked = difference(
            seen, try grid(Data(contentsOf: tape.appending(path: "keys/booked-ct-300-2026-12-12.png")))
        )
        let summary = String(format: "tape vs keys/home.png %.2f, vs keys/booked-ct-300-2026-12-12.png %.2f", home, booked)
        print(summary)
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = summary
        attachment.lifetime = .keepAlways
        add(attachment)
        // The two key images themselves sit about 10.5 apart on this grid.
        XCTAssertLessThan(home, 3, "the window shows the home key: \(summary)")
        XCTAssertGreaterThan(booked, home + 5, "the window is clearly not the booking's key: \(summary)")
    }

    /// Walks the terminal tape along a route planned from its tape.json: every hotspot of every state at least once,
    /// "sea", "honolulu" and "san" typed into the search bar, Escape on the sheet, and Back from at least five states.
    /// Each landing checks the state's name and that its static texts are its words.
    @MainActor
    func testWalksEveryJourneyOfTheTerminalTape() throws {
        let (app, url) = try launch()
        let tape = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: url.appending(path: "tape.json")))
        let walk = try Walk.plan(tape)
        let image = app.images["tape"]
        XCTAssertTrue(image.wait(for: \.label, toEqual: tape.opening.lands, timeout: 30), "the opening rests on the entry")
        XCTAssertEqual(app.windows.firstMatch.title, tape.made.label, "the window is titled with the tape's label")
        let started = Date()
        for (number, step) in walk.enumerated() {
            let what = "step \(number + 1) of \(walk.count), \(step.action) from \(step.from)"
            switch step.action {
            case .press(let label):
                press(app.buttons[label], "\(what): \(step.from) offers \(label)")
            case .search(let text, let bar):
                if let bar {
                    press(app.buttons[bar], "\(what): \(step.from) offers its search bar")
                } else {
                    app.typeText(String(text.prefix(1)))
                }
                let field = app.sheets.firstMatch.textFields.firstMatch
                XCTAssertTrue(field.waitForExistence(timeout: 5), "\(what): the text sheet opens")
                app.typeText(bar == nil ? String(text.dropFirst()) : text)
                XCTAssertEqual(field.value as? String, text, "\(what): the field holds the typed text")
                app.typeKey(.return, modifierFlags: [])
            case .cancel(let text):
                app.typeText(String(text.prefix(1)))
                let sheet = app.sheets.firstMatch
                XCTAssertTrue(sheet.textFields.firstMatch.waitForExistence(timeout: 5), "\(what): the text sheet opens")
                app.typeText(String(text.dropFirst()))
                app.typeKey(.escape, modifierFlags: [])
                XCTAssertTrue(sheet.waitForNonExistence(timeout: 5), "\(what): Escape closes the sheet")
            case .back:
                app.typeKey("[", modifierFlags: .command)
            case .backAtEntry:
                app.typeKey("[", modifierFlags: .command)
                for _ in 0..<6 {
                    XCTAssertEqual(image.label, step.lands, "\(what): Back at the entry plays nothing")
                    usleep(200_000)
                }
            }
            XCTAssertTrue(image.wait(for: \.label, toEqual: step.lands, timeout: 30), "\(what): rests on \(step.lands)")
            let read = image.staticTexts.allElementsBoundByIndex.map { $0.value as? String ?? "" }
            XCTAssertEqual(read, tape.scenes[step.lands]!.words, "\(what): \(step.lands) reads its words")
            guard testRun?.totalFailureCount == 0 else { break }
        }
        print(String(format: "walked %d steps in %.0f s", walk.count, Date().timeIntervalSince(started)))
    }

    @MainActor
    func testABadTapeLeavesOpenAvailable() {
        let app = XCUIApplication()
        app.launchArguments = ["/no/such/tape"]
        app.launch()
        let ok = app.buttons["OK"].firstMatch
        XCTAssertTrue(ok.waitForExistence(timeout: 10), "a bad tape shows an alert")
        ok.click()
        XCTAssertFalse(app.wait(for: .notRunning, timeout: 3), "dismissing the alert keeps TapePlayer running")
        XCTAssertTrue(app.menuBars.menuItems["Open…"].isEnabled, "File > Open is still there to pick another tape")
    }

    @MainActor
    func testCancellingTheOpenPanelKeepsTheApp() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.buttons["Cancel"].firstMatch.waitForExistence(timeout: 10), "launching without a tape shows the Open panel")
        app.typeKey(.escape, modifierFlags: [])
        XCTAssertFalse(app.wait(for: .notRunning, timeout: 3), "cancelling the panel keeps TapePlayer running")
        XCTAssertTrue(app.menuBars.menuItems["Open…"].isEnabled, "File > Open is still there to pick a tape")
    }

    /// Launches TapePlayer on the Contrail tape, or fails with the command that renders it.
    @MainActor
    private func launch() throws -> (XCUIApplication, URL) {
        let exists = FileManager.default.fileExists(atPath: Self.tape.appending(path: "tape.json").path(percentEncoded: false))
        let tape = try XCTUnwrap(
            exists ? Self.tape : nil,
            "No tape.json in \(Self.tape.path(percentEncoded: false)). In examples/contrail, run: uv run videotape render --story terminal"
        )
        let app = XCUIApplication()
        app.launchArguments = [tape.path(percentEncoded: false)]
        app.launch()
        return (app, tape)
    }

    /// Clicks a hotspot as soon as its state rests and offers it.
    @MainActor
    private func press(_ button: XCUIElement, _ offered: String) {
        XCTAssertTrue(button.waitForExistence(timeout: 30), offered)
        button.click()
    }
}

private let columns = 20, rows = 11, cell = 8

/// The image as the mean sRGB colour of each cell in a `columns` by `rows` grid, less the image's mean colour. Scaling,
/// video encoding and the colour shift from the display's profile and the clips' untagged colour matrix wash out,
/// while a different key does not.
private func grid(_ png: Data) throws -> [Double] {
    guard let source = CGImageSourceCreateWithData(png as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw CocoaError(.fileReadCorruptFile)
    }
    let width = columns * cell, height = rows * cell
    var pixels = [UInt8](repeating: 0, count: width * height * 4)
    let drawn: Bool = pixels.withUnsafeMutableBytes { buffer in
        guard let context = CGContext(
            data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else { return false }
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return true
    }
    guard drawn else { throw CocoaError(.featureUnsupported) }
    var cells = [Double](repeating: 0, count: columns * rows * 3)
    for y in 0..<height {
        for x in 0..<width {
            for channel in 0..<3 {
                cells[((y / cell) * columns + x / cell) * 3 + channel] += Double(pixels[(y * width + x) * 4 + channel])
            }
        }
    }
    let means = (0..<3).map { channel in
        stride(from: channel, to: cells.count, by: 3).map { cells[$0] }.reduce(0, +) / Double(columns * rows)
    }
    return cells.enumerated().map { ($1 - means[$0 % 3]) / Double(cell * cell) }
}

/// Mean absolute difference per channel, from 0 for the same picture to 255.
private func difference(_ a: [Double], _ b: [Double]) -> Double {
    zip(a, b).map { abs($0 - $1) }.reduce(0, +) / Double(a.count)
}

/// The tape as the test reads it, straight from tape.json.
private struct Manifest: Decodable {
    struct Clip: Decodable { let lands: String }
    struct Hotspot: Decodable { let label, move: String }
    struct Option: Decodable { let label, move: String }
    struct NoMatch: Decodable { let lands: String }
    struct Search: Decodable {
        let bar: String
        let options: [Option]
        let noMatch: NoMatch
        enum CodingKeys: String, CodingKey { case bar, options, noMatch = "no_match" }
    }
    struct Scene: Decodable { let words: [String]; let hotspots: [Hotspot]; let search: Search? }
    struct Made: Decodable { let label: String }

    let opening: Clip
    let scenes: [String: Scene]
    let moves: [String: Clip]
    let made: Made
}

/// What the test types into the search bar, and the option each picks, or nil for no match.
private let typed: [(text: String, option: String?)] = [("sea", "Seattle (SEA)"), ("honolulu", "Honolulu (HNL)"), ("san", nil)]

private enum Walk {
    enum Action: CustomStringConvertible {
        case press(String)
        /// Types the text, after clicking the bar's hotspot when it names one.
        case search(String, bar: String?)
        /// Types the text and presses Escape.
        case cancel(String)
        case back
        case backAtEntry

        var description: String {
            switch self {
            case .press(let label): "press \"\(label)\""
            case .search(let text, let bar): bar == nil ? "type \"\(text)\"" : "click the bar and type \"\(text)\""
            case .cancel(let text): "type \"\(text)\" and press Escape"
            case .back: "Back"
            case .backAtEntry: "Back at the entry"
            }
        }
    }

    struct Step {
        let action: Action
        let from: String
        let lands: String
    }

    struct Unwalkable: Error, CustomStringConvertible {
        let description: String
    }

    /// Plans the walk from the tape's graph. From the state it is at, it presses the first hotspot not yet pressed, goes
    /// back from a state with none, or follows the shortest route to a state with one, typing into a search bar where
    /// that is the way. The first time it rests on a state with a search bar it types each text and goes back, then
    /// opens the sheet once more and cancels it.
    static func plan(_ tape: Manifest) throws -> [Step] {
        for (state, scene) in tape.scenes {
            for hotspot in scene.hotspots where try lands(hotspot.move, tape) == state {
                throw Unwalkable(description: "\(state)'s \(hotspot.label) lands on itself, which the walk cannot tell from staying")
            }
        }

        var unused = Dictionary(uniqueKeysWithValues: tape.scenes.keys.map { ($0, pressable($0, tape).map(\.label)) })
        var steps: [Step] = []
        var at = tape.opening.lands
        var history: [String] = []
        var wentBackFrom: Set<String> = []
        var typedInto: String?

        func go(_ action: Action, to next: String) {
            if case .press(let label) = action { unused[at]!.removeAll { $0 == label } }
            steps.append(Step(action: action, from: at, lands: next))
            history.append(at)
            at = next
        }
        func back() {
            wentBackFrom.insert(at)
            let to = history.removeLast()
            steps.append(Step(action: .back, from: at, lands: to))
            at = to
        }

        steps.append(Step(action: .backAtEntry, from: at, lands: at))
        while true {
            if let search = tape.scenes[at]!.search, typedInto == nil {
                typedInto = at
                let clickable = tape.scenes[at]!.hotspots.contains { $0.label == search.bar }
                for (index, entry) in typed.enumerated() {
                    var next = search.noMatch.lands
                    if let option = entry.option {
                        guard let found = search.options.first(where: { $0.label == option }) else {
                            throw Unwalkable(description: "\(at)'s search bar offers no \(option)")
                        }
                        next = try lands(found.move, tape)
                    }
                    go(.search(entry.text, bar: index == 0 && clickable ? search.bar : nil), to: next)
                    back()
                }
                steps.append(Step(action: .cancel("x"), from: at, lands: at))
            }
            if let label = unused[at]!.first {
                go(.press(label), to: try lands(tape.scenes[at]!.hotspots.first { $0.label == label }!.move, tape))
            } else if unused.values.allSatisfy(\.isEmpty) {
                break
            } else if try edges(of: at, tape).isEmpty {
                back()
            } else {
                for edge in try route(from: at, tape, toward: { !unused[$0]!.isEmpty }) {
                    go(edge.action, to: edge.lands)
                }
            }
        }
        while wentBackFrom.count < 5, !history.isEmpty {
            back()
        }
        guard wentBackFrom.count >= 5 else {
            throw Unwalkable(description: "the walk went back from \(wentBackFrom.count) states, fewer than five")
        }
        guard typedInto != nil else { throw Unwalkable(description: "no state the walk reached has a search bar") }
        return steps
    }

    private static func lands(_ move: String, _ tape: Manifest) throws -> String {
        guard let move = tape.moves[move] else { throw Unwalkable(description: "tape.json defines no move \(move)") }
        return move.lands
    }

    /// The hotspots that play a move when clicked, which leaves out a search bar's own.
    private static func pressable(_ state: String, _ tape: Manifest) -> [Manifest.Hotspot] {
        let scene = tape.scenes[state]!
        return scene.hotspots.filter { $0.label != scene.search?.bar }
    }

    /// Every way out of a state: its pressable hotspots, then typing each option's label into its search bar, then
    /// typing the text that matches no option.
    private static func edges(of state: String, _ tape: Manifest) throws -> [(action: Action, lands: String)] {
        var edges: [(action: Action, lands: String)] = []
        for hotspot in pressable(state, tape) {
            edges.append((.press(hotspot.label), try lands(hotspot.move, tape)))
        }
        if let search = tape.scenes[state]!.search {
            for option in search.options {
                edges.append((.search(option.label, bar: nil), try lands(option.move, tape)))
            }
            if let miss = typed.first(where: { $0.option == nil }) {
                edges.append((.search(miss.text, bar: nil), search.noMatch.lands))
            }
        }
        return edges
    }

    /// The shortest route from `state` to one that satisfies `toward`.
    private static func route(
        from state: String, _ tape: Manifest, toward: (String) -> Bool
    ) throws -> [(action: Action, lands: String)] {
        var cameFrom: [String: (state: String, action: Action)] = [:]
        var queue = [state]
        var seen: Set<String> = [state]
        while !queue.isEmpty {
            let here = queue.removeFirst()
            for edge in try edges(of: here, tape) {
                guard seen.insert(edge.lands).inserted else { continue }
                cameFrom[edge.lands] = (here, edge.action)
                if toward(edge.lands) {
                    var route: [(action: Action, lands: String)] = []
                    var back = edge.lands
                    while let step = cameFrom[back] {
                        route.insert((step.action, back), at: 0)
                        back = step.state
                    }
                    return route
                }
                queue.append(edge.lands)
            }
        }
        throw Unwalkable(description: "no route from \(state) reaches a hotspot not yet pressed")
    }
}
