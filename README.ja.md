# Krea2 Photo Prompt Builder for ComfyUI

写真用プロンプトをラベル付きの9項目で組み立て、項目ごとの入力履歴をローカルのJSONファイルに保存するComfyUIカスタムノードです。

## インストール

1. ZIPを`ComfyUI/custom_nodes/`に展開し、フォルダーが`ComfyUI/custom_nodes/comfyui-photo-prompt-builder/`になるようにします。
2. ComfyUIのPythonサーバーを再起動し、ブラウザーを更新します（必要に応じてCtrl+Shift+R）。
3. `prompt/photo`カテゴリで**Krea2 Photo Prompt Builder**を検索します。
4. `CLIPTextEncode`ノードにテキスト入力ポートがまだない場合は、`text`ウィジェットを右クリックして入力に変換します。このノードの`prompt`出力（STRING）をその入力につなぎます。

ComfyUIに含まれる`aiohttp`以外に、pipでインストールする依存パッケージはありません。

ComfyUI内部でのノードIDは`MagichanLab_Krea2PhotoPromptBuilder`です。旧IDの`Krea2PhotoPromptBuilder`で保存したワークフローをこのバージョンで読み込むには、ワークフロー内のノードタイプを新しいIDに変更する必要があります。画面上のノード名は引き続き**Krea2 Photo Prompt Builder**です。

## 入力項目

- `subject`：人数、年齢、性別、民族的背景、容姿、体格
- `appearance`（Clothing）：服装、アクセサリー
- `hair_makeup`（Hair & Makeup）：髪型、メーク
- `pose`（Posing）：ポーズ、しぐさ
- `expression`（Expression）：表情、視線
- `environment`：場所、背景、小道具、時間帯
- `composition`：構図、カメラ位置、レンズ、被写界深度
- `lighting`：光源、光の方向、コントラスト、色温度
- `finishing`：質感、カラーグレーディング、雰囲気、写真のスタイル

各項目には`use_...`切り替えがあります。オフにした項目もワークフローと履歴には残りますが、出力からは除外されます。空欄の項目も出力されません。`auto_save_history`は、このノードの**実行時**に空でない入力を履歴に保存するかを制御します。`history_limit`の初期値は各項目100件です。

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

- 通常の複数行テキスト欄で直接編集できます。
- `History: <section> ▾`をクリックすると履歴のドロップダウンが開き、全文の確認、値の適用、個別の削除、項目ごとの履歴の全削除ができます。
- `Save current values to history`をクリックすると、`auto_save_history`がオフでも現在の値をすぐに保存できます。
- `Preview combined prompt`をクリックすると、サンプラーを実行せずに生成されるプロンプトを確認・コピーできます。
- 重複する値は取り除かれ、最後に保存した値が先頭に表示されます。履歴は9項目それぞれ独立しています。
- **履歴は同じComfyUI環境にあるすべてのビルダーノードで共有されます。** 現在の入力値と切り替え状態は、各ComfyUIワークフローにも保存されます。

## 保存場所とバックアップ

履歴は`ComfyUI/custom_nodes/comfyui-photo-prompt-builder/data/prompt_history.json`に保存されます。人が読めるUTF-8形式で、ファイルの置き換えはアトミックに行われます。カスタムノードを再インストールまたは更新する前に、このファイルをバックアップしてください。

**Google Colab**：Colabの一時的な実行環境では、ランタイムをリセットするとローカルの履歴が削除されます。履歴を残すには、`data`ディレクトリをGoogle Drive上の永続ストレージにバックアップするか、シンボリックリンクを作成してください。このプロジェクトはDriveを自動でマウントしません。

## 注意事項と制限

- 履歴メニューは、常時表示されるコンボウィジェットではなく、ノード内のボタンから開くドロップダウンです。これにより、ComfyUI標準の入力ウィジェットのシリアライズへの影響を避けています。
- 生成時の自動保存は、このビルダーのPythonノードが実際に実行された場合にのみ行われます。キャッシュが使われた場合など、ノードが実行されなければ履歴は更新されません。その場合は手動保存を使用してください。
- ノードの入力は`CONDITIONING`ではなく`STRING`です。後段には対応するテキストエンコーダーを使用してください。
- JavaScript UIは、ComfyUIの従来のLiteGraph `addWidget`連携を使用しています。バックエンドは追加のUI操作機能がなくても動作します。将来のバージョンやNodes 2.0専用ビルドではフロントエンドの動作が変わる可能性があるため、使用するComfyUIのバージョンで確認してください。
- このノードは信頼できるComfyUI環境でのみ使用してください。他のローカルComfyUIデータと同様に、ComfyUIのHTTP APIにアクセスできる人は共有履歴を読み書きできます。

## テスト

プロジェクトの親ディレクトリから`python -m unittest discover -s comfyui-photo-prompt-builder/tests -v`を実行します。

## ライセンス

このプロジェクトはMITライセンスで公開されています。詳しくは[LICENSE](LICENSE)を参照してください。
