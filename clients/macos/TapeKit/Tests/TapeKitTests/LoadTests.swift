import Foundation
import Testing
import TapeKit

struct LoadTests {
    @Test func readsTheSurfShop() throws {
        let tape = try Fixture.tape("surf_shop/tape")
        let directory = Fixture.url("surf_shop/tape").standardizedFileURL

        #expect(tape.name == "surf_shop")
        #expect(tape.size == CGSize(width: 1280, height: 704))
        #expect(tape.opening.url == directory.appending(path: "moves/opening.mp4"))
        #expect(tape.opening.lands == "welcome")
        #expect(tape.scenes.keys.sorted() == ["entrance", "gallery", "login", "signup", "welcome"])
        #expect(tape.scenes["entrance"]!.hotspots.map(\.label) == ["I have an account", "Create an account", "Browse as guest"])
        #expect(tape.scenes["login"]!.hotspots.isEmpty)
        #expect(tape.scenes["gallery"]!.hotspots.isEmpty)

        let enter = try #require(tape.scenes["welcome"]!.hotspots.first)
        #expect(enter.label == "Enter shop")
        #expect([enter.box.x, enter.box.y, enter.box.w, enter.box.h] == [0.3984, 0.5568, 0.2031, 0.0739])
        #expect(enter.clip.url == directory.appending(path: "moves/welcome--enter-shop.mp4"))
        #expect(enter.clip.lands == "entrance")
    }

    @Test func readsATapeFromItsManifest() throws {
        #expect(try Fixture.tape("surf_shop/tape/tape.json") == Fixture.tape("surf_shop/tape"))
    }

    static let errors: [(String, String)] = [
        ("no-manifest", "No tape.json at \(path("errors/no-manifest/tape.json"))."),
        ("not-json", "\(path("errors/not-json/tape.json")) is not a tape: not valid JSON."),
        ("missing-key", "\(path("errors/missing-key/tape.json")) is not a tape: missing \"scenes.home.hotspots.0.move\"."),
        ("unknown-move", "Hotspot \"Go\" in scene \"home\" plays move \"home--go\", which tape.json does not define."),
        ("unknown-scene", "moves/home--go.mp4 lands on scene \"away\", which tape.json does not define."),
        ("missing-clip", "Clip moves/home--go.mp4 is missing from \(path("errors/missing-clip"))."),
    ]

    @Test(arguments: errors)
    func rejects(fixture: String, message: String) {
        #expect {
            try Fixture.tape("errors/\(fixture)")
        } throws: { error in
            (error as? TapeError)?.description == message
        }
    }

    private static func path(_ fixture: String) -> String {
        Fixture.url(fixture).path(percentEncoded: false)
    }
}
