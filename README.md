# zmk-config-roBa

[![現在のroBaキーマップ](keymap-drawer/roBa.svg)](keymap-drawer/roBa.svg)

[配置図を直接開く](keymap-drawer/roBa.svg) · [生成された配置データ](keymap-drawer/roBa.yaml)
画像・本文・keymapは、閲覧中の同じブランチの内容です。

`iwashita-nozomu/zmk-config-roBa` の個人用配置です。**ホストの配列はJIS（日本語）を前提**とします。
配置の正本は [config/roBa.keymap](config/roBa.keymap)、変更理由・検証結果は
[追跡Issue #226](https://github.com/iwashita-nozomu/project_template/issues/226) に記録します。
PR公開やビルド成功は実機への適用とは別です。書き込み後には、ZMK Studioの保存設定も含めて
実際の割り当てを確認してください。確認のためにペアリング情報を消去しないでください。

## 基本操作

位置名は通常レイヤーの文字、番号は0始まりです。

| 位置 | タップ／通常操作 | 保持中 |
| --- | --- | --- |
| 左親指、Space左 (37) | IME切替＋MOUSE解除（押下時） | Shift兼用なし |
| Z (22) | z | 約200msでShift。単独保持の解放後は200msの1打猶予 |
| Space (38) | Space | NUM |
| 左親指、Space右・旧Tab (39) | 変換（INT_HENKAN） | NAV、離すと解除 |
| 右親指Backspace (40) | Backspace | FUNCTION中だけDelete |
| 右親指Enter (41) | Enter | FUNCTION |
| 右下Esc (42) | Esc | SYSTEM |
| U (6) | 通常層ではU | MOUSE_HOLD。マウス中は押下から保持 |
| N (29) | N | 通常のNリピート。スクロール兼用なし |
| M (30) | 通常層ではM | SCROLL。マウス中は押下から有効 |
| P直下の引用符キー (21) | 通常層では `'` | 通常層からもSLOW。マウス操作中は押下から有効 |
| H左隣の `-` (16) | 普通の `-` | スクロール兼用を撤去 |

**Nのスクロール役割をM位置へ移しました。文字のN/Mは交換していません。**
Mの旧MOUSE_HOLD入口は撤去し、Uを通常速度の手動入口にします。
U/M/引用符、Space/変換/Esc/Enterは標準layer-tapの200ms・tap-preferred判定を使います。
タップは文字等、ホールドは各レイヤーです。マウス中のU/M/引用符は標準 `&mo` で即時保持します。
左親指IMEは押下でIMEを切り替える専用キーです。ShiftやSYSTEMには入りません。

保持解除はそのレイヤーだけを外し、ほかの保持状態やIME送信順をリセットしません。
解放後の**新しい押下**が残ったレイヤーで解決されます。既に押下中のキーを途中で別のHIDキーに
変換する動作ではありません。通常U保持はMOUSE_HOLD、M保持はSCROLL、引用符保持はSLOWです。

Ctrl・GUI (Win/Command)・Altの専用キーは維持しています。
H/I/Nは通常層で普通の文字キーです。Zは下記のShift兼用です。削除コンボは追加していません。
右親指のBackspaceはタップ／ホールド兼用にせず、押しっぱなしの連続削除を使えます。
DeleteはEnterのFUNCTIONを保持して同じBackspace位置を押します。

### ShiftとZ

**ShiftはZ位置(22)に集約し、親指37のShift兼用は撤去しています。**
通常層でZを200ms未満で離すとz、約200ms保持するとShiftです（tap-preferred）。
別キーを押しただけでは長押しへ早期確定せず、保持中は通常のShiftとして使います。

**Zを単独で長押しして離した後は、200msだけ次の1打を待ちます。**
その間にZを押し直せばShift+Z、AならShift+Aです。次の非修飾キー押下で猶予を使い切り、
何も入力しなければ期限で解除します。2文字目を巻き込まないようquick-releaseを使用します。
Z保持中に既に文字や矢印へShiftを使った場合は、Z解放で解除し、猶予を残しません。
Ctrl/GUI/Altの押下だけは猶予を消費せず、Ctrl+Shift+Z等と組み合わせられます。

```text
z:        Zを短く押して離す
Shift+A:  Zを約200ms保持し、そのままAを押す
Shift+Z:  Zを単独で約200ms以上保持 → 離す → 200ms以内にZを押し直す
```

長押し判定の200msと、解放後の200msは別の設定です。Shiftが有効な間のZはmod-morphで
長押し再判定を通さず文字入力へ進み、keep-modsでShiftを隠しません。quick-releaseなので、
猶予を消費した後も押し続けたキーのリピートがすべて大文字になるとは保証しません。
200msちょうどの境界やUSB/BLE/ホスト処理の遅延は実機確認が必要です。

マウス中も同じZ長押しを使い、**Shift保持だけでは自動MOUSEを解除しません**。
Zの文字入力が確定した分岐だけが自動MOUSEをOFFにしてZを送ります。手動U/M/SLOWは残します。
自動MOUSE自体の1秒期限は延長しないので、長いShift+クリック操作にはU保持を併用します。
Sticky Keyが使用済みかを判断する対象はキーボードのキーコードです。クリックだけにShiftを
使った場合は、解放後に200msの猶予が残る点に注意してください。

実装は標準hold-tap、sticky-key、mod-morphと2つの押下/解放マクロです。独自Cタイマーはありません。
採用版hold-tapは解放にも最初の押下時刻を渡すため、そのままsticky-keyへつなぐと
猶予の期限が古い時刻になります。`shift_hold`を標準behavior queueへ通して実行時刻を渡し、
解放処理から200msを測ります。キューが他のマクロを待つ場合、その配送分の遅延は残ります。
`z_tap`も固定時間のキー連打ではなく、実際の押下/解放を転送します。

NUM中はZ位置の「0/Shift」（既存balanced判定）、NAV中は同位置の専用Shiftを維持しています。
これらには新しい解放後猶予を追加していません。範囲選択はHENKAN/NAVを保持してから
Z位置のShiftとHJKLを使い、Shift+Tabには既存のD+Fコンボも使えます。

根拠: [ZMK Hold-Tap](https://zmk.dev/docs/keymaps/behaviors/hold-tap)、
[Sticky Key](https://zmk.dev/docs/keymaps/behaviors/sticky-key)、
[Mod-Morph](https://zmk.dev/docs/keymaps/behaviors/mod-morph)、
[採用版behavior queue](https://github.com/zmkfirmware/zmk/blob/acfd8e5ea76cf23ad1c9b6b99848f97a95224257/app/src/behavior_queue.c)。

### 左親指の変換とTab

**旧Tab位置(39)のタップは、専用の変換キー `INT_HENKAN` です。保持NAVは残します。**
Spaceによる代用はしません。親指38のSpace/NUMと、親指37のLANG切替専用キーとは別の入力です。
短く押して離したときにHENKANを送り、200msの保持判定が成立するとNAVへ入り、HENKANは送りません。
そのため、この兼用キーを押し続けてHENKANをリピートする使い方にはなりません。
実際の変換・再変換はホストOS・IME・再割り当て設定に依存し、macOS/Karabinerを含む実機では未検証です。
JIS記号の出力成功だけでは、専用HENKANの対応まで確認したことにはなりません。Spaceへの自動代替も行いません。

Tabは既存のS+D、Shift+TabはD+Fに残ります。J+Kは変換やマウス入口ではなく、下記の中クリックです。

根拠: [Macの日本語入力](https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10265/6.3/mac/26)、
[Microsoft日本語IME](https://support.microsoft.com/ja-jp/windows/hardware/input-devices/microsoft-japanese-ime)。

## 時間条件と操作の有効範囲

値は初期調整値のままです。設定時間は入力判定の基準であり、OSまでの応答時間の保証ではありません。
採用ZMK `acfd8e5` の標準定義・処理と、このリポジトリの本番Cを照合しています。

| 対象 | 時間条件 | 何が有効になるか・終わるか |
| --- | --- | --- |
| 通常U/M/引用符、Space/変換/Enter/Esc | layer-tap、200ms、tap-preferred | 短い解放でU/M/引用符/Space/HENKAN/Enter/Esc。保持判定で各レイヤー。別キーの押下だけでは早期holdしない |
| 通常ZのShift | 200ms、tap-preferred、quick-tap=0 | 保持でShift。単独保持の解放処理から200msだけ次の1打を待ち、1打で解除 |
| 親指37のIME | 長押し判定なし | 押下時にLANG切替。保持でShiftへ変化しない |
| NUMの0/Shift | 200ms、balanced、quick-tap=0 | 200ms保持、または他キーを押して離すまで0を保持するとShift。単なる他キー押下だけでは未決定 |
| マウス中U/M/引用符 | `mo`、長押し判定なし | 押下で保持開始、解放でその層だけ終了。自動MOUSEの期限から独立 |
| 全6コンボ | 1キー目から2キー目まで50ms未満 | J+K中クリック、S+D Tab、D+F Shift+Tab、A+S解除、L+引用符、C+V。slow-releaseなし。中ボタンは片方の構成キー解放で解放 |
| 自動MOUSEへの入口 | 非ゼロXYの継続200ms以上、報告間隔80ms以下、最後のキーコード押下から300ms以上 | 新しいXY報告が条件を満たすと有効化を要求。200msと300msは加算する待ち時間ではない |
| 自動MOUSEの保持 | 最後に受理した非ゼロXYから1000ms | 最新期限で解除。I/OやJ/Kの押下、クリック、スクロール報告では延長しない |
| LANGマクロの送信 | wait-ms=0、tap時間は標準30ms | 親指37の押下でLANGを1回送る。Zの200ms判定とは独立 |

**使い方と境界上の注意**

- **HENKANを長く押すとNAVです。** 変換候補の連打は短いタップで行います。U/M/引用符/Space/Enter/Escも、
  そのキーを長押しして文字をリピートする配置ではありません。通常N/Backspaceはこの200ms判定を持ちません。Zは上記のShift兼用です。
- **Shift+ZはZの単独長押し→解放→200ms以内の押し直し**です。親指37はIME専用です。
  一方、Uを短く押してIを重ね、200ms未満でUを離す操作は、マウスが別途有効でなければ通常のU/I入力です。
- **300msは最後の解放からではありません。** 長い文字キー保持やOSのリピートを追跡しないため、キーを保持したままでも
  300ms経過後の継続XYで自動MOUSEへ入り得ます。A+Sなどキーコードを出さない操作は予約取消し・継続リセットを行いますが、
  idle時計は更新しません。直後の新しい200msの継続XYで再び有効になる場合があります。
- **SLOWを離しても自動MOUSEが残る場合があります。** 自動入口を抑止するのはUのMOUSE_HOLDです。
  SLOWだけの保持中はXYで自動MOUSEも有効になり得ます。SCROLL報告自体は自動期限を延長せず、手動SCROLLは解放まで残ります。
- **クリックを続けても1秒は更新されません。** ボールを止めて操作を続ける場合はU保持の手動層を使います。
  自動層が外れた後の新しいI/O押下は文字側になります。既に押下済みのキー／コンボの解放とは分けて考えます。
- **コンボは「常に現在層を再確認」ではありません。** 1キー目で最高位層から候補を作り、2キー目は位置と期限で絞ります。
  その50ms未満の間に自動MOUSEが外れても候補が残り、中クリックが成立し得ます。成立後は構成キー解放まで管理されます。
  数値を長くするだけでは、この層変化をまたぐ性質はなくなりません。
- **境界ちょうどを狙わないでください。** この版のコンボは差が50msなら失効します。hold-tapは解放時の補正が`>200ms`なので、
  ちょうど200msの解放はタイマー処理との順序に依存します。自動側の200/80/300ms境界は本番Cで検査していますが、
  work実行・入力配送・USB/BLE・ホスト処理の遅延まで一定時間に制限するものではありません。

根拠: [採用版hold-tap](https://github.com/zmkfirmware/zmk/blob/acfd8e5ea76cf23ad1c9b6b99848f97a95224257/app/src/behaviors/behavior_hold_tap.c)、
[採用版combo](https://github.com/zmkfirmware/zmk/blob/acfd8e5ea76cf23ad1c9b6b99848f97a95224257/app/src/combo.c)、
[自動所有](src/motion_dwell.c)、[継続時間述語](src/motion_dwell.h)。
これらはソース・本番Cの順序制御モデルに基づく監査です。実機のhold-tap/コンボ/HID/IME結果は未検証で、
この監査を理由に時間値やマウスの実行コードを変更していません。再現条件と観測は追跡Issue #226に記録します。

## MOUSE / MOUSE_HOLD / SCROLL / SLOW

| 位置 | マウス操作中の出力 |
| --- | --- |
| Y / P | Ctrl+C / Ctrl+V |
| U | 保持でMOUSE_HOLD |
| **I / O** | **左／右クリック (MB1/MB2)** |
| **J＋K** | **ホイール（中）クリック (MB3)** |
| **M / P直下の引用符キー(21)** | **保持でSCROLL／保持でSLOW** |

**自動切替と、次の手動入口があります。**

- **自動**：非ゼロのXY移動が200ms以上続き、最後のキーコード入力から300ms以上経過した場合。
  移動報告の間隔が80msを超えると最初から数え直します。触れて止めたあと、待つだけでは入りません。
- **U保持**：通常層のU(6)を200ms保持してMOUSE_HOLDへ入ります。ボール操作は不要です。
  短いタップはU。マウス中のUは押下から保持できます。MからMOUSE_HOLDには入りません。
- **低速保持**：P直下の引用符(21)を通常層から200ms保持するとSLOWへ入り、離すとSLOWだけ解除します。
  短いタップはJISのシングルクォート。Mと組み合わせると低速スクロールです。

自動MOUSEは最後の非ゼロXY入力から1000msで解除します。MOUSE_HOLDはタイムアウトせず、
Uを離すとそのレイヤーだけ解除します。自動タイマーと所有を分けているので、U保持を自動期限が壊しません。
MOUSE_HOLD中は自動MOUSEを新規有効化・延長しません。
すでに自動MOUSEが残っていた場合、Uを離した後はその残り時間に従います。

**Uを保持したままIを押すと左クリックでき、I保持＋ボール操作でドラッグできます。**
旧Uクリック・Mへの持ち替え操作は不要です。MOUSE_HOLDの入口はUだけなので、保持数を数える
独自shared_moは撤去し、標準lt/moに揃えています。SLOW/SCROLLは別の保持です。
SLOWを離しても、自動MOUSE等が残っていればその状態へ戻ります。

通常状態からMを保持すれば直接SCROLLにも入れます。M→引用符でも引用符→Mでも低速スクロールです。
NUMのU/引用符/N/Mは&/%/[/]、NAVのUは無入力、FUNCTIONではF2/F10/F11/F12を維持します。
Nはマウス中も文字入力に戻れるキーで、スクロールを開始しません。

### J＋Kの中クリック

マウス層（MOUSE/MOUSE_HOLD/SLOW/SCROLL）でJ(18)とK(19)を50ms未満の間隔で同時押しすると
中ボタンを押下します。**どちらか一方を離すと中ボタンを解放**する標準コンボです。
両キーを離すまで保持する `slow-release` や固定トグルは使いません。
マウス中のJ/K単独は `&none` で、コンボ不成立時に文字を漏らしません。
生のJ/K押下で先に自動MOUSEが解除されないよう、両位置を解除除外に含めています。

通常層のJ/Kは普通の文字、NAVのJ/Kは下／上矢印です。
NUM/NAV/FUNCTION/SYSTEMが最高位のときはこのコンボを発動させません。
コンボ・hold-tapの実際のイベント順序と押し心地は実機確認が必要です。

根拠: [ZMK Combos](https://zmk.dev/docs/keymaps/combos)。

200/80/300msは実機調整用の初期値です。動きの連続性はセンサーの移動報告で判定し、手の接触や
使用者の意図を直接検知しません。キーを長く保持している状態やホスト側キーリピートは、
最後のキーコード押下時刻だけでは追跡できません。カーソル移動自体は抑止しません。
Mac画面操作ショートカットは追加していません。

| 保持中 | ボールの動作 |
| --- | --- |
| なし | 通常カーソル移動 |
| P直下の引用符キー | 低速カーソル移動 |
| M | 通常スクロール |
| M＋P直下の引用符キー | 低速スクロール |

MOUSE中からMとP直下キーをどちらの順で押しても組み合わせられます。
両方保持した状態からP直下キーだけ離すと通常スクロール、Mだけ離すと低速カーソル移動へ戻ります。
MOUSEがタイムアウトしても、保持中SCROLL/SLOWのI/OクリックやM・P直下キーの入口は文字に落ちません。
4つのレイヤーのbindingsは `POINTING_BINDINGS` を共有し、内容を二重管理しません。

低速倍率は入力移動量の **1/4** です。`trackball_listener` のSLOW overrideでZMK標準の
`zip_xy_scaler 1 4` と `zip_scroll_scaler 1 4` を使い、通常のCPI・OS設定は変更しません。
XYと縦横ホイールそれぞれの端数を標準実装が保持します。小さい入力を毎回捨てる設定ではありません。
端数はキーを離すと消す独自処理を追加せず、標準scalerのまま次の低速入力へ持ち越します。

既存PMW3610のSNIPEとSCROLLは排他的なので、SNIPEは使いません。
SLOWをSCROLLより下位に置き、listenerはSLOWが**有効かどうか**で倍率を選びます。
このためSCROLL中にも低速が効き、低速キーを押すことでスクロールがカーソル移動へ化けません。
NUMのN/Mは角括弧、FUNCTIONのN/MはF11/F12を維持します。P直下キーもNUMでは%、
NAVでは引用符、FUNCTIONではF10が優先します（別途SCROLLを保持した場合はポインティング優先）。
L+引用符のダブルクォートコンボはBASE/IME_ALT限定とし、MOUSE/SLOWで低速ホールドを奪わないようにしています。

倍率は画面上の速度の厳密な1/4を保証しません。OS加速やアプリのスクロール処理も影響します。
スクロールは既存ドライバの整数ホイールイベントを縮小するため、同方向では概ね4イベントごとに
1イベントを出す方式です。高解像度の滑らかなスクロールを新設したわけではありません。
クリックは押している間ボタンを保持し、ドラッグに使えます。

根拠: [ZMK scaler](https://zmk.dev/docs/keymaps/input-processors/scaler)、
[採用ZMKのscaler定義](https://github.com/zmkfirmware/zmk/blob/v0.3-branch/app/dts/input/processors/scaler.dtsi)、
[listenerの有効層判定](https://github.com/zmkfirmware/zmk/blob/v0.3-branch/app/src/pointing/input_listener.c)。

### キータップで文字入力へ戻る

通常の文字・記号、Space/変換/Tab/Enter/Backspace等を押すと**自動MOUSEだけ**を解除します。
最初のキーイベントも後続へ渡し、解除のためだけに1打を捨てる方式にはしません。
生押下で解除しない位置はYUIOP(5–9)、中クリックJ/K(18/19)、低速21、Z/Shift22、スクロールM30、Ctrl/GUI/Alt(34–36)です。
ZはShift保持では解除せず、文字入力の分岐で自動MOUSEを解除します。親指37は押下でMOUSE解除＋LANG入力を実行します。
A＋Sの明示解除も残し、入力言語やLANG送信順を変えません。H/L/Nは通常文字なので解除対象です。
MOUSE中のYUIOP・J/K・M・引用符から文字入力を始める場合は、まず明示解除するかタイムアウトを待ちます。

NUM/NAV/FUNCTION/SYSTEMやIME送信順は消しません。保持中のMOUSE_HOLD/SCROLL/SLOWも残るため、
文字入力に完全に戻る際はU/M/低速の保持を離してください。全層を消す `&to 0` は使いません。

自動MOUSEの継続判定・入力休止・取消し・保持期限は [motion_dwell.c](src/motion_dwell.c) が一括管理します。
PMW3610側の `automouse-layer=0` と、不要になったドライバの自動設定の撤去は維持します。
標準 `zip_temp_layer` への委譲は廃止し、自動制御を二重に動かしません。
速度変換・手動保持・hold-tap・コンボの判定はZMK標準です。

遅延処理は過去のON/OFF要求をキューに積まず、1つのZephyr delayable workで**現在の要求と最新の期限**を確認します。
生押下による解除対象キーは、既に有効な自動MOUSEだけでなく、まだ実行していない有効化要求も取り消します。
Zは判定後の文字キーコードで保留要求も取り消すため、長押し未確定中の生押下は取消し対象ではありません。
有効化する時点でも入力休止とMOUSE_HOLDを確認し、取消し後に時間だけが経過しても復活させません。
古いタイムアウト処理が残っていても、ボール操作で延長された最新期限より前なら解除せず、残り時間に再設定します。
状態確認と変更は同じ再入可能なmutex内で行い、同期的なレイヤー通知にも対応します。

コンボやhold-tapが押下を捕捉する前に取消しを処理するため、CMakeでこのlistenerを `app` の先頭側へ登録します。
A＋Sのように文字キーコードを送らない操作でも予約を取り消せます。キーイベントそのものは消費しません。
移動が途切れたとき、キーコード押下時、レイヤー変化時に継続判定をやり直します。
低速overrideも同じ入口をスケーラーの前に通し、1000msはkeymapの `AUTOMOUSE_PROCESSOR` に一度だけ定義します。
時間値200/80/300/1000msとレイヤー番号は維持し、解除除外は今回のクリック／スクロール位置に合わせています。

根拠: [Zephyr Work Queues](https://docs.zephyrproject.org/latest/kernel/services/threads/workqueue.html)。
再スケジュールしても既にキューに入ったworkは取り消されないため、取消しフラグと最新期限を実行時の判断基準にします。

### ターミナルでのCtrl+C/V

Y/Pは「ターミナルではマウスを使わない」という利用方針でCtrl+C/Vを維持します。
生のCtrl+CがTTYへ届けば通常はSIGINTで前景ジョブを中断し、Ctrl+Vもzshの標準Emacs編集では
quoted-insertで、貼り付けとは限りません。端末へ移った直後はA＋SでMOUSEを解除し、U/MとP直下の低速キーも離します。
WezTerm標準のクリップボード操作はCtrl+Shift+C/V（macOSではCommand+C/Vも）ですが、
全GUIアプリへそのまま適用できるわけではありません。Ctrl/Commandの自動変換はしていません。

根拠: [TTY特殊文字](https://sourceware.org/glibc/manual/latest/html_node/Special-Characters.html)、
[zsh](https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html)、
[WezTerm](https://wezterm.org/config/default-keys.html)。

## NAV / FUNCTION

**左親指のSpace右(39)は、タップで専用変換（HENKAN）、ホールド中だけNAVです。**
Space/NUM(38)は変更していません。NAV入口は `&lt L_NAV INT_HENKAN` で、標準layer-tapの
200ms・tap-preferred判定を使います。即時の `&mo` ではないため、矢印操作はホールド判定後に行います。
保持が成立した後は離してもHENKANを送らず、NAVだけを解除します。
NAV中のH/J/K/Lは左/下/上/右です。
Y/U/I/O/Pは `&none` で、文字も下位MOUSE/NUMの操作も送りません。
Home/End、Ctrl+Tab、Ctrl+Shift+Tab、GUI+Shift+左右矢印、エンコーダーのCtrl+PageUp/PageDownは維持。
NAVを離すと残ったレイヤーの割り当てへ戻ります。

FUNCTIONはEnterホールド中だけです。

```text
通常の位置:  Y    U    I    O    P
FUNCTION:   F1   F2   F3   F4   F5

通常の位置:  H    J    K    L    '
FUNCTION:   F6   F7   F8   F9  F10

通常の位置:  N    M    ,    .    /
FUNCTION:  F11  F12  F13   透過  透過

右親指Backspace (40): Delete
右下 (42): Esc / 保持でSYSTEM
```

Fnを離すと右親指(40)はBackspaceへ戻ります。NUMを同時に保持していた場合、N/M/COMMAはNUMの括弧へ戻ります。
SCROLLを別途保持している間は、U保持・I/OクリックとM・P直下キーのポインティング操作をFUNCTIONより優先します。

## SYSTEM：右手に集約

**右下Esc (42) はタップEsc、ホールド中だけSYSTEMです。**
右親指(40)はBackspace専用へ交換し、FUNCTION中の同じ位置でDeleteを出します。
Escと一緒にSYSTEM入口を右下へ移したため、Backspaceの長押しは設定操作になりません。
左親指IMEは専用キーで、ShiftやSYSTEMには入りません。設定への入口を含め右手側に集約しています。

| SYSTEM中の右手位置 | 動作 |
| --- | --- |
| Y/U/I/O/P | Bluetoothプロファイル0/1/2/3/4を選択 |
| H/J/K | 既存の数字1/2/3送信（旧X/C/Vから移設） |
| N左隣 (28) | bootloader |
| `.` (32) | **全Bluetoothペアリング情報を消去** |
| `/` (33) | 選択プロファイルのペアリング情報を消去 |

数字1/2/3は普通のキー送信で、CPI設定などの新機能ではありません。
SYSTEMの左手位置には専用の設定割り当てを置かず透過にします。
Escのタップ／ホールド判定が加わるので、通常の即時Escとは操作感が変わります。
SYSTEMからの戻りはEscキーを離すだけで、IME送信順や他の保持レイヤーをリセットしません。
**bootloaderとペアリング消去は通常入力ではありません。検証のために実行しないでください。**

## NUM：数字とShift記号

数字の並びはテンキー型のまま、送信はテンキー用 `KP_NUMBER_*` ではなく通常の
数字列 `NUMBER_0`〜`NUMBER_9` です。NUMはSpaceホールド、ShiftはZ位置のホールドを使います。
NUM中のZ位置はタップ0／ホールドShiftのままです。

```text
物理位置:  W E R    S D F    X C V    Z
NUM数字:   7 8 9    4 5 6    1 2 3    0（保持はShift）
```

**数字も専用記号も、JISとして認識するホストに合わせています。**
半角・ローマ字入力でのShift数字は次の対応です。

```text
数字:        1  2  3  4  5  6  7  8  9
Shift記号:   !  "  #  $  %  &  '  (  )
```

0とShiftは同じ物理キーなので、そのキーだけでShift+0は押せません。
JISの閉じ丸括弧はShift+9、または専用のNUM+Pを使えます。
NUMのG右隣(15)にあるCtrl+Alt+テンキー0は別の既存ショートカットとして維持します。

## 記号：JISのShift組合せ

NUMはSpaceホールド、NUM中のShiftはZ位置のホールドです。
**NUM+Jで@、NUM+Shift+Jでバッククォート**を出します。バッククォート用の新キーは追加しません。
表はホストがJIS配列として解釈し、半角入力している場合の対応です。

| 操作位置 | Shiftなし | Shiftあり |
| --- | --- | --- |
| NUM + J | `@` | バッククォート（U+0060） |
| NUM + Y | `^` | `~` |
| NUM + N / M | `[` / `]` | `{` / `}` |
| 通常のB右隣(27) | `:` | `*` |
| 通常のN左隣(28) | `;` | `+` |
| 通常のH左隣(16)、またはNUM + Q | `-` | `=` |
| NUM + `/` | バックスラッシュ（U+005C） | `_` |
| 通常の`,` / `.` | `,` / `.` | `<` / `>` |
| 通常の`/`、またはNUM + A | `/` | `?` |

括弧などの専用配置は維持します。NUM+O/Pは丸括弧、NUM+`,`/`.`は波括弧、
NUM+Iはチルダ、NUM+N左隣(28)はパイプ、NUM+H左隣(16)はアンダースコアです。
**通常の右端引用符キー(21)はJISのShift+7によるシングルクォート**です。
Shiftを追加してもダブルクォートにはなりません。ダブルクォートはNUM+Shift+2位置(C)、
またはBASE/IME_ALTでL+引用符コンボを使って出します。C+Vの等号コンボもJISのShift+MINUSへ変換済みです。

ZMK標準の記号名はUSのHID位置が基準なので、JISで異なるものだけをkeymap冒頭の
`JP_*` にまとめています。BASE/NUM/NAVと記号コンボはこの別名を参照します。
バックスラッシュは円キーではなく `INT_RO`、パイプはShift+`INT_YEN`を使います。
記号用の新しいbehavior、実行時のOS判定、Shift反転処理は追加せず、ホストの通常のShift処理を使います。

NUMはMOUSE/MOUSE_HOLD/SLOWより上なので、括弧はクリックや低速に化けません。
**IMEの日本語ON/OFFとJIS配列認識は別条件です。** Windows/macOSともroBaをJISとして
解釈する設定を前提とし、この変更でPC設定そのものは変更しません。USとして認識すると
記号は一致しません。IMEのかな入力や全角入力、ホストの再割り当ても別条件です。

根拠: [採用ZMKのキー定義](https://github.com/zmkfirmware/zmk/blob/v0.3-branch/app/include/dt-bindings/zmk/keys.h)、
[QMKのJIS HID対応表](https://github.com/qmk/qmk_firmware/blob/master/quantum/keymap_extras/keymap_japanese.h)、
[ZMKのホスト配列の説明](https://zmk.dev/blog/2024/01/05/zmk-tools)。
QMKは対応表の照合だけに用い、QMKのコードや依存は取り込みません。

実機ではシェルでなく空のエディタで、通常／マウス直後／解除後に次を確認します。
`@` とShift+`@`、NUMの角括弧とShiftによる波括弧、通常の`;`/`:`とShift時の`+`/`*`も比較します。

```text
0123456789 !"#$%&'() @` ^~ :; () [] {} <> ' " \ | _ - = +
std::vector<int> v; f(x[i], {a, b});
```

ホスト上の実際の文字出力、特にバックスラッシュ（U+005C）と円記号（U+00A5）の区別は
実機で未確認です。フォントの見た目だけでなく文字コードも照合してください。

## LANG交互送信とレイヤー順序

左親指IME (37) はタップごとにLANG1 → LANG2 → LANG1 → … を送ります。初回はLANG1です。
Z位置のShiftホールドではLANGを送らず、送信順も変更しません。
Windowsの対応する日本語Microsoft IMEでLANG1=ImeOn、LANG2=ImeOff、Mac日本語入力でかな／英数です。
IME切替操作ではCtrl+Space・LANG5・変換／無変換は送りません。親指39の専用HENKAN送信とは独立しています。
別IMEや再割り当てツールは実機確認が必要です。

BASEの37は `&ime_toggle LANG1`、IME_ALTの37は `&ime_toggle LANG2`。
押下で既存のマクロを直接呼び、保持判定やShift兼用はありません。
そのマクロがMOUSEだけをOFFにし、IME_ALTの送信順ビットを反転し、渡されたLANGを1回送ります。
IME_ALTの残り42位置とsensorは透過です。IME処理には独自Cコード・OS検出・永続化を追加していません。

**覚えるのはroBaの送信順であり、PCの現在のIME状態ではありません。**
他の入力機器や画面操作、アプリごとの状態、接続先変更、再起動後には、既に有効なモードを
再指定する場合があります。全接続先共通の状態で、再起動で初期化します。起動時にLANGは送信しません。
実機では同じキーを4回タップして往復を確認し、ZのShiftホールド、EscのSYSTEMホールド、変換/NAV、A＋SではLANGが出ないことを確認します。

```text
BASE0 < IME_ALT1 < MOUSE2 < MOUSE_HOLD3 < SLOW4 < NUM5 < NAV6 < FUNCTION7 < SCROLL8 < SYSTEM9
```

番号はkeymapの定義・レイヤー順・trackball・listenerで合わせています。
SYSTEMを保持中は管理操作が最優先です。S+D=Tab、D+F=Shift+Tab、A+S=MOUSE解除、
C+V=等号はBASE/IME_ALT/MOUSE/MOUSE_HOLD/SLOWに限定します。L+引用符=ダブルクォートはBASE/IME_ALT限定です。
J+K=中クリックはMOUSE/MOUSE_HOLD/SLOW/SCROLL限定で、上位NUM/NAV/FUNCTION/SYSTEMの入力を奪いません。

今回の配置修正ではレイヤー番号を変えていません。
ZMK Studioの保存済みkeymapがある場合は内容を控え、Z22・親指37・HENKAN39を含む新しいstockと照合してください。
撤去したime_shiftやshared_moを使う保存設定をそのまま残さないでください。settings_resetやペアリング消去を自動実行しません。

根拠: [MicrosoftのLANG対応](https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/keyboard-japan-ime)、
[ZMK LANGキー](https://zmk.dev/docs/keymaps/list-of-keycodes#language)、
[レイヤー](https://zmk.dev/docs/keymaps/behaviors/layers)、[マクロ](https://zmk.dev/docs/keymaps/behaviors/macros)。

## ファームウェア更新時に書き込む側

**キー割り当てだけの変更は、通常は右手の `roBa_R-seeeduino_xiao_ble-zmk.uf2` だけを書き込めば反映されます。**
このroBaでは [Kconfig.defconfig](boards/shields/roBa/Kconfig.defconfig) が右側を
`ZMK_SPLIT_ROLE_CENTRAL=y` にしており、左手のキーも右側でキーマップ処理します。
左親指の変換やShiftの変更だから左側だけを更新する、という意味ではありません。

初回導入、左右通信仕様やZMKバージョンを変える更新、左右それぞれのハードウェア設定変更では
左右に対応したファームウェアを更新してください。キー割り当ての変更とは区別します。
通常更新に `settings_reset` は使いません。ZMK Studioの保存済み配置がある場合は、
ビルドしたstock keymapと実際の割り当てを照合してください。

根拠: [ZMK Split Keyboards](https://zmk.dev/docs/features/split-keyboards#building-and-flashing-firmware)。

## 検証と描画

既存の構造回帰はPython 3と `cpp` で実行します。継続時間の境界は同じ入口からCコンパイラ `cc` で
[本番の判定関数](src/motion_dwell.h)を直接コンパイル・実行します（`CC`で指定可能）。
同じ入口から [予約・期限の回帰テスト](tests/bug/temp_layer_pending.py) も実行します。
このテストは本番 `motion_dwell.c` を書き換えずコンパイルし、Zephyrの周辺APIだけを順序制御モデルへ置換します。
POSIXスレッドの再入可能mutexとUndefinedBehaviorSanitizerに対応するCコンパイラが必要です。

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q tests
```

10層×43位置、全512層集合、Z長押しと1打猶予、親指IME専用化、変換/NAV、LANG送信順、NAV上段の無入力、MとP直下キーの組合せと解放順、MOUSEタイムアウト時の
参照先、Iクリック・J+K中クリックの層制限、XY/scroll scaler設定、設定操作の右手集約、JISの記号・Shift・Fキーを検査します。
**キーマップ検査はマクロを展開する静的モデルです。時間判定のCテストも、ZMKヘッダ・実HID・タイマー・ホストの出力・
物理的な操作感を検証するものではありません。** 実機の速度・スクロール量・連打・解放順は未検証です。

予約・期限のテストでは、打鍵後の予約取消し、古い期限後の延長、手動保持、全43位置の除外判定など19項目を確認します。
単独実行は `python3 tests/bug/temp_layer_pending.py` です。実際のZephyrスケジューラやHIDを実行する試験ではありません。
以前の上流ソース専用の不具合再現はGit履歴に残し、現在のテストは修正後の本番経路を対象とします。
廃止した共有保持behaviorの専用テストは撤去し、UだけがMOUSE_HOLDへ入ることを配置テストで確認します。

正規firmware buildは [.github/workflows/build.yml](.github/workflows/build.yml)、図は既存の
[Draw Keymap](.github/workflows/draw.yml)です。keymap/配置JSON/描画設定の入力変更をpushすると、
同じブランチへ `keymap-drawer/roBa.{yaml,svg}` を生成・コミットします。
`keymap_drawer.config.yaml` の標準 `raw_binding_map` でJISの記号とShift側、変換/NAVを表示します。
別名はkeymapと同じプリプロセッサで解決するため、US名の誤ったラベルを表示しません。
生成物自体は入力トリガーではなく、描画を再帰起動しません。別の生成経路や手編集した図は追加しません。
成功したSHA、実行結果と検証限界はIssue/PRで追跡できます。
