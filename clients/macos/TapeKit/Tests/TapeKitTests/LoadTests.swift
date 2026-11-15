import Foundation
import Testing
import TapeKit

struct LoadTests {
    @Test func readsTheSurfShop() throws {
        let tape = try Fixture.tape("surf_shop/tape")
        let directory = Fixture.url("surf_shop/tape").standardizedFileURL

        #expect(tape.size == CGSize(width: 1280, height: 704))
        #expect(tape.fps == 24)
        #expect(tape.opening.url == directory.appending(path: "moves/opening.mp4"))
        #expect(tape.opening.lands == "welcome")
        #expect(tape.scenes.keys.sorted() == ["entrance", "gallery", "login", "signup", "welcome"])
        #expect(tape.scenes["entrance"]!.hotspots.map(\.label) == ["I have an account", "Create an account", "Browse as guest"])
        #expect(tape.scenes["entrance"]!.words == ["Welcome", "I have an account", "Create an account", "Browse as guest"])
        #expect(tape.scenes["login"]!.hotspots.isEmpty)
        #expect(tape.scenes["gallery"]!.hotspots.isEmpty)
        #expect(tape.scenes.values.allSatisfy { $0.search == nil })
        #expect(tape.made.label == "surf_shop 0.1.0 + beach 1.0.0")
        #expect(tape.made.id == "4c1d0e8f6a2b9c7d5e3f1a0b8c6d4e2f0a9b7c5d3e1f8a6b4c2d0e9f7a5b3c1d")

        let enter = try #require(tape.scenes["welcome"]!.hotspots.first)
        #expect(enter.label == "Enter shop")
        #expect([enter.box.x, enter.box.y, enter.box.w, enter.box.h] == [0.3984, 0.5568, 0.2031, 0.0739])
        #expect(enter.clip.url == directory.appending(path: "moves/welcome--enter-shop.mp4"))
        #expect(enter.clip.lands == "entrance")
    }

    @Test func readsATapeFromItsManifest() throws {
        #expect(try Fixture.tape("surf_shop/tape/tape.json") == Fixture.tape("surf_shop/tape"))
    }

    /// The `search` fixture has Contrail's search state: a bar with options, one of which the checks found no box for.
    @Test func readsASearchBarWithItsOptions() throws {
        let tape = try Fixture.tape("search")
        let directory = Fixture.url("search").standardizedFileURL
        #expect(tape.made.label == "contrail 0.1.0 + terminal 1.0.0")
        #expect(tape.scenes["home()"]!.search == nil)

        let search = try #require(tape.scenes["search()"]!.search)
        #expect(search.bar == "Where to?")
        #expect(search.options.map(\.label) == ["Boston (BOS)", "Honolulu (HNL)", "New Orleans (MSY)", "New York (JFK)", "Seattle (SEA)"])
        #expect(search.options.map(\.clip.lands) == ["no_flights(BOS)", "dates(HNL)", "no_flights(MSY)", "dates(JFK)", "dates(SEA)"])
        #expect(search.options[2].clip.url == directory.appending(path: "moves/search--new-orleans-msy.mp4"))
        #expect(tape.scenes["search()"]!.hotspots.map(\.label) == ["Where to?", "Boston (BOS)", "Honolulu (HNL)", "New York (JFK)", "Seattle (SEA)"])
        #expect(search.noMatch.lands == "not_found()")
        #expect(search.noMatch.url == directory.appending(path: "moves/search--where-to.mp4"))
    }

    static let errors: [(String, String)] = [
        ("no-manifest", "No tape.json at \(path("errors/no-manifest/tape.json"))."),
        ("not-json", "\(path("errors/not-json/tape.json")) is not a tape: not valid JSON."),
        ("missing-key", "\(path("errors/missing-key/tape.json")) is not a tape: missing \"scenes.home.hotspots.0.move\"."),
        ("missing-words", "\(path("errors/missing-words/tape.json")) is not a tape: missing \"scenes.home.words\"."),
        ("missing-made", "\(path("errors/missing-made/tape.json")) is not a tape: missing \"made\"."),
        ("unknown-move", "\"Go\" in scene \"home\" plays move \"home--go\", which tape.json does not define."),
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
