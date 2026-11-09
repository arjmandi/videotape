import CoreGraphics
import Testing
import TapeKit

struct HitTests {
    let menu: Scene

    init() throws {
        menu = try Fixture.tape("hits").scenes["menu"]!
    }

    @Test(arguments: [
        (CGPoint(x: 0.25, y: 0.25), "Back"),
        (CGPoint(x: 0.4, y: 0.7), "Back"),
        (CGPoint(x: 0.6, y: 0.6), "Back"),
        (CGPoint(x: 0.75, y: 0.75), "Front"),
        (CGPoint(x: 0.99, y: 0.6), "Front"),
    ])
    func hits(point: CGPoint, label: String) {
        #expect(menu.hotspot(at: point)?.label == label)
    }

    @Test(arguments: [
        CGPoint(x: 0.1, y: 0.1),
        CGPoint(x: 0.2499, y: 0.5),
        CGPoint(x: 0.4, y: 0.75),
        CGPoint(x: 1.0, y: 0.6),
        CGPoint(x: 0.6, y: 1.0),
    ])
    func misses(point: CGPoint) {
        #expect(menu.hotspot(at: point) == nil)
    }
}
