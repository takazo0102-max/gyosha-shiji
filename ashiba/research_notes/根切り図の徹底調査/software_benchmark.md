# 根切り・掘削の機能比較（施工BIM／CAD／土工ソフト）— ashiba の根切り図の物差し

調査日 2026-11-02。出典は各行の URL。マニュアル PDF は本文を取り出して読んだもの（頁は PDF の版の頁番号）。
ashiba の現状（比較の基準）: 選んだ躯体から 50mm 升目で掘削面、床付け＝躯体底−地業、余掘り 500、法面 自動/鉛直/1:0.3〜1.5、山留めの内は山留め面まで、1.1m 以下の細い地山も掘る、メッシュ＋平面の法肩・法尻・高さ・勾配の文字・面積・土量、法令の判定つき報告。寸法・断面・釜場・手順・埋戻し・残土/ダンプ台数は無し。

## GLOOBE Construction（福井コンピュータアーキテクト）の根切り・山留め・土工

### Takeaway
最も近い競合。現況地形→整地（切土・盛土）→「躯体参照（範囲）」で根切りを自動作成（根切底・ゆとり幅・法面勾配）→手で直す（辺移動・レベル変更・法肩法尻揃え・根切クリーン・釜場の追加）→根切図（掘削底のレベル色分け）と通り芯から断面図を自動作図、という一連が揃う。2026 版で埋め戻し形状の自動更新が入った。山留壁・支保工・構台・干渉・施工ステップ・LandXML まで同じ製品内。

