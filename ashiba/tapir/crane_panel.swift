// クレーン操作の浮いた小窓（利用者の指定 2026-11-06: SCP の手引 p.5「車両・フックの移動」）。
// 押すと scripts/crane_move.py を呼ぶ。.nonactivatingPanel なので Archicad の選択は外れない。
// 移動量は 1m・15°、Shift で 10m・45°、Control で 0.1m・1°。
import AppKit

final class CranePanel: NSObject, NSWindowDelegate {
    let root: String, py: String, port: String
    var panel: NSPanel!
    var status: NSTextField!
    var buttons: [NSButton] = []
    var actions: [[String]] = []
    var busy = false

    init(root: String, py: String, port: String) {
        self.root = root; self.py = py; self.port = port
        super.init()
    }

    func label(_ text: String, _ frame: NSRect, bold: Bool = false, size: CGFloat = 12) -> NSTextField {
        let l = NSTextField(labelWithString: text)
        l.frame = frame
        l.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        return l
    }

    func button(_ title: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ args: [String], _ view: NSView) {
        let b = NSButton(frame: NSRect(x: x, y: y, width: w, height: 28))
        b.bezelStyle = .rounded
        b.title = title
        b.tag = actions.count
        b.target = self
        b.action = #selector(clicked(_:))
        actions.append(args)
        buttons.append(b)
        view.addSubview(b)
    }

    // ↑↓←→ と Z・回転の組。args の "@m" は移動量 m、"-@m" はその逆、"@a" は回転量に置き換える
    func cluster(_ x0: CGFloat, _ top: CGFloat, _ flag: String, _ view: NSView) {
        let w: CGFloat = 42, g: CGFloat = 3, r = 32 as CGFloat
        let hook = flag == "--hook"
        func col(_ i: CGFloat) -> CGFloat { return x0 + i * (w + g) }
        func args(_ dx: String, _ dy: String, _ dz: String, _ dr: String, _ da: String) -> [String] {
            return hook ? [flag, dx, dy, dz, dr, da] : [flag, dx, dy, dz, da]
        }
        button("↑", col(1), top - r, w, args("0", "@m", "0", "0", "0"), view)
        button("Z+", col(3), top - r, w, args("0", "0", "@m", "0", "0"), view)
        button("←", col(0), top - 2 * r, w, args("-@m", "0", "0", "0", "0"), view)
        button("→", col(2), top - 2 * r, w, args("@m", "0", "0", "0", "0"), view)
        button("Z-", col(3), top - 2 * r, w, args("0", "0", "-@m", "0", "0"), view)
        button("↓", col(1), top - 3 * r, w, args("0", "-@m", "0", "0", "0"), view)
        button("⟲", col(0), top - 4 * r, w, args("0", "0", "0", "0", "@a"), view)
        button("⟳", col(1), top - 4 * r, w, args("0", "0", "0", "0", "-@a"), view)
        if hook {
            button("R-", col(2), top - 4 * r, w, args("0", "0", "0", "-@m", "0"), view)
            button("R+", col(3), top - 4 * r, w, args("0", "0", "0", "@m", "0"), view)
        } else {
            button("接地", col(3), top - 3 * r, w, ["--ground"], view)
        }
    }

    func build() {
        let W: CGFloat = 392, H: CGFloat = 250, M: CGFloat = 12
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                        styleMask: [.titled, .closable, .utilityWindow, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.title = "クレーン操作"
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        if let vf = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: vf.maxX - W - 340, y: vf.maxY - H - 60))
        }
        panel.setFrameAutosaveName("AshibaCranePanel")
        let v = panel.contentView!
        let top = H - M - 20
        v.addSubview(label("車両操作", NSRect(x: M, y: top, width: 160, height: 18), bold: true))
        v.addSubview(label("フック座標", NSRect(x: W / 2 + 4, y: top, width: 160, height: 18), bold: true))
        cluster(M, top, "--car", v)
        cluster(W / 2 + 4, top, "--hook", v)
        v.addSubview(label("移動量 1m・15° ＋Shift 10m・45° ＋Control 0.1m・1°", NSRect(x: M, y: 30, width: W - 2 * M, height: 16), size: 11))
        status = label("クレーンを選んで押す", NSRect(x: M, y: 10, width: W - 2 * M, height: 16), size: 11)
        status.lineBreakMode = .byTruncatingTail
        v.addSubview(status)
    }

    @objc func clicked(_ sender: NSButton) {
        if busy { return }
        let f = NSEvent.modifierFlags
        let m = f.contains(.shift) ? "10" : f.contains(.control) ? "0.1" : "1"
        let a = f.contains(.shift) ? "45" : f.contains(.control) ? "1" : "15"
        let args = actions[sender.tag].map { s -> String in
            switch s {
            case "@m": return m
            case "-@m": return "-" + m
            case "@a": return a
            case "-@a": return "-" + a
            default: return s
            }
        }
        run(args)
    }

    func run(_ args: [String]) {
        busy = true
        status.stringValue = "…"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = [root + "/scripts/crane_move.py"] + args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONIOENCODING"] = "utf-8"
        if !port.isEmpty { env["ASHIBA_PORT"] = port }
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: root)
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.terminationHandler = { _ in
            let text = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let last = text.split(separator: "\n").last.map(String.init) ?? ""
            DispatchQueue.main.async {
                self.status.stringValue = last
                self.busy = false
            }
        }
        do { try p.run() } catch {
            status.stringValue = "動かせませんでした"
            busy = false
        }
    }

    func windowWillClose(_ notification: Notification) { NSApp.terminate(nil) }
}

let argv = CommandLine.arguments
guard argv.count >= 3 else {
    FileHandle.standardError.write("使い方: AshibaCrane <ashiba> <python> [ポート]\n".data(using: .utf8)!)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let crane = CranePanel(root: argv[1], py: argv[2], port: argv.count > 3 ? argv[3] : "")
crane.build()
if ProcessInfo.processInfo.environment["ASHIBA_PALETTE_SELFTEST"] != nil {
    print(crane.buttons.map { $0.title }.joined(separator: ","))
    if let png = ProcessInfo.processInfo.environment["ASHIBA_PALETTE_SNAPSHOT"] {
        crane.panel.appearance = NSAppearance(named: .aqua)
        crane.panel.setFrameOrigin(NSPoint(x: -10000, y: -10000))
        crane.panel.orderFrontRegardless()
        crane.panel.display()
        let v = crane.panel.contentView!
        if let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: png))
        }
    }
    exit(0)
}
crane.panel.orderFrontRegardless()
app.run()
