// 仮設パレットの窓（scripts/ashiba_palette.py が swiftc で作って開く）.
//
// 利用者の指定（2026-10-22）「Tapirの足場を一つにパレットとしてまとめて、使いやすいように工夫して」。
// Archicad の前に浮いた小窓に、仮設のすべての操作を組ごとのボタンで並べる。窓の上の一覧で組を選ぶと、その組のボタンだけを出す
// （利用者の指定 2026-11-01: パレットを整理して。組は src/ashiba/palette.py の PANEL_GROUPS、最後に開いた組を次も開く）
// - 押しても Archicad の選択は外れない（前に出ない窓）。ボタンに指を置くと、いつ押すかの説明が出る
// - 選んでいるもの（躯体スラブ・足場・分解した支柱・足場条件の部品）を数秒ごとに見て、合う操作に★を付ける
// - 実行中は他のボタンを押せない。終わると結果の要点を窓の下に出す（ダイアログは出さない）
// 実行は scripts/palette_run.py（Python）に任せる。
// 引数: <ashiba> <python> <並びの JSON> <ashiba_out> [ポート]。環境変数 ASHIBA_PALETTE_SELFTEST で窓を作って並びを出して終わる。
// （osascript の JavaScript では ObjC.registerSubclass が止まって窓を作れなかった 2026-10-22）
import AppKit

struct Action: Decodable { let title: String; let hint: String; let when: [String] }
struct Group: Decodable { let group: String; let actions: [Action] }
struct Kinds: Decodable { let kinds: [String]; let desc: String }

final class Palette: NSObject, NSWindowDelegate {
    let root: String, py: String, out: String, port: String
    let groups: [Group]
    var acts: [Action] = []
    var panel: NSPanel!
    var status: NSTextField!
    var result: NSTextView!
    var buttons: [NSButton] = []
    var groupPopup: NSPopUpButton!
    var groupOf: [Int] = []            // ボタン（操作）ごとの組の番号
    var task: Process?
    var taskTitle = ""
    var kindTask: Process?
    var kinds: [String] = []
    var lastKinds = Date.distantPast
    var busy = false

    init(root: String, py: String, layout: [Group], out: String, port: String) {
        self.root = root; self.py = py; self.groups = layout; self.out = out; self.port = port
        super.init()
        for (gi, g) in layout.enumerated() {
            acts.append(contentsOf: g.actions)
            groupOf.append(contentsOf: Array(repeating: gi, count: g.actions.count))
        }
    }

    func label(_ text: String, _ frame: NSRect, size: CGFloat, bold: Bool) -> NSTextField {
        let l = NSTextField(labelWithString: text)
        l.frame = frame
        l.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        return l
    }

    func button(_ title: String, _ frame: NSRect, tag: Int) -> NSButton {
        let b = NSButton(frame: frame)
        b.bezelStyle = .rounded
        b.title = title
        b.tag = tag
        b.target = self
        b.action = #selector(clicked(_:))
        return b
    }

