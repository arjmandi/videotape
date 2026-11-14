import CoreGraphics
import Testing
import TapeKit

/// Typing into the `search` fixture's bar, which rests on search() after home's "Where to?".
struct TypingTests {
    var player: Player

    init() throws {
        player = Player(tape: try Fixture.tape("search"))
        player.clipEnded()
        player.click("Where to?")
        player.clipEnded()
    }

    @Test mutating func typingPlaysTheOptionTheTextNames() {
        let typed = player.type("sea")
        #expect(typed)
        #expect(player.playing == "moves/search--seattle-sea.mp4")
        player.clipEnded()
        #expect(player.resting == "dates(SEA)")
    }

    @Test mutating func typingAnOptionWithoutABoxStillPlaysItsMove() {
        player.type("new orleans")
        #expect(player.playing == "moves/search--new-orleans-msy.mp4")
        player.clipEnded()
        #expect(player.resting == "no_flights(MSY)")
    }

    @Test(arguments: ["san", "new", ""])
    mutating func typingWhatNoOneOptionMatchesPlaysNoMatch(text: String) {
        let typed = player.type(text)
        #expect(typed)
        #expect(player.playing == "moves/search--where-to.mp4")
        player.clipEnded()
        #expect(player.resting == "not_found()")
    }

    @Test mutating func typingWhileAClipPlaysDoesNothing() {
        player.click("Seattle (SEA)")
        let typed = player.type("sea")
        #expect(!typed)
        #expect(player.playing == "moves/search--seattle-sea.mp4")
    }

    @Test func typingWithoutASearchBarDoesNothing() throws {
        var player = Player(tape: try Fixture.tape("search"))
        player.clipEnded()
        let typed = player.type("sea")
        #expect(!typed)
        #expect(player.resting == "home()")
    }

    @Test mutating func pressingTheBarAsksForTextInsteadOfMoving() {
        let byLabel = player.press(label: "Where to?")
        #expect(byLabel == .bar)
        let byPoint = player.click("Where to?")
        #expect(byPoint == .bar)
        #expect(player.resting == "search()")
    }

    @Test mutating func pressingAnOptionPlaysItsMove() {
        let pressed = player.click("Seattle (SEA)")
        #expect(pressed == .move)
        #expect(player.playing == "moves/search--seattle-sea.mp4")
    }

    /// Home's bar has no options, so it is an ordinary hotspot that plays into search().
    @Test func pressingABarWithoutOptionsMoves() throws {
        var player = Player(tape: try Fixture.tape("search"))
        player.clipEnded()
        let pressed = player.press(label: "Where to?") == .move
        #expect(pressed)
        #expect(player.playing == "moves/home--where-to.mp4")
    }
}