### Cited Findings
**作り方（土工計画編（根切）2026 マニュアル）**
- 目次: 1 現況地形の入力（土工事入力に切替・土工事用地盤）／2 整地部分の入力（参照データ・整地・法面勾配）／3 掘削部分の自動作成（掘削の対象領域を指定）／4 掘削部分の編集（領域を拡張して不要部分を修正・掘削レベルを変更・法肩・法尻の位置を揃える・不要な根切を削除・掘削部分を追加）／5 図面の作成・印刷 — [GLOOBE Construction 2026 土工計画編（根切）PDF](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/manual/GLCon02_negiri.pdf)（案内頁 [HTML](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/manual/GLCon02_negiri.html?20260708)、2026/07/08 更新）
- 現況地形: 「現況地形」コマンド、入力モード「閉領域」で敷地をクリック→「各点高」ダイアログで頂点ごとの高さ（例 頂点1：600、頂点4：-300）。TREND-POINT の現況連携データ（点群）も読み込める — 同 PDF p.3–4
- 整地: 入力モード「矩形」、整地高さ（例 GL 0）を指定すると切土体積・盛土体積が同時に表示 — 同 PDF p.6
- 法面勾配は**辺ごと**: 「法面勾配」→整地の各辺に「勾配／鉛直」の文字→辺の文字をクリックして設定。単位は「度」「1/n」「%」を切替。切土・盛土の体積が変わり、マニュアルは「土砂の搬出等に必要なトラックの台数等の計算に有効」と書く（台数そのものを計算する機能かは未確認）— 同 PDF p.7
- 自動の根切り: 「掘削」→土工事用地盤をクリック→「根切り」コマンド、入力モード「躯体参照（範囲）」。設定は「根切底」（例 設計GL−1400）・「ゆとり幅」（例 500）・「法面勾配」（例 0.3）。「根切り精度」（任意形状・汎用オブジェクトを「簡易」等）あり。参照する躯体の範囲を囲む（例では後打ちの土間コンを外して囲む）。基礎・地中梁に合わせて掘削され、掘削体積も表示 — 同 PDF p.8–9
- 掘削底のレベル別の色分け: 「レベル色分けを有効にする」「色一括セット」（グラデーション／虹色、個別の色も可）。平面・3D とも — 同 PDF p.10
- 手直し（自動のあとに「小さな山など実務上の不具合箇所を修正」と明記）: 掘削領域を選ぶと辺長と法面勾配が出る、ハンドル「辺移動」で広げる／根切り底レベルを隣に合わせて変える（−150→−950 等）／「法肩・法尻揃え」コマンド（基準の法肩・法尻→揃える側をクリック）／補助寸法線の辺長を数値で変える／「根切クリーン（一括）」で掘削に影響しない不要な根切を一括削除 — 同 PDF p.11–16
- 釜場: 「根切り」入力モード「矩形」で根切り底 設計GL−2500・ゆとり幅 0・法面勾配 0 として追加（専用の釜場コマンドではなく矩形の根切りとして入れる）— 同 PDF p.17
- 図面: 「図面作成」→「土工計画図」メニューの「総合図」（テンプレート「01_土工計画総合図／02_カラー土工計画総合図」、A2 横の用紙枠）、「断面図」（テンプレート「01_土工計画断面図／02_カラー総合断面図」）は「断面を開く」の入力モード「断面線（通り芯参照）」で通り芯（Y2・X2 等）と向きを指すだけ — 同 PDF p.18–20
- 製品頁の記載: 根伐図は掘削レベルに応じたカラー表現、日付と作業を指定して施工ステップを確認。リアルタイム土量計算（現況地形から整地時の切土・盛土、掘削時の掘削体積）。土工計画断面図を自動作図し、労働安全衛生法第88条の計画届の添付書類に活用。概算数量は Excel 出力、掘削・支保工のレベル（一次掘削・二次掘削）を躯体を参照して設定し、レベル別に集計。掘削データを LandXML に出して ICT 建機へ — [GLOOBE Construction 土工計画](https://archi.fukuicompu.co.jp/products/gloobe_c/earthwork.html)
- 山留: シートパイル・親杭横矢板・SMW、コーナーの取り合いを一操作。「山留支保工」で腹起し、「山留支保工編集」で切梁等、躯体との干渉確認。構台は入力設定から各部材を自動配置し、躯体・支保工との干渉を見ながら詳細検討 — [同頁](https://archi.fukuicompu.co.jp/products/gloobe_c/earthwork.html)
- 2020 年の発売時の紹介: 基礎データから根切り図を自動作成、TREND-POINT の点群を現況地形に、土工モデルを LandXML でICT施工へ — [建設ITワールド 2020-11](https://ken-it.world/it/2020/11/gloobe-construction-entered.html)
- 根切り・杭芯・設備基礎の位置を CSV・SIMA で出して測量機器へ — [福井コンピュータグループ製品一覧](https://www.fcgr.jp/fad/product/gloobe_c/detail/?tab=feature)
- 山留壁・支保工・構台の部材と土量を自動集計（動画の説明）— [YouTube 土工計画【GLOOBE Construction】](https://www.youtube.com/watch?v=ZfgpYdo16SY)

**GLOOBE 2026（2026年7月リリース）の土工事の新機能** — [GLOOBE 2026 Construction 新機能 PDF p.24–25](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/new/GLC_2026new.pdf)（案内 [HTML](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/new/GLC_2026new.html?20260708)）
- 「土工事用地盤の精度向上」: 掘削・埋め戻し形状の立体精度を上げ「穴抜けや塞がり」を軽減。根切り入力時に許容誤差以内の頂点ずれを補正、埋め戻し形状は許容誤差 1.0mm で梁・スラブも含めて補正
- 「山留壁・山留支保工の FL 基準入力対応」
- 「埋め戻し更新」コマンド新設: 杭・基礎工事での変更（例 土間の削除）を土工事の**埋め戻し形状**に反映。「根切り」の入力・削除・プロパティ変更、「根切りクリーン」完了時、「法肩・法尻揃え」完了時は自動で埋め戻し形状を更新 → つまり GLOOBE には掘削と別に埋め戻し形状（躯体の外の空き）がある
- 同版の工程計画: 工区タイプに「躯体工事」「基礎工事」を追加（最下層の工区割り）

### Inferences
- GLOOBE の自動根切りは「根切底を1つ指定＋ゆとり幅＋法面勾配」で、躯体ごとの底から床付けを決める ashiba の方式（躯体底−地業）とは発想が違う。GLOOBE は自動のあとに人が直す前提（小さな山・揃え・クリーン）で、ashiba の「1.1m 以下の細い地山も掘る」は GLOOBE の手直しの一部を自動化している。
- GLOOBE にあって ashiba に無いもの: 現況地形（各点高・点群）と整地の切土/盛土、辺ごとの勾配の手直し、法肩・法尻揃え、寸法値での辺の編集、掘削底のレベル色分け、通り芯から断面図の自動作図、総合図テンプレート、釜場（矩形根切りで代用）、埋め戻し形状とその自動更新、レベル別の概算数量 Excel、施工ステップ（日付）、LandXML/CSV/SIMA 出力、山留・支保工・構台との干渉。
- ashiba にあって GLOOBE で確認できなかったもの: 法面勾配の「自動」（土質・深さからの決定）、法令の判定（安衛則356条等）を出す報告。GLOOBE は計画届の添付図に使えると言うが判定はうたっていない。

### Gaps
- GLOOBE の根切断面図に寸法・レベルの注記がどこまで自動で入るかは PDF の図からは読み取れず未確認。
- 「トラック台数」を GLOOBE が自動で数えるのか、体積を見て人が計算するのかは未確認（マニュアルは「計算に有効」とだけ書く）。
- 土量変化率（L・C）・残土量の扱い、段掘り専用の機能、2025 版新機能（PDF が 10MB 超で読めず）は未確認。土工計画編（山留）2026 も同じ理由で本文未読。

## smartCON Planner（SCP、Archicad アドオン、鹿島建設開発・Global BIM 販売）

### Takeaway
Archicad で唯一確認できた市販の根切りアドオン。躯体から部材ごとに「掘削オブジェクト」を作り、利用者が Archicad のソリッド編集で敷地を削って根切りモデル・掘削数量モデルにする。法面は角度、余掘りは横オフセット。図面・土量表・判定は持たず、Archicad 標準の機能に任せる。

### Cited Findings
- 対応は Archicad 29 と 28 のみ。機能: 掘削形状生成（「親杭基礎、地中梁などの構造体モデルから掘削形状を生成」「根切図のモデル作成や掘削土量のモデル作成が可能」）、山留め（親杭横矢板・鋼矢板・SMW 等、仕様は辺単位で変更）、切梁・腹起し・火打ち、地盤アンカー（角度・長さ）、構台、建機・車両（油圧ショベル・ダンプ等）、車両軌跡、選んだ部材の体積・重量の合計表示 — [SCP 製品頁](https://scp.global-bim.com/?page=software)
- 「掘削形状生成」の設定: 横オフセット（躯体側面から法尻まで）、深オフセット（躯体底面から床付け面まで、底面の法線方向）、GL から掘削形状の天端レベル、法面の角度、配置レイヤー。作成元の部材は複数選べるが**部材ごとに個別の掘削形状**。底面範囲角度（その角度以下の傾斜を底面とみなす、超える傾斜面には作らない）、頂点丸め基準角度。底面の高さが違う部材は底面ごとに別形状 — [smartCON Planner for Archicad27 操作マニュアル 2024/02/15 p.73–74](https://scp.global-bim.com/Content/download/manual/usermanual_all_20240215.pdf)
- 一つにまとめるには利用者が「選択内容をモルフに変換」→「ブール演算」「結合」。平面に稜線を出すには材質上書きを「ガラス-シンプル」に — 同 p.74
- 根切モデル: [デザイン]→[ソリッド編集]で敷地をターゲット、掘削オブジェクトをオペレータとして「上方向へ減算」→敷地をモルフ化（以後は戻せない）。2D は 3D ドキュメントでも可。掘削数量モデル: 敷地を2つにコピーし、①を減算→モルフ化、②から①を減算すると掘削量の立体が残り、体積表示ツールで数量。「敷地が傾斜してる場合にも有効」— 同 p.75
- 山留め側に「床付けレベルの設定」（[同一]／[個別]）と、床付け設定で見付け面積を表示 — 同 マニュアル（山留めの章）
- 利用例: 掘削形状を使った捨てコンの一括モデリング、シートパイルの凹凸に合わせて敷地をカット — [Graphisoft Community 捨てコン](https://community.graphisoft.com/t5/How-to-use-Archicad-NEW/%E3%82%A2%E3%83%89%E3%82%AA%E3%83%B3%E3%82%BD%E3%83%95%E3%83%88%E3%82%92%E6%B4%BB%E7%94%A8%E3%81%97%E3%81%A6%E6%8D%A8%E3%81%A6%E3%82%B3%E3%83%B3%E4%B8%80%E6%8B%AC%E3%83%A2%E3%83%87%E3%83%AA%E3%83%B3%E3%82%B0-%E6%97%A7%E3%82%B5%E3%82%A4%E3%83%88%E3%81%8B%E3%82%89%E8%BB%A2%E8%BC%89/td-p/610310)、[シートパイルの凹凸](https://community.graphisoft.com/t5/How-to-use-Archicad-NEW/%E3%82%A2%E3%83%89%E3%82%AA%E3%83%B3%E3%82%BD%E3%83%95%E3%83%88-SCP-%E3%81%AE%E3%82%B7%E3%83%BC%E3%83%88%E3%83%91%E3%82%A4%E3%83%AB%E3%81%AE%E5%87%B9%E5%87%B8%E3%81%AB%E5%90%88%E3%82%8F%E3%81%9B%E3%81%A6%E6%95%B7%E5%9C%B0%E3%82%92%E3%82%AB%E3%83%83%E3%83%88%E3%81%99%E3%82%8B-%E6%97%A7%E3%82%B5%E3%82%A4%E3%83%88%E3%81%8B%E3%82%89%E8%BB%A2%E8%BC%89/td-p/610969)
- 建災防の ICT 活用事例: 土工事〜基礎工事の仮設検討（山留計画・車両配置）を**ステップ図**で手順を見える化 — [建災防 smart CON Planner を利用した施工シミュレーション](https://www.kensaibou.or.jp/safe_tech/ict/entry/003105.html)
- 開発は鹿島建設、グラフィソフトコリア（Doalltec）と共同 — [建設通信新聞 BIMのその先を目指して・51](https://www.decn.co.jp/?p=99425)

### Inferences
- SCP は部材ごとの錐台を重ねるだけで、掘削の和集合・細い地山・山留め内の掘り切りは利用者のブール演算任せ。ashiba の升目で一つの面を作る方式はここで優位。
- SCP の「底面の法線方向の深オフセット」「底面範囲角度」は斜めの底（傾いた基礎）への対応で、ashiba が持っていない観点。
- ステップ図は SCP の機能ではなく、利用者がモデルを段階ごとに置いて作るもの（建災防事例の記述から）。

### Gaps
- SCP 2025/2026 年版（AC28/29）のマニュアルで掘削形状が変わったかは未確認（読んだのは AC27 版 2024/02/15）。

## Archicad 標準（メッシュ・ソリッド編集）

### Takeaway
Archicad に根切り専用の道具は無い。メッシュ（敷地）をスラブ等のオペレータで「上方向へ減算」するのが定番で、土量は削る前後のメッシュの体積差か、削った結果の体積で読む。法面・余掘りは自分で作る。

### Cited Findings
- 掘削量は SEO なしの敷地コピーの体積 V1 と SEO 後の体積 V2 の差 — [Graphisoft Community: Calculate Volume of Site excavations](https://community.graphisoft.com/t5/Modeling/Calculate-Volume-of-Site-excavations/td-p/183667)
- メッシュには Net Volume はあるが Gross Volume は無い、一覧表で SEO の有無の差をとる — [Community: Schedule SEOed mesh volume](https://community.graphisoft.com/t5/Collaboration-with-other/Schedule-seoed-mesh-volume/m-p/342958)
- AC23 以降、メッシュに置いた開口ツールで穴の体積が出るという報告 — [Community: Grading Calculation volume of excavation from a mesh](https://community.graphisoft.com:443/t5/Collaboration-with-other/Grading-Calculation-volume-of-excavation-from-a-mesh/td-p/265810)
- 最下階スラブか建物外形のスラブをオペレータ、メッシュをターゲットに上方向減算 — [Community: Creating an excavation plan](https://community.graphisoft.com/t5/Modeling/Creating-an-excavation-plan/m-p/272872)
- SEO 後のメッシュが「Excluded」になる不具合報告 — [Community: Solid Element Operations on Mesh indicate "Excluded"](https://community.graphisoft.com/t5/Modeling/Solid-Element-Operations-on-Mesh-indicate-quot-Excluded-quot-no/m-p/580652)

### Inferences
- ashiba が出す「メッシュそのものが掘削面」の方式は SEO の不具合（Excluded・体積の信頼性）を避けられる。土量を自前で出すのも同じ理由で利点。

### Gaps
- Graphisoft 公式のヘルプで掘削の手順を書いた頁は見つからず（フォーラムのみ）。Archicad 29/30 で敷地・掘削の新機能があるかは未確認。

## Revit（Toposolid の Excavate・Graded Region）と Revit アドイン

### Takeaway
Revit 2024 で Toposolid、2025 で Excavate ツールと掘削体積パラメータ、2026 でサブディビジョンの負オフセット掘削と Graded Region の切盛り計算の改良。いずれも「交差する床等の天端まで」削るだけで、法面・余掘りは無い。日本の Revit 向け根切り・山留めアドインは見つからなかった。

### Cited Findings
- Excavate: 床・屋根・トポソリッドを cutter にしてホストのトポソリッドから「交差する床の天端まで」体積を除く。Remove Excavation で戻す。深さのオフセット・法面・作業余裕の設定は記載なし。Cut Void Stability が x/y に小さくずらすことがある — [Revit 2026 Help: Toposolid: Excavate and Remove Excavation](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-Model/files/GUID-21047A44-6030-49E8-B1B9-03366EA6A0C2.htm)
- 掘削体積はトポソリッドのプロパティ（総掘削量）と、cutter ごとの内訳ダイアログ。集計は Toposolid Total Excavate 集計表、cutter 側は Excavate Multi-Category 集計表 — [Toposolid: Excavation Volume Parameters (2026)](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-Model/files/GUID-CF284C55-7CBF-40DD-B4D5-4DB6DED7A843.htm)
- 2026 新機能: サブディビジョンの負オフセットがホストを掘り掘削体積を報告、Graded Region の切盛りを新しいトポソリッドの境界内だけで上へ投影して計算するよう改訂、点数上限 20,000（10,000〜50,000）— [Revit 2026 What's New: Toposolid Enhancements](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-WhatsNew/files/GUID-B15F26EC-57C1-4570-8EAD-1A0C8089A23A.htm)
- 2024 では Building Pad が無くなり Cut Geometry で切るしかなく、Excavate は 2025 から。床による掘削は床の下を埋めない — [bimpure: Revit 2024](https://bimpure.com/blog/revit-2024)、[CAD Notes: Revit 2025 toposolid enhancements](https://www.cad-notes.com/revit-2025-toposolid-enhancements/)（検索要旨による、本文未精読）
- Graded Region の切盛りは近似（±2% 程度）、既存フェーズのトポソリッドが前提 — [Video: Calculate Cut and Fill Volumes (2024)](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-Model/files/GUID-B7B5057A-46DC-4BD6-8ECB-BFFA220D2B1D.htm)（±2% は検索要旨、未精読）
- 日本語で「Revit 根切り 山留め 自動作成」のアドインは見つからず（清水建設の配筋、Arent の自動配筋など配筋系のみ）— [検索で出た例: 清水建設 配筋](https://bim-design.com/user-story/shimz-haikin/)、[LightningBIM 自動配筋](https://ken-it.world/it/2022/05/automatic-rebar-bim-modeling.html)

### Inferences
- Revit 標準は「掘る形」を利用者が作る前提で、躯体から余掘り・法面つきの掘削形状を作る機能は無い。BIMLOGIQ・Naviate・Arkance の Excavation 系アドインは今回確認できなかった。

### Gaps
- BIMLOGIQ／Naviate／Arkance／BooT.one の掘削機能、Dynamo の掘削スクリプトは調べきれず未確認。

## 他社の自社ツール・土木系・機械土工のソフト

### Takeaway
ゼネコンは自社ツールを持つ（東急建設の山留ツール、鹿島の SCP）。土木系は山留めの「計算」（FORUM8）、地形の切盛り（Civil 3D）、機械土工の段取り（コマツ Smart Construction Simulation のダンプ台数・ルート）が強い。いずれも建築の根切り図そのものは作らない。

### Cited Findings
- 東急建設「仮設計画ツール」の山留ツール: 地下掘削形状・山留め部材を配置、BIM 設計モデルから施工計画モデルを数クリックで、2022年4月から社内運用（出力の記載なし）— [ビジネス+IT 2022-05-19](https://www.sbbit.jp/article/refers/87729)
- FORUM8「土留め工の設計・3DCAD」: 慣用法と弾塑性法の同時計算、自立時・掘削時・撤去時のステージ検討、腹起し・切ばり・火打ち・中間杭の照査と図面。性能設計計算版は斜め切ばり・アンカー併用・撤去順序の自由化 — [FORUM8 製品ガイド 土留め工 vol.34](https://ftp.forum8.co.jp/forum8lib/proguide/vol34/dodome.pdf)（検索要旨、版は古い可能性）
- Civil 3D: フィーチャラインから法面を地表まで延ばす（Grade to Daylight、勾配は 3H:1V 表記）、掘削量は土量サーフェス（Volume Surface）で求めるのが正しく、境界を引くだけでは法面分が漏れる — [Autodesk Civil 3D Best Practices: Feature Lines and Projection Grading](https://help.autodesk.com/cloudhelp/2022/ENU/Civil3D-BestPractices/files/GUID-C24BF6AB-FE55-4A23-BD66-D38B2E3CFE58.htm)、[Autodesk Forum: Grading between two surfaces](https://forums.autodesk.com/t5/civil-3d-forum/grading-between-two-surfaces/td-p/6916913)
- コマツ Smart Construction Simulation: 地形と設計から AI が切盛り量を計算、施工手順（最も効率的な土の配分と作業順）のアニメーション、機械の配置、ダンプの台数（例 20t 車 43 台）、走行ルート・積込み・荷下ろし場所 — [Smart Construction Simulation](https://jp.smartconstruction.com/en/smart-construction-simulation)
- 国交省の資料: 4D を設定できるソフトはあるが 4D の情報交換標準は無い — [検索要旨: 農水省 BIM/CIM ダム編](https://www.maff.go.jp/j/nousin/sekkei/pdf/ICT_BIMCIM/bimcim/vol6_dam/part03_vol6_dam.pdf)（本文未精読）

### Inferences
- 「残土・ダンプ台数・搬出の段取り」は建築側（GLOOBE・SCP）より機械土工側（コマツ）が強い。ashiba で足すなら土量×変化率 L÷1台の積載で台数、という単純計算で GLOOBE を超えられる可能性がある。

### Gaps
- 「快速土量」（建設システム）は製品自体を確認できず。福井コンピュータ TREND-ONE／TREND-POINT／TREND-CORE、Trimble Business Center の土量機能は時間内に一次情報を確認できず未記載。
- 「SMART CON Planner（シーティーエス/キャドネット）」という別製品は見つからず。smartCON Planner は上記の SCP（鹿島・Global BIM）。

## 土量の計算方法（平均断面法・点高法・TIN・プリズモイダル）

### Takeaway
国の 3次元の要領は TIN による求積とプリズモイダル法を挙げ、点高法も使われる。グリッド（メッシュ）法は間隔で精度が決まり TIN の方が正確とされる。平均断面法は従来の寸法による方法として残る。ashiba の 50mm 升目は点高法（メッシュ法）に当たる。

### Cited Findings
- 国交省（港湾）の要領: TIN は表面を変化点の標高で補間する一般的な構造。求積は各 TIN の水平投影面積×頂点から基準面までの平均高低差の総和。プリズモイダル法は両面の TIN の点を互いに投影して体積を出す — [国交省 港湾 3次元データ 要領 001475808](https://www.mlit.go.jp/kowan/content/001475808.pdf)（検索要旨、本文の頁未確認）
- 国総研の論文: 点高法（一点法）と点高法（四点平均法）で数量を算出、同じ方法でもソフトの有効桁数・アルゴリズムで差が出る — [国総研 土木情報学論文 2018](https://www.nilim.go.jp/lab/qbg/achievements/papers/pdf/201809_dobokujyouhougaku04_43-49.pdf)
- Civil 3D の資料: グリッド土量サーフェスは軽いが精度はグリッド間隔次第、TIN 土量サーフェスが最も正確 — [Autodesk Civil 3D 入門セミナー vol.5](https://bim-design.com/infra/assets/file/seminar_civil3d_entry_vol5.pdf)
- 点群から 3次元 CAD で計った寸法を平均断面法の体積計算に使ってよい（従来法）、点群から直接数量を出す方法も示す。精度は寸法で ±20mm、3次元 CAD で ±50mm — [沖縄県 SLAM 試行要領](https://www.pref.okinawa.jp/_res/projects/default_project/_page_/001/013/337/slam_sikouyouryou.pdf)
- 点群のメッシュ法で施工前後の土量差、平均断面法より時間短縮・精度向上 — [北陸地整 施工土量計測 概要](https://www.hrr.mlit.go.jp/bosai/saishingijutsu/6_sekoudoryoukeisoku/gaiyou.pdf)（検索要旨）

### Inferences
- 50mm 升目の点高法は、建築の根切り（平らな床付けと一様な法面）なら TIN との差は小さいはず。報告に「点高法（50mm 升目）」と方法名を書けば、公共の数量の説明に足りる見込み。

### Gaps
- 公共建築の積算（公共建築数量積算基準）が根切り量をどう数えるか（根切り幅・余掘りの見方、法の扱い）は今回の範囲で一次情報を確認できず — 別の調査担当に回すべき。
- 平均断面法と点高法の精度を直接比べた国の資料は見つからず。

## 出力の比較と ashiba に足りないもの（まとめ）

### Takeaway
ashiba に足りないのは主に「図面化」（寸法・断面・総合図）と「後工程」（埋戻し・残土・ダンプ・手順）。自動の質（細い地山・山留め内・法令判定）は競合より上。

### Cited Findings
- 断面図を通り芯から自動、総合図テンプレート、レベル色分け — [GLOOBE 根切 PDF p.10, 18–20](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/manual/GLCon02_negiri.pdf)
- 埋め戻し形状と自動更新 — [GLOOBE 2026 新機能 p.24–25](https://www.fukuicompu.co.jp/mnl/GLOOBE/2026/guide/new/GLC_2026new.pdf)
- 施工ステップ（日付）・Excel の概算数量（レベル別）・LandXML — [GLOOBE 土工計画](https://archi.fukuicompu.co.jp/products/gloobe_c/earthwork.html)
- CSV/SIMA で根切り位置を測量機器へ — [fcgr 製品一覧](https://www.fcgr.jp/fad/product/gloobe_c/detail/?tab=feature)
- ステップ図（SCP 利用の建災防事例）— [建災防](https://www.kensaibou.or.jp/safe_tech/ict/entry/003105.html)
- ダンプ台数・ルート — [Smart Construction Simulation](https://jp.smartconstruction.com/en/smart-construction-simulation)

### Inferences（足りないものの候補、確かさの順）
1. 断面図（通り芯を指して作る、法肩・法尻・床付けの高さと勾配の注記）— GLOOBE が持つ。
2. 平面の寸法（躯体から法尻まで・法肩まで）と、寸法で辺を直す手直し・法肩法尻揃え — GLOOBE が持つ。
3. 釜場（矩形の追加の掘削）— GLOOBE は矩形の根切りで代用。
4. 埋戻し量（掘削−躯体−地業）と残土量、変化率 L/C、ダンプ台数 — GLOOBE は埋め戻し形状、台数はコマツ側。
5. 掘削底のレベル色分け（平面と 3D）— GLOOBE。
6. 現況地形（点の高さ・点群）からの掘削と整地の切土・盛土 — GLOOBE（各点高・TREND-POINT）。ashiba が地盤を平らと仮定しているなら差になる。
7. 一次掘削・二次掘削（支保工の段ごとのレベル）と施工ステップ — GLOOBE・SCP 事例。
8. Excel/CSV の数量表、LandXML・SIMA の書き出し — GLOOBE。
9. 斜めの底（傾いた基礎）への深さの取り方（底面の法線方向）— SCP。

### Gaps
- 競合の「根切り数量表」の具体的な書式（列の並び）は、どの製品も公開資料で確認できず。