    func build() -> CGFloat {
        let W: CGFloat = 300, M: CGFloat = 12, BH: CGFloat = 28, RES: CGFloat = 150, PH: CGFloat = 26
        let BW = (W - 2 * M - 8) / 2
        let rows = groups.map { CGFloat(($0.actions.count + 1) / 2) }.max() ?? 1
        let H = M + 36 + 6 + PH + 8 + rows * (BH + 4) + 4 + 6 + RES + 6 + BH + M

        // 題・閉じる・小さな枠（ユーティリティ）、押しても前に出ない（Archicad の選択を保つ）
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                        styleMask: [.titled, .closable, .utilityWindow, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.title = "仮設パレット"     // 利用者の指定 2026-11-01: 足場パレットじゃなく仮設パレットに
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        if let vf = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: vf.maxX - W - 24, y: vf.maxY - H - 60))
        }
        panel.setFrameAutosaveName("AshibaPalette")     // 動かした位置を次も使う
        let view = panel.contentView!

        var y = H - M - 36
        status = label("選んでいるものを見ています…", NSRect(x: M, y: y, width: W - 2 * M, height: 36), size: 11, bold: false)
        status.lineBreakMode = .byWordWrapping
        status.maximumNumberOfLines = 2
        view.addSubview(status)
        // 組の一覧（★は今の選択に合う操作のある組）
        y -= 6 + PH
        groupPopup = NSPopUpButton(frame: NSRect(x: M, y: y, width: W - 2 * M, height: PH), pullsDown: false)
        groupPopup.addItems(withTitles: groups.map { $0.group })
        groupPopup.target = self
        groupPopup.action = #selector(groupChanged(_:))
        view.addSubview(groupPopup)
        y -= 8
        // どの組のボタンも同じ所から並べ、選んだ組だけを見せる
        let top = y
        var idx = 0
        for g in groups {
            y = top
            for (j, a) in g.actions.enumerated() {
                let col = CGFloat(j % 2)
                if j % 2 == 0 { y -= BH + 4 }
                let b = button(a.title, NSRect(x: M + col * (BW + 8), y: y, width: BW, height: BH), tag: idx)
                b.toolTip = a.hint
                view.addSubview(b)
                buttons.append(b)
                idx += 1
            }
        }
        y = top - rows * (BH + 4) - 4
        y -= 6 + RES
        let sv = NSScrollView(frame: NSRect(x: M, y: y, width: W - 2 * M, height: RES))
        sv.hasVerticalScroller = true
        sv.borderType = .bezelBorder
        result = NSTextView(frame: NSRect(x: 0, y: 0, width: W - 2 * M - 4, height: RES))
        result.isEditable = false
        result.font = .systemFont(ofSize: 11)
        result.isVerticallyResizable = true
        result.textContainer?.widthTracksTextView = true
        result.string = "上の一覧で組を選ぶと、その組のボタンが出ます。ボタンに指を置くと、いつ押すかの説明が出ます。★は今の選択に合う操作です。"
        sv.documentView = result
        view.addSubview(sv)
        y -= 6 + BH
        let lb = button("全文のログを開く", NSRect(x: W - M - BW, y: y, width: BW, height: BH), tag: 1000)
        view.addSubview(lb)
        buttons.append(lb)
        let saved = UserDefaults.standard.integer(forKey: "AshibaPaletteGroup")
        showGroup(saved >= 0 && saved < groups.count ? saved : 0)
        return H
    }

    func showGroup(_ gi: Int) {
        for (i, b) in buttons.enumerated() where i < acts.count {
            b.isHidden = groupOf[i] != gi
        }
        groupPopup.selectItem(at: gi)
        UserDefaults.standard.set(gi, forKey: "AshibaPaletteGroup")
    }

    @objc func groupChanged(_ sender: NSPopUpButton) {
        showGroup(sender.indexOfSelectedItem)
    }

    func start(_ args: [String], to outFile: String) -> Process? {
        FileManager.default.createFile(atPath: outFile, contents: nil)
        guard let fh = FileHandle(forWritingAtPath: outFile) else { return nil }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONIOENCODING"] = "utf-8"
        if !port.isEmpty { env["ASHIBA_PORT"] = port }
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: root)
        p.standardOutput = fh
        p.standardError = fh
        do { try p.run() } catch { return nil }
        return p
    }

    func setBusy(_ b: Bool) {
        busy = b
        for x in buttons { x.isEnabled = !b }
        groupPopup.isEnabled = !b
    }

    func mark() {
        let ks = kinds.isEmpty ? ["none"] : kinds
        for (i, a) in acts.enumerated() {
            let hit = a.when.contains { ks.contains($0) }
            buttons[i].title = (hit ? "★ " : "") + a.title
            buttons[i].font = hit ? .boldSystemFont(ofSize: 12) : .systemFont(ofSize: 12)
        }
        // 組の一覧にも★（その組に今の選択に合う操作がある）
        for (gi, g) in groups.enumerated() {
            let hit = g.actions.contains { a in a.when.contains { ks.contains($0) } }
            groupPopup.item(at: gi)?.title = (hit ? "★ " : "") + g.group
        }
    }

    @objc func clicked(_ sender: NSButton) {
        if busy { return }
        if sender.tag == 1000 {
            NSWorkspace.shared.open(URL(fileURLWithPath: out + "/パレット実行.log"))
            return
        }
        guard sender.tag < acts.count else { return }
        let a = acts[sender.tag]
        if a.title == "撤去" || a.title == "型枠の撤去" {
            // 消す操作だけは確かめる（押し間違いで足場・型枠と図面が消えないように）
            let form = a.title == "型枠の撤去"
            let al = NSAlert()
            al.messageText = form ? "型枠を撤去しますか" : "足場を撤去しますか"
            al.informativeText = form ? "置いた型枠（壁・柱・梁・スラブの型枠と支保工）と、型枠支保工のレイアウトを消します。躯体と足場は消しません。"
                : "選んだ躯体スラブの足場部品と、立面・平面・詳細図のレイアウトを消します。"
            al.addButton(withTitle: "撤去する")
            al.addButton(withTitle: "やめる")
            NSApp.activate(ignoringOtherApps: true)
            if al.runModal() != .alertFirstButtonReturn { return }
        }
        taskTitle = a.title
        setBusy(true)
        status.stringValue = "実行中: \(a.title) …（終わるまでお待ちください）"
        result.string = a.hint
        task = start([root + "/scripts/palette_run.py", a.title], to: out + "/.palette_result.txt")
        if task == nil {
            status.stringValue = "\(a.title): 始められませんでした（\(py)）"
            setBusy(false)
        }
    }

    @objc func tick() {
        if let t = task, !t.isRunning {
            let text = (try? String(contentsOfFile: out + "/.palette_result.txt", encoding: .utf8)) ?? ""
            var lines = text.components(separatedBy: "\n")
            let head = lines.isEmpty ? "終わりました" : lines.removeFirst()
            status.stringValue = "\(taskTitle): \(head.isEmpty ? "終わりました" : head)"
            result.string = lines.joined(separator: "\n")
            task = nil
            setBusy(false)
            lastKinds = .distantPast           // 操作で選択が変わることがあるので、すぐ見直す
        }
        if let k = kindTask, !k.isRunning {
            if let d = try? Data(contentsOf: URL(fileURLWithPath: out + "/.palette_kinds.json")),
               let v = try? JSONDecoder().decode(Kinds.self, from: d) {
                kinds = v.kinds
                if !busy { status.stringValue = v.desc }
                mark()
            }
            kindTask = nil
        }
        if !busy, kindTask == nil, Date().timeIntervalSince(lastKinds) > 4 {
            lastKinds = Date()
            kindTask = start([root + "/scripts/palette_run.py", "--kinds"], to: out + "/.palette_kinds.json")
        }
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.terminate(nil)
    }
}

