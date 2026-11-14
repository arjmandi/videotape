import Testing
import TapeKit

/// The option matcher on the `search` fixture's bar, whose options are Boston (BOS), Honolulu (HNL), New Orleans (MSY),
/// New York (JFK) and Seattle (SEA).
struct MatchTests {
    let search: Search

    init() throws {
        search = try #require(Fixture.tape("search").scenes["search()"]!.search)
    }

    @Test(arguments: [
        ("sea", "Seattle (SEA)"),
        ("SEA", "Seattle (SEA)"),
        ("Seattle", "Seattle (SEA)"),
        ("seattle (sea)", "Seattle (SEA)"),
        ("honolulu", "Honolulu (HNL)"),
        ("(hnl)", "Honolulu (HNL)"),
        ("york", "New York (JFK)"),
        ("new o", "New Orleans (MSY)"),
    ])
    func picksTheOneOptionTheTextNames(text: String, label: String) {
        #expect(search.option(matching: text)?.label == label)
    }

    @Test(arguments: ["san", "new", "eattle", "", " ", "seattle (sea) today"])
    func picksNothingWhenNoOptionOrMoreThanOneMatches(text: String) {
        #expect(search.option(matching: text) == nil)
    }
}
