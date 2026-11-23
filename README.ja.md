# Krea2 Photo Prompt Builder for ComfyUI

写真用プロンプトをラベル付きの9項目で組み立て、項目ごとの入力履歴をローカルのSQLiteデータベースに保存するComfyUIカスタムノードです。保存済みPhoto IDを読み込むだけの参照ノードも含みます。

## インストール

Comfy Registryで初回公開した後は、ComfyUI Managerで`photo-prompt-builder`を検索し、**Krea2 Photo Prompt Builder**をインストールできます。

手動でインストールする場合：

1. ZIPを`ComfyUI/custom_nodes/`に展開し、フォルダーが`ComfyUI/custom_nodes/comfyui-photo-prompt-builder/`になるようにします。
2. ComfyUIのPythonサーバーを再起動し、ブラウザーを更新します（必要に応じてCtrl+Shift+R）。
3. `prompt/photo`カテゴリで**Krea2 Photo Prompt Builder**を検索します。
4. `CLIPTextEncode`ノードにテキスト入力ポートがまだない場合は、`text`ウィジェットを右クリックして入力に変換します。このノードの`prompt`出力（STRING）をその入力につなぎます。

ComfyUIに含まれる`aiohttp`以外に、pipでインストールする依存パッケージはありません。

## Comfy Registryへの公開準備

`pyproject.toml`に公開用のメタデータを、`.comfyignore`に公開アーカイブから除外するファイルを指定しています。Registry上のパッケージ名は`photo-prompt-builder`で、ComfyUI内部のノードIDとは別です。現在のプレリリース版は`1.0.0RC2`です。

