import Foundation

/// Ընդհանուր կոնֆիգը ../app.json-ից (նույնը կարդում է Android-ը build-ի ժամանակ)
struct AppConfig: Decodable {
    let name: String
    let url: String
    let devUrl: String
    let hosts: [String]
    let devHosts: [String]
    let userAgentSuffix: String

    static let shared: AppConfig = {
        guard let u = Bundle.main.url(forResource: "app", withExtension: "json"),
              let d = try? Data(contentsOf: u),
              let c = try? JSONDecoder().decode(AppConfig.self, from: d) else {
            fatalError("app.json բացակայում է bundle-ից")
        }
        return c
    }()

    var startURL: URL {
        #if DEBUG
        return URL(string: devUrl.replacingOccurrences(of: "10.0.2.2", with: "localhost"))!
        #else
        return URL(string: url)!
        #endif
    }

    var allowedHosts: Set<String> {
        #if DEBUG
        return Set(hosts + devHosts)
        #else
        return Set(hosts)
        #endif
    }

    func isAllowed(_ url: URL?) -> Bool {
        guard let url, let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else { return false }
        return (scheme == "https" || scheme == "http") && allowedHosts.contains(host)
    }
}
