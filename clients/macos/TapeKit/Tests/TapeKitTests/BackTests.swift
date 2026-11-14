import Testing
import TapeKit

/// Back on the `search` fixture: home() opens, "Where to?" plays into search(), and typing plays further.
struct BackTests {
    var player: Player

    init() throws {
        player = Player(tape: try Fixture.tape("search"))
        player.clipEnded()
    }

    @Test mutating func backAtTheEntryDoesNothing() {
        #expect(!player.canGoBack)
        let clip = player.back()
        #expect(clip == nil)
        #expect(player.resting == "home()")
    }

    @Test mutating func backRewindsTheMoveThatArrivedAndRestsWhereItLeft() {
        player.click("Where to?")
        player.clipEnded()
        #expect(player.canGoBack)
        let clip = player.back()
        #expect(clip?.path == "moves/home--where-to.mp4")
        #expect(player.rewinding?.clip == "moves/home--where-to.mp4")
        #expect(player.rewinding?.to == "home()")
        #expect(!player.canGoBack)
        player.clipEnded()
        #expect(player.resting == "home()")
        let again = player.back()
        #expect(again == nil)
    }

    @Test mutating func repeatedBackWalksHistoryFurther() {
        player.click("Where to?")
        player.clipEnded()
        player.type("sea")
        player.clipEnded()
        player.click("Friday, December 11, $99")
        player.clipEnded()
        #expect(player.resting == "results(SEA, 2026-12-11)")

        let first = player.back()
        #expect(first?.path == "moves/dates-sea--11.mp4")
        player.clipEnded()
        #expect(player.resting == "dates(SEA)")
        let second = player.back()
        #expect(second?.path == "moves/search--seattle-sea.mp4")
        player.clipEnded()
        #expect(player.resting == "search()")
        let third = player.back()
        #expect(third?.path == "moves/home--where-to.mp4")
        player.clipEnded()
        #expect(player.resting == "home()")
        let clip = player.back()
        #expect(clip == nil)
    }

    @Test mutating func backWhileAClipPlaysDoesNothing() {
        player.click("Where to?")
        #expect(!player.canGoBack)
        let clip = player.back()
        #expect(clip == nil)
        #expect(player.playing == "moves/home--where-to.mp4")
    }

    @Test mutating func backThenForwardKeepsTheEarlierHistory() {
        player.click("Where to?")
        player.clipEnded()
        player.click("Boston (BOS)")
        player.clipEnded()
        player.back()
        player.clipEnded()
        #expect(player.resting == "search()")
        player.type("honolulu")
        player.clipEnded()
        #expect(player.resting == "dates(HNL)")
        player.back()
        player.clipEnded()
        #expect(player.resting == "search()")
        player.back()
        player.clipEnded()
        #expect(player.resting == "home()")
    }

    @Test mutating func startOverForgetsHistory() {
        player.click("Where to?")
        player.clipEnded()
        player.startOver()
        player.clipEnded()
        #expect(player.resting == "home()")
        let clip = player.back()
        #expect(clip == nil)
    }
}
