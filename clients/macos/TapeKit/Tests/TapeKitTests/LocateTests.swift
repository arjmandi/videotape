import Foundation
import Testing
import TapeKit

/// A throwaway checkout: `<root>/examples/surf_shop/tape/tape.json` and `<root>/clients/macos/build/TapePlayer.app`.
struct LocateTests: ~Copyable {
    let root: URL
    let tape: URL
    let app: URL

    init() throws {
        root = FileManager.default.temporaryDirectory.appending(path: "tapekit-locate-\(UUID().uuidString)").standardizedFileURL
        tape = root.appending(path: "examples/surf_shop/tape")
        app = root.appending(path: "clients/macos/build/TapePlayer.app")
        try FileManager.default.createDirectory(at: tape, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: app, withIntermediateDirectories: true)
        try Data("{}".utf8).write(to: tape.appending(path: "tape.json"))
    }

    deinit {
        try? FileManager.default.removeItem(at: root)
    }

    @Test func findsARelativePathAboveTheAppWhenLaunchedFromRoot() throws {
        let found = try Tape.locate("examples/surf_shop/tape", cwd: URL(filePath: "/"), app: app)
        #expect(found.standardizedFileURL == tape.standardizedFileURL)
    }

    @Test func prefersTheWorkingDirectory() throws {
        let cwd = root.appending(path: "elsewhere")
        let nearer = cwd.appending(path: "examples/surf_shop/tape")
        try FileManager.default.createDirectory(at: nearer, withIntermediateDirectories: true)
        try Data("{}".utf8).write(to: nearer.appending(path: "tape.json"))

        let found = try Tape.locate("examples/surf_shop/tape", cwd: cwd, app: app)
        #expect(found.standardizedFileURL == nearer.standardizedFileURL)
    }

    @Test func resolvesAgainstTheWorkingDirectory() throws {
        let found = try Tape.locate("surf_shop/tape", cwd: root.appending(path: "examples"), app: app)
        #expect(found.standardizedFileURL == tape.standardizedFileURL)
    }

    @Test func acceptsThePathOfTapeJSON() throws {
        let found = try Tape.locate("examples/surf_shop/tape/tape.json", cwd: URL(filePath: "/"), app: app)
        #expect(found.standardizedFileURL == tape.appending(path: "tape.json").standardizedFileURL)
    }

    @Test func keepsAnAbsolutePath() throws {
        #expect(try Tape.locate("/nowhere/tape", cwd: root, app: app) == URL(filePath: "/nowhere/tape"))
    }

    @Test func reportsWhereItLooked() {
        #expect(throws: TapeError.notFound("examples/beach/tape", cwd: URL(filePath: "/"), app: app)) {
            try Tape.locate("examples/beach/tape", cwd: URL(filePath: "/"), app: app)
        }
        let message = TapeError.notFound("examples/beach/tape", cwd: URL(filePath: "/"), app: app).description
        #expect(message == "No tape.json at examples/beach/tape in / or in any folder above \(app.path(percentEncoded: false)).")
    }
}
