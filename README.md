# zmk-config-roBa

<img src="keymap-drawer/roBa.svg" alt="roBa keymap">

`iwashita-nozomu/zmk-config-roBa` の個人用配置です。
配置の正本は [config/roBa.keymap](config/roBa.keymap) です。
[追跡Issue #226](https://github.com/iwashita-nozomu/project_template/issues/226) に
変更理由・検証結果・未解決事項を記録します。ファームウェアを実機へ書き込むまでは、
この配置が実機で有効になったとは限りません。ZMK Studioで保存した設定がある場合も
ビルド時のkeymapと異なる可能性があるため、書き込み後に実際の割り当てを確認してください。

## 基本操作

位置名は通常レイヤーの文字、位置番号は0始まりです。

| 位置 | 通常 | レイヤー保持中 |
| --- | --- | --- |
| 右親指内側、旧Backspace (40) | Esc | Escを維持 |
| 右下、旧Delete (42) | Backspace | FUNCTION中だけDelete。NAV/NUM中はBackspace |
| Enter (41) | タップでEnter | ホールド中はFUNCTION |
| NAV、旧無変換 (39) | 文字・IME入力なし | 押した瞬間からNAV、離すと解除 |
| Space (38) | タップでSpace | ホールド中はNUM |
| 半角／全角切替、旧変換 (37) | タップでMOUSE解除＋LANG1/LANG2を交互送信 | ホールド中はSYSTEM |
| H左隣の `-` (16) | タップで `-` | ホールド中はSCROLL |

左親指はSpaceを挟んで、左が半角／全角切替 (37)、右が専用NAV (39) です。
**Ctrl+Spaceは送信しません。補完用の設定を変更せず、LANG1/LANG2を交互に送ります。**
送信順の状態とホストのIME状態の違いは、下記「半角／全角切替と送信順」を参照してください。

IME・Space・Enter・通常の位置16はlayer-tapなのでタップ／ホールドの判定があります。
NAVの位置39とMOUSE/NAV/FUNCTIONの位置16は、押した瞬間から有効になるmomentaryです。
いずれも保持を離すと対象レイヤーだけを解除し、他の有効レイヤーをリセットしません。
解除後の新規押下は、その時点の有効レイヤーで解決します。すでに押したキーを、
途中から別のHIDキーへ変換するという意味ではありません。

Backspace/Deleteの追加コンボはありません。Ctrl・GUI (Win/Command)・Altの専用キー、
Z/ShiftとNUMの0/Shiftは従来のままです。H/Iは通常の文字キーです。

## NAV

左親指の位置39を押している間、右手ホーム段のH/J/K/Lを左/下/上/右にします。
入口は `&mo L_NAV` なので長押し判定を待たず、離すとNAVだけが解除されます。
旧E/S/D/Fの矢印割り当ては外しました。左側のHome/End、Ctrl+Tab、
Ctrl+Shift+Tab、GUI+Shift+左右矢印、エンコーダーのCtrl+PageUp/PageDownは維持します。
NAVのY/U/I/O/Pは明示的な文字入力で、自動MOUSEが残っていてもコピー／クリックに化けません。

## MOUSE / SCROLL

| 位置 | MOUSEとSCROLLで共通の出力 |
| --- | --- |
| Y | Ctrl+C |
| U | 左クリック (MB1) |
| I | 中クリック (MB3) |
| O | 右クリック (MB2) |
| P | Ctrl+V |

MOUSE中はH左隣を保持してトラックボールを動かすとスクロールします。
通常時は同じ位置のホールドで入れます。HJKLとは位置が重なりません。
SCROLLにも同じ上段bindingsを展開するため、MOUSEがタイムアウトした後や、
通常レイヤーから直接SCROLLへ入った場合も、UIOが文字へ落ちません。
押しっぱなしのクリックはボタン保持として使います。

SCROLL中はY/U/I/O/Pの操作をFUNCTIONなどより優先します。
SCROLLを離すと、残っているFUNCTION/NAV/NUM/MOUSEなどへ戻ります。
SYSTEM中は管理操作が最優先で、位置16は通常の `-` です。

### キータップで文字入力へ戻る

**左親指のIMEキー (37) をタップすると、MOUSEを解除し、LANG1またはLANG2を1回送ります。**
同時に次回の送信先を反転します。
入力言語を変えずに戻るには、BASE/IME_ALT/MOUSE中のA+Sを押します。A+SはMOUSE解除だけで、
キー入力を送らず、LANG1/LANG2の送信順も変更しません。
MOUSEが既にOFFならOFFのままです。IMEキーのホールドはSYSTEMへの一時アクセスで、
MOUSE解除・IME入力・送信順反転のタップ処理は実行しません。専用NAV (39) はIME入力を送りません。

ZMK標準のoff-only layer behaviorとmacro/hold-tapの合成で実現しています。
`&to 0`のように、同時に保持しているNUM/NAV/FUNCTION/SCROLLを消す処理ではありません。
ほかのレイヤーがなければ、解除後の新規Y/U/I/O/Pは文字へ戻ります。
SCROLL保持中はMOUSEを解除してもSCROLLのクリックが残るので、文字入力へ戻る際は
SCROLLも離してください。再びボールを動かすと自動MOUSEに入ります。

任意の文字キー・クリックで自動解除する機能は追加していません。
右親指Escは通常のEscのままです。解除キーでOSのIME状態を必ず変更できるという保証と、
ファームウェア内のMOUSE解除は別です。LANGキーの対応条件と送信順の制約は下記を参照してください。

### ターミナルでのCtrl+C/Vに注意

Y/Pの出力は生のCtrl+C/Vであり、汎用のコピー／貼り付け命令ではありません。
Ctrl+CがTTYへ届くと、通常は前景ジョブへのSIGINTになり、コピーしたつもりで
実行中の処理を中断する可能性があります。Ctrl+Vも、zshの標準emacs編集では
次の文字をそのまま挿入するquoted-insertで、貼り付けではありません。

WezTerm標準のクリップボード操作はCtrl+Shift+C/V（macOSではCommand+C/Vも使用可能）です。
ただしこの組み合わせをすべてのGUIアプリへ送ればよいわけではありません。
Y/Pは「ターミナルではマウスを使わない」という利用方針に合わせ、Ctrl+C/Vを維持します。
ターミナルへ移った直後にMOUSEが残っている場合は、A+Sで解除してから入力してください。
MOUSE解除だけでは、実際のCtrl+Cショートカットの意味までは変わりません。

根拠: [TTYの特殊文字](https://sourceware.org/glibc/manual/latest/html_node/Special-Characters.html)、
[zsh quoted-insert](https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html)、
[WezTerm標準割り当て](https://wezterm.org/config/default-keys.html)。

## 記号の配置とUS/JIS条件

記号の配置は維持します。表はUS配列としてホストが解釈し、半角入力で余分な修飾キーを
保持していない場合の想定です。NUMの入口はSpaceホールドです。

| 記号 | 操作位置 |
| --- | --- |
| `:` | B右隣 (27)、通常レイヤーの専用キー |
| `;` | N左隣 (28)、通常レイヤーの専用キー |
| `(` / `)` | NUM + O / P |
| `[` / `]` | NUM + N / M |
| `{` / `}` | NUM + `,` / `.` |
| `<` / `>` | 通常のShift + `,` / `.` |
| `'` / `"` | 通常のSQT (21) / Shift+SQT、または既存L+SQTコンボ |
| `\` / `\|` | NUM + `/` / N左隣 (28) |

NUM+N左隣はPIPEで、通常の同じ位置はSEMICOLONです。
NUMは自動MOUSEより上なので、MOUSEが残っていてもNUMのO/Pは括弧です。
FUNCTION中のN/M/COMMAはF11/F12/F13を優先しますが、FUNCTIONだけを離せば
保持中のNUMの角括弧／波括弧へ戻ります。レイヤーは必要なものだけ保持してください。

ZMKの`COLON`や`LEFT_PARENTHESIS`はUnicode文字を直接送る指定ではなく、
US配列を基準としたHIDキーとShiftの組み合わせです（例: COLONはShift+SEMICOLON、
左丸括弧はShift+9）。ホストのUS/JIS認識が違うと、同じ名前でも実際の記号はずれます。
**IMEの日本語ON/OFFと、キーボードのUS/JIS配列設定は別の状態です。**
Windows/macOS両方で想定配列を合わせるか、ホスト配列ごとの変換を別途設計する必要があります。
このPRでホスト配列の自動判定や変換を実装したわけではありません。

定義: [採用ZMKブランチのkeys.h](https://github.com/zmkfirmware/zmk/blob/v0.3-branch/app/include/dt-bindings/zmk/keys.h)。
実機では、まずシェルへ実行しないエディタの空バッファで次を入力して確認します。

```text
: ; () [] {} <> ' " \ | _ - = +
std::vector<int> v; f(x[i], {a, b});
```

この順番を通常状態、MOUSE直後、MOUSE解除後、NUM/FUNCTION解除後で比較します。
シェルのコマンド欄では、誤った貼付やEnterによる実行を伴う試験をしないでください。

## FUNCTION

```text
通常の位置:  Y    U    I    O    P
FUNCTION:   F1   F2   F3   F4   F5

通常の位置:  H    J    K    L    '
FUNCTION:   F6   F7   F8   F9  F10

通常の位置:  N    M    ,    .    /
FUNCTION:  F11  F12  F13   透過  透過

右下 (42): Delete
```

F11は旧 `/` からN、F12は旧右下からM、F13は旧H左隣から `,` へ移しました。
H左隣はFUNCTION中もmomentary SCROLLです。

## 優先順位と既存操作の移設

レイヤー番号の大きい方を優先します。

```text
BASE(0) < IME_ALT(1) < MOUSE(2) < NUM(3) < NAV(4) < FUNCTION(5) < SCROLL(6) < SYSTEM(7)
```

自動MOUSEより手動のNUM/NAV/FUNCTIONを優先します。
同時にNAVとFUNCTIONを保持したときはFUNCTIONのFキーが優先します。
SCROLLはポインティング操作の最上位、SYSTEMは管理用の最上位です。
番号はkeymap冒頭の定義・レイヤー順・trackball設定で揃えています。

NUMの右下にあった `|` はN左隣のキー (28、通常は `;`) へ移しました。
SYSTEMの右下にあった `BT_CLR_ALL` は `.` (32) へ移しました。
SYSTEMの `/` (33) の `BT_CLR` とY〜Pのプロファイル選択は維持します。
**SYSTEM + `.` は全Bluetoothペアリング情報を消去する操作です。**
右下は管理層でも通常はBackspaceで、FUNCTIONを同時に保持した場合だけDeleteです。

既存コンボ（S+D=Tab、D+F=Shift+Tab、A+S=MOUSE解除のみ、L+`'`=`"`、C+V=`=`）は
BASE/IME_ALT/MOUSEに限ります。コンボのlayers判定は最上位有効レイヤーを用いるため、
NAV/FUNCTION/NUM/SCROLL/SYSTEMでは発動しません。矢印やFキーを奪う旧グローバル設定は撤去しました。
IMEタップとA+SのMOUSE解除は維持します。変換／無変換の送信と旧 `&to 0` の全層リセットは残しません。

## 半角／全角切替と送信順

**左親指の1キー (37) のタップごとに、LANG1 → LANG2 → LANG1 → … と送信します。**
LANG1はWindowsのImeOn／Macのかな、LANG2はWindowsのImeOff／Macの英数です。
Ctrl+SpaceやLANG5は使わず、補完用ショートカットの設定変更も不要です。
Windowsは対応バージョンの日本語Microsoft IME、Macは日本語入力でのLANGキー対応を前提とします。
別のIMEやキー再割り当てツールによる挙動は、そのホスト上で確認してください。

### 1ビットの実装

`IME_ALT` の有効／無効だけを送信順の1ビットに使います。

| タップ直前のIME_ALT | 送るキー | タップ後 |
| --- | --- | --- |
| OFF（再起動時の初期状態） | LANG1 | ON |
| ON | LANG2 | OFF |

BASEの位置37は `&lt_ime L_SYSTEM LANG1`、IME_ALTの同位置は
`&lt_ime L_SYSTEM LANG2` です。共通マクロがMOUSEをOFFにし、IME_ALTだけを
反転し、渡されたLANGキーを1回タップします。SYSTEMホールド時はこのマクロを実行しません。
標準のmacro・hold-tap・layer toggleの合成だけで、新しいC behaviorはありません。

IME_ALTの残り42キーは透過、sensor bindingも追加しません。
MOUSEより下位に置くため、IME_ALTが有効でもクリック、スクロール、NAV、FUNCTION、
記号の実効bindingは変わりません。既存コンボもIME_ALTを有効対象に含めています。
MOUSEのタイムアウトやA+SはIME_ALTを変更せず、NAV/FUNCTION等の解放もこのビットを消しません。

### 状態の限界と実機確認

**記憶するのはroBaの送信順であり、PCの現在のIME状態ではありません。**
再起動後の初回はLANG1で、起動時にLANGキーを自動送信することはありません。
別のキーボードや画面操作でIMEを変えた場合、アプリごとに入力モードが違う場合、
または接続先を切り替えた場合、最初のタップが既に有効なモードを指定することがあります。
そのキーがホストに受理されれば以後は交互です。状態は全接続先で共有し、再起動時に初期化します。
接続先別の永続化・OS自動判定・ホスト状態同期は追加しません。

レイヤー番号を1段ずらしているため、ZMK Studioに保存済みのkeymapがある場合は
そのまま混在させないでください。必要な設定を控え、ビルドしたstock keymapとの一致を確認します。
ペアリングまで消すsettings_resetをこの確認のために自動実行することはありません。

実機では余分な修飾を離し、空のエディタで同じキーを4回タップして
日本語／英数の交互指定、SYSTEMホールドで送信順が進まないこと、
NAV保持／解除とA+SがIME入力を送らないことを確認します。
HIDログ上のLANG1/LANG2交互送信と、画面の実際の入力モードは分けて確認してください。
**実機での送信・IME切替は未検証**です。US/JIS記号配列認識も独立の条件です。

根拠: [MicrosoftのImeOn/ImeOff HID対応](https://learn.microsoft.com/en-us/windows-hardware/design/component-guidelines/keyboard-japan-ime)、
[ZMKのLANGキーとmacOS対応](https://zmk.dev/docs/keymaps/list-of-keycodes#language)、
[ZMKレイヤー](https://zmk.dev/docs/keymaps/behaviors/layers)、
[ZMKマクロ](https://zmk.dev/docs/keymaps/behaviors/macros)。

MOUSEのY/PはCtrl+C/Vのままで、macOS向けCommand+C/Vへの自動切替はしません。
Ctrl/Command差の自動吸収、修飾キー再配置は今回の変更には含めません。

## 検証と描画

構造回帰検査はPython 3とCプリプロセッサ `cpp` で実行します。

```sh
python3 -m unittest discover -s tests -v
```

keymap内のマクロだけを展開し、43bindings、位置、優先順位、全128通りのレイヤー集合での
新規押下の参照先、LANG1/LANG2の交互送信・専用NAV、コンボ対象範囲、MOUSE解除の合成、記号配置を検査します。
**ZMKヘッダはこの構造検査では読みません。ファームウェアのコンパイル、Devicetree binding検証、
hold-tapの時間判定、HIDイベント、実機動作を検証するテストではありません。**

正規ファームウェアビルドは既存の [.github/workflows/build.yml](.github/workflows/build.yml)、
図の生成は既存の [.github/workflows/draw.yml](.github/workflows/draw.yml) の
`Draw Keymap` workflowです。keymap・配置JSON・描画設定・描画workflowの変更をpushすると、
同じブランチに `keymap-drawer/roBa.{yaml,svg}` を生成・コミットします。
対象ブランチを指定した手動実行も可能です。入力は `config/roBa.keymap` と
`config/roBa.json` で、図を手編集する別経路は追加していません。
生成図を更新したコミット自身はpush対象の入力パスを変更しないため、描画を再帰起動しません。
現在の検証成否・実行阻害要因はIssue/PRに記録します。
