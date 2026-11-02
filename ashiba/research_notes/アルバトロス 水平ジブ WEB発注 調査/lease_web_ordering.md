# 仮設資材リース会社の Web 発注と BIM/CAD 連携（ashiba の発注表をつなげるか）

調査日 2026-11-02。WebSearch / WebFetch のみ。ログインが要る画面（日建ダイレクト・COLA・OPERA 等）は見ていない。

## 1. リース各社に Web 発注はあるか、何を受け付けるか

### Takeaway
日建リース（日建ダイレクト）、杉孝（COLA）、タカミヤ（OPERA）は Web 発注を持つ。どれもログインが要る会員向けの仕組み。公開資料で「ファイル取込」がはっきり書かれているのは杉孝 COLA の CSV 取込だけ。列の並びや品番の体系はどの会社も公開していない。アルインコ・信和・ダイサン・三共・中央ビルト・ヤマトについては、Web 発注の公開情報が見つからなかった。

### Cited Findings
- **日建リース工業**: カタログのページに「Web発注はこちらから可能です」とあり、入口は「日建ダイレクト」（https://ndirect.nrg.co.jp/NDirect）。「※ログインID、パスワードが必要です」「ご利用方法は担当営業までお問い合わせください」と書かれている。Excel/CSV の取込や BIM 連携は、このページには書かれていない — [日建リース カタログ・Web発注](https://www.nrg.co.jp/nikkenlease/catalog?catalog_cat=%E4%BB%AE%E8%A8%AD%E8%B3%87%E6%9D%90%E3%83%AC%E3%83%B3%E3%82%BF%E3%83%AB)
- 日建リースはこのほかに、Web からレンタルを申し込める「リース・コンシェルジェ」（https://lc-plus-web.com/）も案内している — [同上](https://www.nrg.co.jp/nikkenlease/catalog?catalog_cat=%E4%BB%AE%E8%A8%AD%E8%B3%87%E6%9D%90%E3%83%AC%E3%83%B3%E3%82%BF%E3%83%AB)
- 日建リースは構想として、「仮設施工BIMの開発・提供にとどまらず、必要な箇所の数量取り込み機能やWeb発注業務と連携させ、スマートフォンやタブレットなどのマルチデバイスに対応した資材発注・管理を一括で賄うシステム構築を目指しています」と述べている（「目指しています」なので、まだできていない段階） — [日建リース 仮設事業](https://www.nrg.co.jp/nikkenlease/service/kasetsu)
- 日建リースは 2025年2月にタカミヤの子会社になった（取得価額 15億6100万円） — [ストライク M&A ニュース](https://www.strike.co.jp/ma_news/detail.html?id=20250115b)
- **杉孝（SUGIKO）**: 「足場BIM×WEB発注システム」として「COLA」を案内している。「BIMモデルから算出した数量表を直接WEB画面へ取り込むことができ、機材発注までを簡単に行えます」。流れは次の 3 段。①SUGIKO が足場 BIM モデルを納品する。②お客様が専用システムで搬入範囲を囲って数量を出す。③「CSVから数量をワンクリックで反映」し、COLA の注文画面からそのまま発注する。対応する BIM ソフト、CSV の列の並び、会員登録の要否、提供開始の時期は、このページには書かれていない — [杉孝 BIM・3Dスキャン](https://www.sugiko.co.jp/service/technical/bim/)
- **タカミヤ**: 「OPERA」は、電話や FAX で受けていた仮設機材の受発注や配送車両の手配を「WEB上で24時間365日対応するというWEBオーダーシステム」として展開してきたもの — [タカミヤ 2023-06 リリース](https://www.takamiya.co/upload/news/20230609release.pdf)。今は Takamiya Platform の各サービスに入るポータルという位置づけ — [Takamiya Report 2024](https://corp.takamiya.co/Portals/0/ir/統合報告書/Takamiya%20Report%202024/価値創造実現への道筋と強み.pdf)
- タカミヤの「OPE-MANE」は、購入された足場機材の管理・整備を代わりに行い、全国の機材 Base から引き出せるサービス。その中の「Iq-Bid」に、Iq システムの売買に加えて「貸す／借りる」機能を足すと 2026-01-28 に発表された。この記事には、発注データの取込や BIM 連携は書かれていない — [PR TIMES 2026-01-28](https://prtimes.jp/main/html/rd/p/000000087.000098013.html)
- タカミヤは 2020-07-10 に「IqシステムとBIMを連携したサービス」を始めた。BricsCAD に足す「Takamiyaコマンド」で、範囲を選ぶと数量を計算する — [建設ITワールド 2020-09](https://ken-it.world/it/2020/09/takamiya-uses-bricscad-as-bim.html)。タカミヤのコラム（最終更新 2026-09-02）は、数量の出し方を次の 3 つとして紹介している。Revit・ArchiCAD・GLOOBE に標準で載っている集計、ConnecT.oneQS（Revit のデータを ACC で集計）、Takamiyaコマンド（BricsCAD）。CSV/Excel や発注への連携は書かれていない — [タカミヤ コラム](https://www.takamiya.co/column/plan-bimcim-softwaretype)
- **アルインコ（仮設リース）**: 公式サイトの案内では、見積の提示→契約・発注→配送→返却の順に進む。初めての取引先は契約書と発注書を取り交わしてから正式発注。オクト事業部は電話で注文を受ける。Web 受注の記載は見当たらなかった（検索結果の要約から読んだもので、ページ本文は取得していない） — [アルインコ 仮設リース事業部](https://alinco.co.jp/lease/)
- **ダイサン**: 仮設工業会から委託を受けて「仮設8D BIM」特設サイト（kasetsu-digital.com）を作り、2026-02-02 に公開した。足場の部位ごとのリスクと法令を「安全衛生情報デジタルパッケージ」にまとめたもので、発注の仕組みではない — [ダイサン リリース PDF](https://www.daisan-g.co.jp/file/news/000685.pdf)

### Inferences
- Web 発注は「元請・足場業者がログインし、画面上でリース会社の品目を選んで数量を入れる」形が基本。外から作ったファイルを受け付けると公開しているのは、杉孝 COLA の CSV 取込（それも杉孝の専用システムが出す CSV が前提）だけと読める。
- 日建リースはタカミヤの傘下に入ったので、今後は日建ダイレクトと OPERA がまとめられる可能性がある（推測。根拠になる発表は見ていない）。

### Gaps
- 日建ダイレクト・COLA・OPERA の取込形式（CSV の列、文字コード、品番の体系）はどこにも公開されていない。ログインが要るので確かめられない。担当営業に聞くしかない。
- 信和・三共・中央ビルト・ヤマト（大和）・アルインコの Web 発注の有無は、公開情報が見つからなかった（検索に出てこない＝無いとは言えない）。
- 応用技術「スートルep」（BIM から仮設足場の数量を拾うクラウド）のページは 403 で読めなかった — https://tobim.apptec.co.jp/solution/ep/

## 2. BIM/CAD と Web 発注の既にある連携（GLOOBE・Revit/Archicad・smartCON 等）

### Takeaway
福井コンピュータの GLOOBE Construction は、「各足場メーカーが提供するWEB発注システムに対応し、部材の集計結果をそのままCSV形式で出力」できるとしている。メーカーの仕様ごとにデータを合わせ、工区・節・任意の範囲で発注できる。ただし、連携先の会社名と CSV の中身は公開されていない。Archicad 向けにリース会社の発注と連携する仕組みは見つからなかった。

### Cited Findings
- GLOOBE Construction（工程計画のページ・数量集計）には次のように書かれている。「各足場メーカーが提供するWEB発注システムに対応し、部材の集計結果をそのままCSV形式で出力可能」「メーカーごとの仕様に合わせたデータ連携により工区・節・任意の範囲といった様々な単位でWEB発注ができます」「誤発注の防止や営業時間外での発注も可能」。メーカーの名前は出てこない — [GLOOBE Construction 工程計画](https://archi.fukuicompu.co.jp/products/gloobe_c/process.html)
- 仮設計画のページには「必要な足場部材の WEB 発注システムへの連携も行えます」、数量は「Excelに出力でき、積算・見積に2次利用可能」とある。「メーカー足場ダウンロード」は「国内足場メーカー11社のシステムに対応」 — [GLOOBE Construction 仮設計画](https://archi.fukuicompu.co.jp/products/gloobe_c/provisional.html)
- GLOOBE 2025（2025-07-23 発売）では、既存機能の強化として「工区・節・任意範囲で必要な足場部材の数量を自動算出。そのままWeb発注システムと連携可能」となった — [BuildApp News](https://news.build-app.jp/article/35597/)。2025 年版の新機能ガイド（PDF）には連携機能の強化として「足場発注 CSV 出力」が載っている（検索結果の要約による。PDF は 10MB を超えて取得できず、本文は確かめていない） — [GLC_2025new.pdf](https://www.fukuicompu.co.jp/mnl/GLOOBE/2025/guide/new/GLC_2025new.pdf)
- GLOOBE 2024（2024-05 発売）では、国内 8 社の足場マスタをダウンロードできるようになった。8 社はアサヒ産業、アルインコ、信和、杉孝、ダイサン、タカミヤ、東阪工業、日建リース工業 — [BUILT 2024-04-23](https://built.itmedia.co.jp/bt/articles/2404/23/news065.html)。今の製品ページは「11社」としている — [仮設計画](https://archi.fukuicompu.co.jp/products/gloobe_c/provisional.html)
- 福井コンピュータは X で、日建リース工業の BIM の取り組みの中で GLOOBE が紹介されたと告知している — [X @archifukuicompu](https://x.com/archifukuicompu/status/1936977961825321319)
- 杉孝 COLA の CSV 取込は、杉孝の「専用システム」で範囲を囲んで出した CSV が前提（上の 1 を参照） — [杉孝](https://www.sugiko.co.jp/service/technical/bim/)
- タカミヤの BIM は BricsCAD が基本で、「ほとんどのBIMソフトに変換が可能」としている — [タカミヤ コラム](https://www.takamiya.co/column/plan-bimcim-softwaretype)

### Inferences
- GLOOBE の「メーカーごとの仕様に合わせたデータ連携」とは、メーカーのマスタ（品番）で部材を置き、各社の Web 発注が取り込める CSV の形に合わせて書き出すことだと読める。連携先は、マスタを出している 8〜11 社のうち Web 発注を持つ会社（少なくとも杉孝 COLA、ほかに日建リース・タカミヤ）と思われる。ただし、どの会社に対応しているかは確かめられていない。
- 足場マスタの品番で部材を置けば、リース会社の発注側と品番がそのまま合う。これは ashiba の「規格品の品番・定尺で割り付ける」方針（スギコ アルバトロスのマスタなど）と同じ考え方。

### Gaps
- GLOOBE の足場発注 CSV の列・連携先の一覧・手順はマニュアル PDF に載っていると思われるが、読めていない（10MB 超）。福井コンピュータの製品マニュアルのページ（https://archi.fukuicompu.co.jp/user/products/gloobe/manual.html）で、2025/2026 の分冊を別に探す余地がある。
- 「smartCON Planner」の発注連携は、検索で何も見つからなかった。製品名・提供元の確認が要る。
- Revit/Archicad のアドインで、リース会社の Web 発注に直接送るもの（「Smart Ashiba」「KASETSU」など依頼にあった名前を含む）は見つからなかった。日建リースが BIM オブジェクトを Archicad 形式で出しているかどうかも確認できていない。

## 3. 業界で共通の部材コード（仮設工業会・CI-NET）

### Takeaway
足場部材でリース会社をまたいで使える共通コードや、CI-NET の仮設資材向けの品目コードは見つからなかった。実際の受け渡しは、各社の品番（マスタ）のままと見られる。

### Cited Findings
- CI-NET は、建設業振興基金が開発・保守している、国が認めた建設業の EDI 標準。ただし資機材のコードは「設備工事で使用されるものを中心とした資機材がコード化されたにとどまっている」（2000 年代の国交省資料） — [国交省資料](https://www.mlit.go.jp/common/000004974.pdf)
- 仮設工業会の委託でダイサンが作った「仮設8D BIM」は、安全衛生の情報（部位ごとのリスクと法令）を整理したもの。部材コードの仕組みは、確認できた範囲には無い — [ダイサン リリース](https://www.daisan-g.co.jp/file/news/000685.pdf)

### Inferences
- 決まった交換形式が無いので、GLOOBE は「メーカーごとの仕様に合わせた」CSV を出している（2 の引用）。この事実もそれを裏付けている。

### Gaps
- 仮設工業会の認定品番・型式番号が品目の鍵として使えるかは、調べていない。
- CI-NET の最新のコード（建設資機材コード）に仮設資材が入ったかどうかは、確認できていない（取れた資料が古い）。

## 4. ashiba は何を出せば、今リース会社に受け付けてもらえるか（提言）

### Takeaway
各社の Web 発注に直接入る、公開された取込形式は無い。現実的な形は次のとおり。(a) 会社ごとの品番をそのまま載せた Excel 発注表（担当営業に渡す・FAX/メール で送る）を主にする。(b) そのデータを「品番, 品名, 規格, 数量, 工区/節」の簡単な CSV でも出す。(c) 列の並びは会社ごとに差し替えられる設定にしておく。(d) 杉孝 COLA など相手の CSV の仕様が手に入ったら、その会社の形を足す。

### Cited Findings
- 外部の数量 CSV を取り込めると公開しているのは杉孝 COLA だけ — [杉孝](https://www.sugiko.co.jp/service/technical/bim/)
- GLOOBE も、各社の仕様に合わせた CSV を工区・節・範囲ごとに出す方式をとっている — [GLOOBE 工程計画](https://archi.fukuicompu.co.jp/products/gloobe_c/process.html)
- 日建リースの Web 発注は、使い方を担当営業に聞く形 — [日建リース](https://www.nrg.co.jp/nikkenlease/catalog?catalog_cat=%E4%BB%AE%E8%A8%AD%E8%B3%87%E6%9D%90%E3%83%AC%E3%83%B3%E3%82%BF%E3%83%AB)
- アルインコは見積→契約・発注書→配送の流れ（紙・書面の発注書が前提） — [アルインコ 仮設リース](https://alinco.co.jp/lease/)

### Inferences
- ashiba の発注表は、GLOOBE の機能に揃えると強い。そのためには次の 3 点を持たせる。①メーカーの品番を主キーにする。②工区・節（層）・任意の範囲ごとに数量を分けて出せるようにする。③CSV（UTF-8 と Shift_JIS の両方。古い取込は SJIS が多いため。ここは推測）と Excel を出す。
- 直接つなぐ（API）のは、今は無理と見るべき。公開 API の情報は 1 社も無い。
- 次にやること（調査）は 2 つ。杉孝の担当に COLA の CSV 取込の仕様（列・文字コード・品番）を聞くこと。GLOOBE 2025 のマニュアルで「足場発注 CSV 出力」の頁を読み、列の並びと対応メーカーを確かめること。

### Gaps
- 各社の取込 CSV の実物の形（列の名前・順・必須の項目・文字コード）。公開されておらず、営業経由で手に入れるしかない。
- ashiba の発注表がリース会社に紙・Excel で受け付けてもらえるかどうか（運用）は、当たり前と思われるが、資料で確かめてはいない。
