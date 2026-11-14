import CoreGraphics
import Testing
import TapeKit

struct PlayerTests {
    var player: Player

    init() throws {
        player = Player(tape: try Fixture.tape("surf_shop/tape"))
    }

    @Test mutating func opensOnWelcome() {
        #expect(player.playing == "moves/opening.mp4")
        player.clipEnded()
        #expect(player.resting == "welcome")
    }

    @Test mutating func welcomeToEntranceToLogin() {
        player.clipEnded()
        player.click("Enter shop")
        #expect(player.playing == "moves/welcome--enter-shop.mp4")
        player.clipEnded()
        #expect(player.resting == "entrance")
        player.click("I have an account")
        #expect(player.playing == "moves/entrance--i-have-an-account.mp4")
        player.clipEnded()
        #expect(player.resting == "login")
    }

    @Test mutating func entranceToSignupToLogin() {
        player.clipEnded()
        player.click("Enter shop")
        player.clipEnded()
        player.click("Create an account")
        #expect(player.playing == "moves/entrance--create-an-account.mp4")
        player.clipEnded()
        #expect(player.resting == "signup")
        player.click("Sign up")
        #expect(player.playing == "moves/signup--sign-up.mp4")
        player.clipEnded()
        #expect(player.resting == "login")
    }

    @Test mutating func entranceToGallery() {
        player.clipEnded()
        player.click("Enter shop")
        player.clipEnded()
        player.click("Browse as guest")
        #expect(player.playing == "moves/entrance--browse-as-guest.mp4")
        player.clipEnded()
        #expect(player.resting == "gallery")
    }

    @Test mutating func pressesByAccessibilityLabel() {
        player.clipEnded()
        let pressed = player.press(label: "Enter shop") == .move
        #expect(pressed)
        #expect(player.playing == "moves/welcome--enter-shop.mp4")
    }

    @Test mutating func clickReportsAMoveStarted() {
        player.clipEnded()
        let pressed = player.click("Enter shop") == .move
        #expect(pressed)
    }

    @Test mutating func ignoresPressesThatMissEveryHotspot() {
        player.clipEnded()
        let pressed = player.press(label: "Browse as guest") == .nothing
        #expect(pressed)
        let pressedPoint = player.press(CGPoint(x: 0.05, y: 0.05))
        #expect(pressedPoint == .nothing)
        #expect(player.resting == "welcome")
    }

    @Test mutating func galleryHasNothingToPress() {
        player.clipEnded()
        player.click("Enter shop")
        player.clipEnded()
        player.click("Browse as guest")
        player.clipEnded()
        let pressed = player.press(CGPoint(x: 0.5, y: 0.77))
        #expect(pressed == .nothing)
        #expect(player.resting == "gallery")
    }

    @Test mutating func ignoresPressesWhilePlaying() {
        let pressed = player.press(label: "Enter shop") == .nothing
        #expect(pressed)
        let pressedPoint = player.press(CGPoint(x: 0.5, y: 0.59))
        #expect(pressedPoint == .nothing)
        #expect(player.playing == "moves/opening.mp4")
    }

    @Test mutating func startsOverMidClip() {
        player.clipEnded()
        player.click("Enter shop")
        player.startOver()
        #expect(player.playing == "moves/opening.mp4")
        player.clipEnded()
        #expect(player.resting == "welcome")
    }

    @Test mutating func startsOverWhileResting() {
        player.clipEnded()
        player.click("Enter shop")
        player.clipEnded()
        player.startOver()
        #expect(player.playing == "moves/opening.mp4")
    }
}
