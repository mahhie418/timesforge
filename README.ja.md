# timesforge

[English](README.en.md)

timesforge は、Slack のワークスペースのメンバーが、自分専用の公開チャンネル `#times_<ファーストネーム>` (times チャンネル) を作れるようにします。times チャンネルには、好きなことを自由に投稿できます。メンバーは timesforge の App Home から自分で作成し、timesforge がワークスペースのほかのメンバーを招待します。Slack のフリープランでも使えます。

timesforge は、あなたのコンピューターで、ワークスペース内だけで使う Slack app として動きます。Slack とは Socket Mode でつながるので外部に公開する URL は要らず、通信先は Slack だけです。

## できること

- **App Home からの作成**: メンバーが Slack で timesforge を開いてファーストネームを入力すると、timesforge が裏でチャンネルを作成し、ワークスペースのメンバーを招待します。名前がすでに使われていなければ、誰の承認も待たずに作成されます。
- **歓迎のメッセージ**: times チャンネルをまだ持っていないメンバーが #welcome などの歓迎用チャンネルに参加すると、bot が App Home へのリンクを付けた DM を 1 回だけ送ります。times チャンネルができると、そのメッセージはチャンネルへのリンクに書き換わります。
- **1 人 1 回**: times チャンネルを作成できるのは、原則 1 人 1 回です。削除しても作成権は戻りませんが、オーナーがもう 1 回作成できるようにできます。
- **オーナーは 1 人**: オーナーは App Home で、使われている名前の代わりを決めたり、メンバーを作成対象から外したり、再作成権を与えたり、取り込んだチャンネルの保持者を直したり、履歴を見たりできます。
- **Slack に合わせた表示**: Slack で times チャンネルをアーカイブ、アーカイブ解除、名前の変更、削除すると、App Home の表示もそれに従います。timesforge より前にメンバーが手で作った times チャンネルは、取り込めます。

## 必要なもの

