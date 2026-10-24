// 足場の条件の窓（scripts/form_dialog.py が swiftc で作って開く）.
//
// 利用者の指定（2026-10-24）「配置の時 足場の種類選べるようにして。条件の部分がどうやるのかわからない」。
// 足場条件の部品の設定ダイアログ（⌘T）は探しにくいので、配置・条件のボタンを押すとこの窓が前に出て、
// 足場の種類・系列・幅・手すり・階段などを選べる。項目は JSON で受け取り、押したボタンと選んだ値を JSON で返す。
// 引数: <項目の JSON> <結果を書く JSON>。環境変数 ASHIBA_FORM_SNAPSHOT=<png> で窓の絵を書いて終わる（試験用）。
import AppKit

struct Field: Decodable {
    let key: String
    let label: String
    let kind: String            // "choice" / "text" / "number" / "check" / "section"
    let options: [String]?
    let value: String?
    let help: String?
}
struct ButtonSpec: Decodable { let id: String; let label: String }
struct Form: Decodable {
    let title: String
    let intro: String?
    let fields: [Field]
    let buttons: [ButtonSpec]
}

final class FormWindow: NSObject, NSWindowDelegate {
    let form: Form
    let resultPath: String
    var window: NSWindow!
    var controls: [String: NSView] = [:]

    init(form: Form, resultPath: String) {
        self.form = form; self.resultPath = resultPath
        super.init()
    }

    func build() {
        let W: CGFloat = 520, M: CGFloat = 16, LW: CGFloat = 150, RH: CGFloat = 28
        var rows: CGFloat = 0
        for f in form.fields { rows += (f.kind == "section") ? 30 : RH }
        let introH: CGFloat = (form.intro ?? "").isEmpty ? 0 : 44
        let H = M + introH + rows + 16 + 32 + M
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = form.title
        window.level = .floating
        window.delegate = self
        let v = window.contentView!
        var y = H - M
        if let intro = form.intro, !intro.isEmpty {
            let l = NSTextField(wrappingLabelWithString: intro)
            l.frame = NSRect(x: M, y: y - introH + 4, width: W - 2 * M, height: introH - 4)
            l.font = .systemFont(ofSize: 12)
            l.textColor = .secondaryLabelColor
            v.addSubview(l)
            y -= introH
        }
        for f in form.fields {
            if f.kind == "section" {
                let l = NSTextField(labelWithString: f.label)
                l.font = .boldSystemFont(ofSize: 13)
                l.frame = NSRect(x: M, y: y - 26, width: W - 2 * M, height: 20)
                v.addSubview(l)
                let line = NSBox(frame: NSRect(x: M, y: y - 29, width: W - 2 * M, height: 1))
                line.boxType = .separator
                v.addSubview(line)
                y -= 30
                continue
            }
            let l = NSTextField(labelWithString: f.label)
            l.alignment = .right
            l.font = .systemFont(ofSize: 13)
            l.frame = NSRect(x: M, y: y - RH + 5, width: LW, height: 18)
            v.addSubview(l)
            let cx = M + LW + 10, cw = W - cx - M
            var c: NSView
            switch f.kind {
            case "choice":
                let p = NSPopUpButton(frame: NSRect(x: cx, y: y - RH + 1, width: cw, height: 25), pullsDown: false)
                p.addItems(withTitles: f.options ?? [])
                if let val = f.value, p.itemTitles.contains(val) { p.selectItem(withTitle: val) }
                c = p
            case "check":
                let b = NSButton(checkboxWithTitle: f.help ?? "", target: nil, action: nil)
                b.frame = NSRect(x: cx, y: y - RH + 4, width: cw, height: 20)
                b.state = (f.value == "1" || f.value == "true") ? .on : .off
                c = b
            default:
                let t = NSTextField(frame: NSRect(x: cx, y: y - RH + 3, width: f.kind == "number" ? 120 : cw, height: 22))
                t.stringValue = f.value ?? ""
                if f.kind == "number" {
                    let u = NSTextField(labelWithString: f.help ?? "")
                    u.font = .systemFont(ofSize: 11)
                    u.textColor = .secondaryLabelColor
                    u.frame = NSRect(x: cx + 128, y: y - RH + 6, width: cw - 128, height: 16)
                    v.addSubview(u)
                }
                c = t
            }
            if let h = f.help, f.kind != "check" { c.toolTip = h; l.toolTip = h }
            v.addSubview(c)
            controls[f.key] = c
            y -= RH
        }
        // ボタン（右から: 最初のボタンが既定＝Return）
        var bx = W - M
        for (i, b) in form.buttons.enumerated() {
            let btn = NSButton(title: b.label, target: self, action: #selector(pressed(_:)))
            btn.bezelStyle = .rounded
            btn.sizeToFit()
            let bw = max(btn.frame.width + 16, 90)
            bx -= bw
            btn.frame = NSRect(x: bx, y: M, width: bw, height: 32)
            btn.tag = i
            if i == 0 { btn.keyEquivalent = "\r" }
            if b.id == "cancel" { btn.keyEquivalent = "\u{1b}" }
            v.addSubview(btn)
            bx -= 8
        }
        window.center()
    }

    func values() -> [String: String] {
        var out: [String: String] = [:]
        for (k, c) in controls {
            if let p = c as? NSPopUpButton { out[k] = p.titleOfSelectedItem ?? "" }
            else if let b = c as? NSButton { out[k] = b.state == .on ? "1" : "0" }
            else if let t = c as? NSTextField { out[k] = t.stringValue }
        }
        return out
    }

    func finish(_ id: String) {
        let obj: [String: Any] = ["button": id, "values": values()]
        if let data = try? JSONSerialization.data(withJSONObject: obj, options: []) {
            try? data.write(to: URL(fileURLWithPath: resultPath))
        }
        exit(0)
    }

    @objc func pressed(_ sender: NSButton) { finish(form.buttons[sender.tag].id) }
    func windowWillClose(_ notification: Notification) { finish("cancel") }
}

let argv = CommandLine.arguments
guard argv.count >= 3, let data = FileManager.default.contents(atPath: argv[1]),
      let form = try? JSONDecoder().decode(Form.self, from: data) else {
    FileHandle.standardError.write("使い方: AshibaForm <項目の JSON> <結果の JSON>\n".data(using: .utf8)!)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let fw = FormWindow(form: form, resultPath: argv[2])
fw.build()
if let png = ProcessInfo.processInfo.environment["ASHIBA_FORM_SNAPSHOT"] {
    fw.window.appearance = NSAppearance(named: .aqua)
    fw.window.setFrameOrigin(NSPoint(x: -10000, y: -10000))
    fw.window.orderFrontRegardless()
    fw.window.display()
    let v = fw.window.contentView!
    if let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
        v.cacheDisplay(in: v.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: png))
    }
    exit(0)
}
fw.window.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)
app.run()