let argv = CommandLine.arguments
guard argv.count >= 5,
      let data = FileManager.default.contents(atPath: argv[3]),
      let layout = try? JSONDecoder().decode([Group].self, from: data) else {
    FileHandle.standardError.write("使い方: AshibaPalette <ashiba> <python> <並びの JSON> <ashiba_out> [ポート]\n".data(using: .utf8)!)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let palette = Palette(root: argv[1], py: argv[2], layout: layout, out: argv[4], port: argv.count > 5 ? argv[5] : "")
let height = palette.build()
if ProcessInfo.processInfo.environment["ASHIBA_PALETTE_SELFTEST"] != nil {
    // 試験用: 窓を作れたか（ボタンの並び）だけ出して終わる
    print(palette.acts.map { $0.title }.joined(separator: ","), Int(height))
    if let png = ProcessInfo.processInfo.environment["ASHIBA_PALETTE_SNAPSHOT"] {
        // 窓の中身を画像にする（画面の収録の許可が要らない）。★の付き方は ASHIBA_PALETTE_KINDS（例 "line"）で
        palette.kinds = (ProcessInfo.processInfo.environment["ASHIBA_PALETTE_KINDS"] ?? "")
            .split(separator: ",").map(String.init)
        palette.mark()
        if let g = ProcessInfo.processInfo.environment["ASHIBA_PALETTE_GROUP"], let gi = Int(g) { palette.showGroup(gi) }
        palette.panel.appearance = NSAppearance(named: .aqua)
        palette.panel.setFrameOrigin(NSPoint(x: -10000, y: -10000))   // 画面の外で描く
        palette.panel.orderFrontRegardless()
        palette.panel.display()
        let v = palette.panel.contentView!
        if let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: png))
        }
    }
    exit(0)
}
palette.panel.orderFrontRegardless()
Timer.scheduledTimer(timeInterval: 0.5, target: palette, selector: #selector(Palette.tick), userInfo: nil, repeats: true)
app.run()
