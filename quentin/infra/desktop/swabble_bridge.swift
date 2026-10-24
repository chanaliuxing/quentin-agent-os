import Cocoa
import ApplicationServices

// Minimal Swabble implementation for Quentin
// Compile with: swiftc swabble_bridge.swift -o swabble

func getAXTree() -> [String: Any] {
    let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
    let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as! [[String: Any]]
    
    var tree: [String: Any] = ["windows": []]
    var windows: [[String: Any]] = []
    
    for window in windowList {
        let name = window[kCGWindowName as String] as? String ?? "Unknown"
        let owner = window[kCGWindowOwnerName as String] as? String ?? "Unknown"
        let bounds = window[kCGWindowBounds as String] as? [String: Int] ?? [:]
        
        windows.append([
            "name": name,
            "app": owner,
            "bounds": bounds
        ])
    }
    tree["windows"] = windows
    return tree
}

let tree = getAXTree()
let jsonData = try! JSONSerialization.data(withJSONObject: tree, options: .prettyPrinted)
if let jsonString = String(data: jsonData, encoding: .utf8) {
    print(jsonString)
}
