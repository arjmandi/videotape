import CoreGraphics
import ImageIO
import XCTest

/// Clicks through the surf shop tape the way a person does, then checks what the window shows.
final class TapePlayerUITests: XCTestCase {
    /// `examples/surf_shop/tape` in the checkout this file lives in.
    private static let tape = URL(filePath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appending(path: "examples/surf_shop/tape")

    @MainActor
    func testBrowsingAsGuestRestsOnTheGallery() throws {
        let (app, tape) = try launch()
        let screen = app.images["tape"]
        let enter = app.buttons["Enter shop"]
        XCTAssertTrue(enter.waitForExistence(timeout: 30), "the opening rests on welcome, which offers Enter shop")
        enter.click()
        let guest = app.buttons["Browse as guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 30), "Enter shop plays into the entrance, which offers Browse as guest")
        guest.click()
        XCTAssertTrue(screen.wait(for: \.label, toEqual: "gallery", timeout: 30), "Browse as guest plays into the gallery")
        XCTAssertTrue(screen.buttons.firstMatch.waitForNonExistence(timeout: 5), "the gallery offers nothing to press")

        let shot = screen.screenshot()
        let seen = try grid(shot.pngRepresentation)
        let gallery = difference(seen, try grid(Data(contentsOf: tape.appending(path: "keys/gallery.png"))))
        let entrance = difference(seen, try grid(Data(contentsOf: tape.appending(path: "keys/entrance.png"))))
        let summary = String(format: "tape vs keys/gallery.png %.2f, vs keys/entrance.png %.2f", gallery, entrance)
        print(summary)
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = summary
        attachment.lifetime = .keepAlways
        add(attachment)
        XCTAssertLessThan(gallery, 2, "the window shows the gallery key: \(summary)")
        XCTAssertGreaterThan(entrance, gallery + 8, "the window is clearly not the entrance key: \(summary)")
    }

    @MainActor
    func testLoginAndSignupBothRestOnLogin() throws {
        let (app, _) = try launch()
        let screen = app.images["tape"]
        walk(app, ["Enter shop", "I have an account"], to: "login")
        XCTAssertTrue(screen.buttons.firstMatch.waitForNonExistence(timeout: 5), "login offers nothing to press")
        app.typeKey("r", modifierFlags: .command)
        walk(app, ["Enter shop", "Create an account"], to: "signup")
        walk(app, ["Sign up"], to: "login")
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

    /// Launches TapePlayer on the surf shop tape, or fails with the command that renders it.
    @MainActor
    private func launch() throws -> (XCUIApplication, URL) {
        let exists = FileManager.default.fileExists(atPath: Self.tape.appending(path: "tape.json").path(percentEncoded: false))
        let tape = try XCTUnwrap(
            exists ? Self.tape : nil,
            "No tape.json in \(Self.tape.path(percentEncoded: false)). From the repo root, run: videotape render examples/surf_shop --model stand-in"
        )
        let app = XCUIApplication()
        app.launchArguments = [tape.path(percentEncoded: false)]
        app.launch()
        return (app, tape)
    }

    /// Clicks each button as soon as its scene offers it, then waits for the tape to rest on `scene`.
    @MainActor
    private func walk(_ app: XCUIApplication, _ labels: [String], to scene: String) {
        for label in labels {
            let button = app.buttons[label]
            XCTAssertTrue(button.waitForExistence(timeout: 30), "a resting scene offers \(label)")
            button.click()
        }
        XCTAssertTrue(app.images["tape"].wait(for: \.label, toEqual: scene, timeout: 30), "\(labels.last!) plays into \(scene)")
    }
}

private let columns = 20, rows = 11, cell = 8

/// The image as the mean sRGB colour of each cell in a `columns` by `rows` grid, less the image's mean colour. Scaling,
/// video encoding and the colour shift from the display's profile and the clips' untagged colour matrix wash out,
/// while a different screen does not.
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