- macOS か Windows。Linux でも動きますが、setup でログイン時の自動起動は登録できません。
- [uv](https://docs.astral.sh/uv/) (timesforge と、その実行に必要な Python をインストールします)。
- Slack app を作成してインストールできるワークスペース。公開チャンネルを作れるのが管理者だけのワークスペースでは、管理者がインストールします。

## インストール

```sh
uv tool install timesforge
```

## 初期設定

```sh
timesforge setup
```

setup は次の 4 つの段階を順に案内し、入力した内容を設定ファイルに保存します。

1. **Slack app**: setup が表示するリンクを開いて Slack app を作成します。設定は manifest から自動で入力されます。表示される手順に従って進め、Bot User OAuth Token と App-Level Token を貼り付けます。公開チャンネルを作れるのが管理者だけのワークスペースでは、管理者が Slack app をインストールし、User OAuth Token も貼り付けます。それ以外のワークスペースでは、User OAuth Token は空のままにします。
2. **オーナー**: timesforge のオーナーにする人のメンバー ID を貼り付けます。メンバー ID は、Slack でその人のプロフィールを開き、⋮ (その他) の「メンバー ID をコピー」でコピーできます。
3. **歓迎用チャンネル**: #welcome など、新しいメンバーが参加するチャンネルのチャンネル ID を貼り付け、そのチャンネルで `/invite @timesforge` を送って bot を追加します。bot がチャンネルに入るまで setup は先に進まないので、追加したら Enter を押して確認し直します。
4. **確認と自動起動**: 設定、トークン、データベース、オーナー、歓迎用チャンネルを確認し、Slack にあって timesforge がまだ知らない times チャンネルを一覧にします。それから、ログイン時に Slack app を自動で起動するかどうかを聞きます。自動で起動しないと答えると、登録済みの自動起動を `timesforge stop` と同じように外します。

設定を変えるときは、setup をもう一度実行します。すでに答えてある質問では、後ろの [ ] に今の値 (トークンでは `keep current`) が表示され、Enter を押すとその値のまま進めます。最初の 3 つの段階を手動で行う方法は [Creating the Slack app](docs/slack.md) にあります (英語)。

## 既存の times チャンネルの取り込み

timesforge より前にメンバーが手で作った times チャンネルがあれば、誰の times チャンネルかを timesforge に伝えるために取り込みます。各チャンネルの ID を、その保持者のメンバー ID に対応させた JSON ファイルを書きます。

```json
{"C0123ABCDEF": "U0123ABCDE", "C0456GHIJKL": "U0456FGHIJ"}
```

それから、ファイルを確認して取り込みます。

```sh
timesforge import --mapping channels.json --dry-run
timesforge import --mapping channels.json --apply
```

`--dry-run` は、各チャンネルを取り込めるかどうかを表示するだけで、何も変えません。`--apply` は、すべてのチャンネルを取り込めるときだけ取り込みます。

## App Home

メンバーは、次のように times チャンネルを作成します。

1. Slack で timesforge を開いてホームタブを表示するか、歓迎のメッセージの「times を作成する」を選択します。
2. 「times チャンネルを作成」を選択し、ファーストネームを A〜Z の英字で入力して「作成」を選択します。
3. チャンネルができると、App Home に表示されます。名前がすでに使われているときは、オーナーが別の名前を決めます。

オーナーには「オーナーの操作」も表示されます。

- **名前の重複**: 「名前を決める」で、名前が使われていたメンバーのチャンネルを別の名前で作成します。
- **作成対象外のメンバー**: 「除外を変更」で、理由を付けてメンバーを times チャンネルの作成対象から外したり、作成対象に戻したりします。
- **再作成権**: 「再作成権を変更」で、times チャンネルが削除されたメンバーが 1 回だけもう一度作成できるようにします。
- **取り込んだチャンネル**: 「確認」で、取り込んだチャンネルの保持者を変更します。
- **履歴**: 「履歴を見る」で、times チャンネルと作成対象の最近の変更を表示します。

誰が times チャンネルを作成でき、誰が招待されるか、オーナーと作成対象外の扱いは [Times channels and who may create them](docs/permissions.md) にあります (英語)。

## 設定

timesforge は、設定フォルダの `timesforge.env` を読み込みます。同じ名前の環境変数があれば、そちらを優先します。

| OS | 設定ファイル | データフォルダ |
|---|---|---|
| macOS | `~/Library/Application Support/timesforge/timesforge.env` | `~/Library/Application Support/timesforge` |
| Windows | `%LOCALAPPDATA%\timesforge\timesforge.env` | `%LOCALAPPDATA%\timesforge` |
| Linux | `~/.config/timesforge/timesforge.env` | `~/.local/share/timesforge` |

| 変数 | 内容 |
|---|---|
| `SLACK_BOT_TOKEN` | Slack app の Bot User OAuth Token (`xoxb-…`) |
| `SLACK_APP_TOKEN` | Slack app の App-Level Token (`xapp-…`) |
| `SLACK_USER_TOKEN` | 管理者の User OAuth Token (`xoxp-…`)。公開チャンネルを作れるのが管理者だけのワークスペースでだけ設定し、times チャンネルはこのトークンで作成します。 |
| `TIMESFORGE_OWNER_ID` | オーナーのメンバー ID |
| `TIMESFORGE_CHANNEL_ID_WELCOME` | #welcome など、新しいメンバーが参加するチャンネルのチャンネル ID |
| `TIMESFORGE_DATA_DIRECTORY` | データベースを置くフォルダ。ローカルディスク上に置いてください。 |
| `TIMESFORGE_LANGUAGE_DISPLAY` | Slack の言語が英語でも日本語でもない人に表示する、App Home と歓迎のメッセージの言語 (`en` または `ja`) |

設定ファイルを変更したら、Slack app を再起動してください。

## コマンド

| コマンド | 内容 |
|---|---|
| `timesforge setup` | Slack app の作成、オーナーと歓迎用チャンネルの設定、ログイン時の自動起動の登録を案内し、設定ファイルに保存します |
| `timesforge start` | 止めるまで Slack app を実行します。`--log FILE` を付けると、出力をファイルに追記します。 |
| `timesforge stop` | Slack app を止めて、ログイン時の自動起動をやめます |
| `timesforge doctor` | 設定、Slack のトークン、データベース、オーナー、歓迎用チャンネルを確認します |
| `timesforge import --mapping FILE --dry-run` | 対応表のファイルにある times チャンネルを取り込めるかどうかを表示します |
| `timesforge import --mapping FILE --apply` | 対応表のファイルにある times チャンネルを、すべて取り込めるときに取り込みます |
| `timesforge manifest` | Slack app を作成するための manifest を表示します |

## timesforge を動かす

App Home、歓迎のメッセージ、times チャンネルの作成は、Slack app が動いている間だけ動作します。setup でログイン時の自動起動を登録した場合は、すでに動いています。エラーで止まったときも自動で再起動し、出力はデータフォルダの `start.log` に書き込まれます。登録していない場合は、`timesforge start` を実行したままにしてください。

Slack app は起動すると、止まっている間に Slack で変わったことを反映し、作成の途中だった times チャンネルを作り終えます。

1 つのワークスペースに対して動かす Slack app は、1 つだけにしてください。同じデータフォルダで 2 つ目を起動しようとすると timesforge が止めますが、2 台のコンピューターで動かすと、Slack がイベントやボタンの操作を両方に振り分けてしまいます。

Slack app を再起動するには (設定ファイルを変更したときなど):

- macOS: `launchctl kickstart -k gui/$(id -u)/timesforge` を実行します。
- Windows: `schtasks /End /TN timesforge` を実行してから、`schtasks /Run /TN timesforge` を実行します。
- 自動起動を使っていない場合: `timesforge start` を Ctrl+C で止めて、もう一度実行します。

Slack app を止めて、ログイン時の自動起動をやめるには、`timesforge stop` を実行します。

## 注意

- Slack では、各 times チャンネルの作成者として、bot か、そのチャンネルを作成したユーザートークンの管理者が表示されます。保持者は timesforge が記録しているので、作成者の表示は関係ありません。その管理者はすべての times チャンネルのメンバーにもなりますが、退出してかまいません。
- 後からワークスペースに参加したメンバーは、既存の times チャンネルには招待されません。参加してもらうには、times チャンネルをワークスペースのデフォルトチャンネルに加えるか、各自で参加してもらってください。
- フリープランでは、Slack は直近 90 日のメッセージしか表示しないので、古い歓迎のメッセージは見えなくなることがあります。times チャンネルを作成できるかどうかは、App Home にいつでも表示されます。
- 設定ファイルには Slack のトークンが含まれます。macOS と Linux では、本人だけが読めるように保存します。
- 誰がどの times チャンネルを持ち、誰が作成できるかの記録は、データフォルダのデータベースにしかありません。バックアップしてください。