1. [Comfy Registry](https://registry.comfy.org/)のPublisher ID `magichan`を使用します。`pyproject.toml`の`[tool.comfy].PublisherId`にも同じIDを設定しています。
2. `pyproject.toml`のバージョンとメタデータを確認してください。公開済みのバージョンは変更できないため、次回以降の公開では`version`を更新します。
3. [Comfy CLI](https://docs.comfy.org/comfy-cli/getting-started)をインストールし、リポジトリのルートで`comfy node publish`を実行してください。Registry公開用APIキーの入力を求められます。キーをリポジトリに保存しないでください。

`.comfyignore`はローカルのプロンプト履歴、テスト、プレビュー、Pythonバイトコードを公開アーカイブから除外します。旧JSONがない場合に初期データとして読み込む`data/prompt_history_template.json`は公開アーカイブに含めます。アカウントとキーの作成方法は[公式の公開手順](https://docs.comfy.org/registry/publishing)を参照してください。

ComfyUI内部でのノードIDは`MagichanLab_Krea2PhotoPromptBuilder`と`MagichanLab_Krea2PhotoPromptReference`です。旧IDの`Krea2PhotoPromptBuilder`で保存したワークフローをこのバージョンで読み込むには、ワークフロー内のノードタイプを`MagichanLab_Krea2PhotoPromptBuilder`に変更する必要があります。画面上のビルダーノード名は引き続き**Krea2 Photo Prompt Builder**です。

## 入力項目

**Krea2 Photo Prompt Reference**は`prompt/photo`カテゴリにある参照専用ノードです。保存済みPhoto IDのドロップダウンで参照する組み合わせを選択します。選択したIDに関連する9項目を実行時に共有履歴から読み込み、ビルダーと同じ見出し・順序の`prompt`（STRING）を出力します。CLIPTextEncodeの`text`入力に接続できます。履歴の保存・編集・削除は行いません。Photo IDが未選択、または削除済みの場合は実行エラーになります。新しいIDの候補はノード追加時やビルダーで保存した際に更新されます。

追加先タグのドロップダウンと追加プロンプト（LoRAのトリガーワードなど）の入力欄を横一行に配置しています。9項目から追加先を選ぶと、実行時にその項目の末尾へ改行で追記します。元の項目が空でも追加でき、入力欄が空の場合は元のプロンプトをそのまま出力します。追加内容は共有履歴やPhoto IDには保存されません。

参照ノードでは、ドロップダウンの下に検索欄とPhoto ID・画像例を並べた一覧も表示します。IDの一部を入力すると、ドロップダウンと一覧の候補が大文字・小文字を区別せず即時に絞られます。検索だけでは選択済みIDは変わりません。画像をクリックしてもIDを選択できます。画像例を使うには、`data/images/`フォルダーを作り、`photo-1`なら`data/images/photo-1.jpg`または`photo-1.png`のように保存してください。対応形式はPNG、JPG、JPEG、WebP、GIFです。同じIDで複数形式がある場合はこの順で1枚を表示します。画像のないIDも選択できます。`/`を含むPhoto IDはファイル名にできないため画像例を表示できません。画像はブラウザー上で縮小表示され、元ファイルは変更されません。個人の画像が公開パッケージに入らないよう、このフォルダーはGitとComfy Registryの公開対象から除外しています。

以下は**Krea2 Photo Prompt Builder**の入力項目です。

- `subject`：人数、年齢、性別、民族的背景、容姿、体格
- `appearance`（Clothing）：服装、アクセサリー
- `hair_makeup`（Hair & Makeup）：髪型、メーク
- `pose`（Posing）：ポーズ、しぐさ
- `expression`（Expression）：表情、視線
- `environment`：場所、背景、小道具、時間帯
- `composition`：構図、カメラ位置、レンズ、被写界深度
- `lighting`：光源、光の方向、コントラスト、色温度
- `finishing`：質感、カラーグレーディング、雰囲気、写真のスタイル

各項目には`use_...`切り替えがあります。オフにした項目もワークフローと履歴には残りますが、出力からは除外されます。空欄の項目も出力されません。`auto_save_history`は、このノードの**実行時**に空でない入力を履歴に保存するかを制御します。履歴の保存件数に上限はありません。

既存ワークフローとの互換性のため、`appearance`と`pose`の入力キーは維持しています。以前の入力や履歴に髪型・メーク、表情が含まれる場合は、必要に応じて新しい項目へ移してください。

## 出力例

```text
Subject:
A Japanese woman in her 30s

Clothing:
Casual white shirt

Hair & Makeup:
Black hair

Composition & Camera:
Medium shot, eye-level, 50mm lens
```

見出しと段落の間隔は固定です。出力は通常の`STRING`で、CLIPテキストエンコーダーの`text`入力に接続できます。モデル、CLIP、サンプラーはこのノードに含まれません。

## 履歴UI

各タグの履歴リストは、Photo IDが紐付いている履歴を緑、紐付いていない履歴をグレーで表示します。ダイアログ内の凡例で色の意味を確認でき、選択中も文字色と左枠で区別できます。

- 通常の複数行テキスト欄で直接編集できます。
- 各入力欄の右側にある「履歴」ボタンをクリックするとダイアログが開き、リストから履歴を選択できます。100件ずつ読み込み、`Previous page` / `Next page`で前後のページへ移動できます。選択した値の全文確認、適用、個別の削除、項目ごとの履歴の全削除ができます。
- ノード下部の1行目にはPhoto ID検索欄、`Select Photo ID`、`Rename`、`Delete`、2行目には保存用Photo ID入力、`Save`、`Preview`を配置しています。
- `Save`をクリックすると、`auto_save_history`がオフでも現在の値をすぐに保存できます。
- 手動保存時は現在の有効な非空欄に共通のPhoto IDを付けます。`photo_id`入力が空欄なら保存時刻の`yymmddHHMMSS`、入力があればその値を使います。使用できる文字は英数字と`!#$%*+-./:;=?@_~`で、最大24文字です。
- Photo IDはドロップダウンに自然な昇順で表示されます。検索欄に入力すると、大文字・小文字を区別せず、入力文字列を含むIDだけに候補が即時に絞られます。検索欄を空にすると全件に戻ります。
- ノード上の`Select Photo ID`ドロップダウンで保存済みIDを選ぶと、関連する文字列を各項目に復元します。該当する文字列がない項目は空欄かつ未使用になります。選択したIDは`photo_id`入力にも入り、そのまま保存すると同じIDの組み合わせを更新できます。検索欄は候補の絞り込み専用で、保存用Photo ID入力には影響しません。
- 1つの文字列に複数のPhoto IDを付けられます。同じPhoto IDを再保存すると、そのIDの以前の関連付けを新しい組み合わせで置き換えます。手動保存で未使用にした項目の文字列も通常の履歴には残りますが、そのPhoto IDには関連付けません。
- 同じPhoto IDが同一項目の別の文字列に付いている場合は、該当項目を示す確認ダイアログが出ます。承認すると上書きし、キャンセルすると保存しません。同じ文字列への再保存や重複しない項目だけの変更では確認は出ません。
- `Rename`は選択したPhoto IDを全項目で一括変更します。ダイアログで新しいIDを入力して`OK`で確定、`Cancel`で中止します。空欄、使用できない文字、既存IDはエラーになります。
- `Delete`は選択したPhoto IDだけを全項目から削除します。文字列履歴と現在ノードに表示中の各項目の文字列は残り、選択欄は未選択になります。
- `Preview`をクリックすると、サンプラーを実行せずに生成されるプロンプトを確認・コピーできます。
- 重複する値は取り除かれ、最後に保存した値が先頭に表示されます。履歴は9項目それぞれ独立しています。
- 履歴は削除するまで件数に関係なく保持されます。履歴から文字列を削除・全削除すると、関連するPhoto IDからもその項目が外れます。
- **履歴は同じComfyUI環境にあるすべてのビルダーノードで共有されます。** 現在の入力値と切り替え状態は、各ComfyUIワークフローにも保存されます。

## 保存場所とバックアップ

履歴は`ComfyUI/custom_nodes/comfyui-photo-prompt-builder/data/prompt_history.sqlite3`に保存されます。Python標準のSQLiteを使用するため、依存パッケージの追加は不要です。本文・項目・項目別履歴・Photo IDの対応を別テーブルに正規化し、一意制約と外部キーで重複や関連付けの不整合を防ぎます。履歴の新着順取得、本文検索、Photo ID検索にインデックスを使用します。履歴画面はカーソル方式で100件ずつ読み込み、自動保存は対象レコードのみを書き込みます。参照ノードも選択したIDの組み合わせだけを読み込みます。APIのDB処理はComfyUIのイベントループ外で実行します。Photo ID選択欄は引き続き全組み合わせを取得するため、Photo IDが非常に多い場合は初期読み込みに時間がかかる可能性があります。

DBと`-wal` / `-shm`ファイルはGit管理・公開アーカイブから除外します。ComfyUI実行中のバックアップには、下記のJSON Exportを使用してください。ファイルを直接コピーする場合は、ComfyUIとほかのDB利用プロセスを停止してから`data`ディレクトリをコピーしてください。再インストール前にもバックアップしてください。

### 既存JSONからの自動移行

初回のDBアクセス時に`data/prompt_history.json`があれば、トランザクション内で自動移行します。文字列配列のバージョン1とPhoto ID付きのバージョン2に対応し、表示順と関連付けを引き継ぎます。元のJSONは変更せずに残します。移行後はSQLiteを使用し、履歴を全削除してもJSONを再移行しません。旧JSONがなければ`data/prompt_history_template.json`を初期データにします。不正なJSONの場合は移行を中断し、不完全なDBを確定しません。元データを修正して再実行できます。

ComfyUIの起動前に手動で移行する場合は、リポジトリのルートで以下を実行します。

```sh
python migrate_history.py
# パスを明示する場合：
python migrate_history.py --source /path/to/prompt_history.json --database /path/to/prompt_history.sqlite3
```

繰り返し実行しても初期化済みDBは上書きしません。パス指定はスクリプトの実行時だけに適用され、ノードは常に`data/prompt_history.sqlite3`を使用します。`history_limit`欄は廃止し、件数超過による自動削除も行いません。更新前のビルダーワークフローを開いた場合もPhoto IDを引き継ぎます。

### JSON の Export / Import（GUI不要）

ComfyUIを起動した状態で、以下をターミナルから実行できます。Exportファイルには9項目の履歴とPhoto IDの関連付けがすべて含まれます。

```sh
curl -fS http://127.0.0.1:8188/magichanlab_photo_prompt/history/export -o photo-prompt-history.json
curl -fS -X POST -H 'Content-Type: application/json' --data-binary @photo-prompt-history.json http://127.0.0.1:8188/magichanlab_photo_prompt/history/import
```

**Importは現在の共有履歴を丸ごと置き換えます。** 実行前にExportでバックアップしてください。Importが受け付けるのは、このノードのバージョン2の履歴JSON形式です。不正な形式はエラーになり、既存の履歴は変更されません。Import後はComfyUIのブラウザー画面を更新し、Photo IDの一覧を読み直してください。別のポートでComfyUIを起動している場合はURLの`8188`を変更してください。

旧バージョンからの初回更新では、これまでGit管理されていた`prompt_history.json`をリポジトリ外にコピーしてから、`git restore data/prompt_history.json`、`git pull`の順に実行し、SQLiteへの初回アクセス前にバックアップを`data/prompt_history.json`へ戻してください。以後の更新は通常どおり`git pull`できます。

**Google Colab**：Colabの一時的な実行環境では、ランタイムをリセットするとローカルの履歴が削除されます。履歴を残すには、JSON ExportをGoogle Drive上の永続ストレージに保存し、リセット後にImportしてください。稼働中のSQLiteはローカルのランタイム領域に置いてください。Driveのマウント先ではSQLiteに必要なファイルロックが保証されない場合があります。このプロジェクトはDriveを自動でマウントしません。

## 注意事項と制限

- 履歴は各入力欄の右側のボタンから開くダイアログにリスト表示されます。入力値はComfyUI標準のウィジェットに保存されます。
- 生成時の自動保存は、このビルダーのPythonノードが実際に実行された場合にのみ行われます。キャッシュが使われた場合など、ノードが実行されなければ履歴は更新されません。その場合は手動保存を使用してください。
- 自動保存はPhoto IDを付けません。写真の組み合わせを残すには手動保存ボタンを押してください。同じ秒にデフォルトIDで再保存すると同一IDが更新されます。
- ノードの入力は`CONDITIONING`ではなく`STRING`です。後段には対応するテキストエンコーダーを使用してください。
- JavaScript UIは、ComfyUIの従来のLiteGraph `addWidget`連携を使用しています。バックエンドは追加のUI操作機能がなくても動作します。将来のバージョンやNodes 2.0専用ビルドではフロントエンドの動作が変わる可能性があるため、使用するComfyUIのバージョンで確認してください。
- このノードは信頼できるComfyUI環境でのみ使用してください。他のローカルComfyUIデータと同様に、ComfyUIのHTTP APIにアクセスできる人は共有履歴を読み書きできます。

## テスト

リポジトリのルートから`python -m unittest discover -s tests -v`を実行します。フロントエンドのアダプター検証は`node tests/test_frontend.mjs`で実行できます。

## ComfyUIなしでUIを確認する

このリポジトリのルートで`python3 -m http.server 8000`を実行し、ブラウザーで`http://localhost:8000/preview/`を開きます。プレビューは実際のフロントエンドJavaScriptを読み込み、ComfyUIのノードと履歴APIをブラウザー内で模擬します。履歴はブラウザーのローカルストレージに保存されます。

これはボタン配置とダイアログ操作を確認するための画面です。ComfyUI上の描画、ワークフローへの保存、Python側の実行結果は確認できません。

## ライセンス

このプロジェクトはMITライセンスで公開されています。詳しくは[LICENSE](LICENSE)を参照してください。
