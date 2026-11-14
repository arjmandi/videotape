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
        // The two key images themselves sit 10.45 apart on this grid.
        XCTAssertLessThan(home, 3, "the window shows the home key: \(summary)")
        XCTAssertGreaterThan(booked, home + 5, "the window is clearly not the booking's key: \(summary)")
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
