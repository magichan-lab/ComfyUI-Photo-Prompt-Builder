# Krea2 Photo Prompt Builder for ComfyUI

[日本語版 README](README.ja.md)

ComfyUI nodes for building labeled, nine-section photography prompts with local SQLite history and reading saved Photo ID combinations.

## Installation

After the first Comfy Registry release, install **Krea2 Photo Prompt Builder** through ComfyUI Manager by searching for `photo-prompt-builder`.

For manual installation:

1. Extract the ZIP into `ComfyUI/custom_nodes/` so the folder is `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/`.
2. Restart the ComfyUI Python server, and refresh the browser (Ctrl+Shift+R if needed).
3. Search for **Krea2 Photo Prompt Builder** under `prompt/photo`.
4. Right-click the `text` widget of your `CLIPTextEncode` node and convert it to an input, if the text input port is not already available. Connect the builder's `prompt` output (STRING) to that input.

No pip dependencies beyond ComfyUI's own `aiohttp` are required.

## Comfy Registry publishing

The repository includes `pyproject.toml` metadata and a `.comfyignore` release filter. The Registry package name is `photo-prompt-builder` (distinct from the internal node IDs). The current prerelease version is `1.0.0RC3`.

1. Use the `magichan` publisher at [Comfy Registry](https://registry.comfy.org/). The same ID is set in `[tool.comfy].PublisherId` in `pyproject.toml`.
2. Review the version and metadata in `pyproject.toml`. Increment `version` for each later release; a published version cannot be changed.
3. Install [Comfy CLI](https://docs.comfy.org/comfy-cli/getting-started), then run `comfy node publish` from the repository root. The CLI asks for a Registry publishing API key. Do not commit the key.

The `.comfyignore` file excludes the local prompt history, test files, preview, and Python bytecode from the Registry archive. Keep `data/prompt_history_template.json` in the package because it seeds new databases when no legacy JSON exists. See the [official publishing guide](https://docs.comfy.org/registry/publishing) for account and key setup.

The internal ComfyUI node IDs are `MagichanLab_Krea2PhotoPromptBuilder` and `MagichanLab_Krea2PhotoPromptReference`. Workflows saved with the earlier builder ID `Krea2PhotoPromptBuilder` need their node type changed to `MagichanLab_Krea2PhotoPromptBuilder` before loading this version. The displayed builder name remains **Krea2 Photo Prompt Builder**.

## Inputs

**Krea2 Photo Prompt Reference**, under `prompt/photo`, has a Photo ID dropdown to select a saved combination. It reads the selected combination from shared history when executed and outputs the same labeled `prompt` (STRING) as the builder, ready for a CLIP text encoder's `text` input. It never saves or edits history. Running without a selected Photo ID, or with a deleted ID, raises an error. The dropdown refreshes when the node is added or the builder saves a Photo ID.

A tag dropdown and an additional prompt input (for example, LoRA trigger words) appear side by side. Choose one of the nine sections to append the text on a new line at execution time, including sections absent from the saved combination. A blank input leaves the output unchanged. Additions are never written to shared history or Photo IDs.

The reference node also shows a search field and a gallery of Photo IDs with example thumbnails below the dropdown. Typing part of an ID immediately filters the dropdown and gallery without changing the selected ID; matching is case-insensitive. Click an image to select its ID. After saving a Photo ID, generating an image connected to that builder automatically saves the first output image as a PNG thumbnail at `data/images/(Photo ID).png` when generation completes. Thumbnails fit within 256×256 pixels and are updated only when the effective prompt fields used for generation match the saved Photo ID fields. Editing a recalled prompt without saving it to the same ID leaves the existing thumbnail unchanged. Automatically assigned IDs are filled into the builder input after saving. You can also add images manually, such as `data/images/photo-1.jpg`. PNG, JPG, JPEG, WebP, and GIF are supported, in that order when multiple formats exist. IDs without images remain selectable. IDs containing filename-forbidden characters (`/\\:*?"<>|`) cannot be saved as thumbnails. Images are scaled in the browser without modifying the source files. `data/images/` is excluded from Git and Registry packages so local example images are not published.

The following inputs belong to **Krea2 Photo Prompt Builder**.

- `subject`: number, age, gender, ethnic background, appearance, build
- `appearance` (Clothing): clothing, accessories
- `hair_makeup` (Hair & Makeup): hairstyle, makeup
- `pose` (Posing): pose, gesture
- `expression` (Expression): expression, gaze
- `environment`: location, background, props, time
- `composition`: framing, camera position, lens, depth of field
- `lighting`: light source, direction, contrast, color temperature
- `finishing`: texture, color grade, mood, photo style

Each section is included when its local text is nonempty. Connecting an external node to a section automatically excludes that section from the combined prompt and disables its local editor while connected. Blank sections are omitted. The `auto_save_history` toggle controls saving nonempty local values **when this node executes**. History has no retention limit.

The `appearance` and `pose` input keys remain unchanged for existing workflows. If older inputs or history entries contain hair, makeup, or expression details, move those details into the new fields as needed.

## Output example

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

Headings and paragraph spacing are fixed. Output is plain `STRING`, compatible with the CLIP text encoder's `text` input. Model, CLIP and sampler are not provided.

## History UI

- Use the native multiline text fields for direct editing.
- Click the `履歴` button to the right of an input field to open a dialog with a selectable history list. Entries linked to a Photo ID appear in green; unlinked entries appear in gray, with a legend explaining the colors. Text and left border colors remain visible when selected. Use Previous page / Next page to browse 100 entries at a time. Inspect the full text, apply a value, delete one value, or clear that section's history.
- The node's lower controls use two rows: Photo ID search / `Select Photo ID` / `Rename` / `Delete`, then the Photo ID input for saving / `Save` / `Preview`.
- Click `Save` to save immediately (even when `auto_save_history` is off).
- Manual save assigns one Photo ID to all enabled, nonempty fields. Leave the `photo_id` input blank to use the save time in `yymmddHHMMSS` format, or enter up to 24 letters, digits, and `!#$%*+-./:;=?@_~` characters.
- Photo IDs appear in natural ascending order. Type in the search box to immediately filter IDs by a case-insensitive substring; clear it to show all IDs. The search box only filters the dropdown and does not change the Photo ID used for saving.
- Choose an ID from the node's `Select Photo ID` dropdown to restore its saved combination. Fields without that ID become blank and disabled. After changing the recalled content, the selected ID shows `[Edited]` in a different color; reverting or saving clears the marker. Choosing an ID also fills the `photo_id` input, so saving again updates that ID.
- A string can have multiple IDs. Saving an existing ID replaces its earlier associations. Disabled strings remain in ordinary history but receive no ID on that save.
- If an ID is already assigned to different text in the same field, a confirmation dialog lists the affected fields before saving. Cancel leaves the saved combination unchanged. Reusing the same text or adding fields without a conflict needs no confirmation.
- `Rename` changes the selected ID across all fields. The dialog accepts a new ID or can be canceled; blank, invalid, or already used IDs are rejected.
- `Delete` removes the selected ID from all fields while keeping the history strings and current text fields. The selector returns to its unselected state.
- Click `Preview` to inspect/copy the generated prompt without running the sampler.
- Duplicate values are removed, and the most recently saved entry appears first. Histories are independent for all nine categories.
- All strings are retained until deleted. Deleting or clearing history removes the affected fields from their Photo IDs.
- **History is shared by all builder nodes in the same ComfyUI installation.** Current values and external node connections are also saved in each ComfyUI workflow.

## Storage and backup

The history lives at `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/data/prompt_history.sqlite3`, using Python's built-in SQLite support with no additional dependencies. Texts, fields, field history, and Photo ID assignments are normalized into separate tables. Unique keys prevent duplicates; foreign keys keep assignments consistent. Indexes support recent-history pages, text lookup, and Photo ID lookup. History dialogs load 100 entries per page using a cursor rather than loading all history. Autosave writes only the affected rows, and the reference node reads only the selected combination. API database operations run outside ComfyUI's event loop. Photo ID selectors still load all saved combinations, so very large Photo ID collections can increase their initial load time.

The database and its `-wal` / `-shm` sidecars are excluded from Git and release archives. Use JSON export below for a consistent backup while ComfyUI is running. For a file backup, stop ComfyUI and other database users before copying the `data` directory. Back up before reinstalling the custom node.

### Automatic migration from JSON

On first database access, existing `data/prompt_history.json` is automatically imported in one transaction. Version 1 string histories and version 2 histories with Photo ID assignments are supported; history order and associations are preserved. The source JSON is retained unchanged. Once initialized, SQLite is authoritative and the JSON is never reimported, including after history is cleared. Without legacy JSON, `data/prompt_history_template.json` seeds the database. Invalid JSON fails migration without committing a partial database; correct the source and retry.

To migrate before starting ComfyUI, run from this repository's root:

```sh
python migrate_history.py
# Optional explicit paths:
python migrate_history.py --source /path/to/prompt_history.json --database /path/to/prompt_history.sqlite3
```

The script preserves initialized databases on repeat runs. Custom paths apply to that script invocation only; the node always uses `data/prompt_history.sqlite3`. The removed `history_limit` setting no longer truncates history. Existing builder workflows restore their Photo ID when loaded after the update.

### JSON export and import without the GUI

With ComfyUI running, use these commands in a terminal. The export includes all nine history sections and their Photo ID associations.

```sh
curl -fS http://127.0.0.1:8188/magichanlab_photo_prompt/history/export -o photo-prompt-history.json
curl -fS -X POST -H 'Content-Type: application/json' --data-binary @photo-prompt-history.json http://127.0.0.1:8188/magichanlab_photo_prompt/history/import
```

**Import replaces the entire shared history.** Export a backup before importing. The endpoint accepts this node's version 2 history JSON format. Invalid data is rejected without changing the existing history. Refresh the ComfyUI browser page after import to reload the Photo ID list. Replace port `8188` if your ComfyUI server uses another port.

For the first update from an older checkout that still tracks `prompt_history.json`, copy it outside the repository, run `git restore data/prompt_history.json` and `git pull`, then copy the backup back to `data/prompt_history.json` before the first SQLite access. Later updates can use `git pull` directly.

**Google Colab**: Colab's ephemeral runtime deletes the local history when the runtime is reset. To retain it, export a JSON backup to persistent Google Drive storage and restore it after a reset. Keep the live SQLite database on local runtime storage; mounted Drive may not provide the file locking SQLite needs. This project does not automatically mount Drive.

## Notes and limitations

- Each input field has a history button on its right. The dialog shows history as a list, while ComfyUI's built-in widget retains the input value for workflow serialization.
- Generation-triggered autosave runs only when the builder's Python node executes. Cached/unexecuted runs do not update the history; use the manual save action.
- Autosave does not assign Photo IDs. Use manual save to preserve a combination. Two default saves within the same second update the same ID.
- The built-in node inputs are `STRING`, not `CONDITIONING`; use a compatible text encoder downstream.
- The JavaScript UI uses ComfyUI's classic LiteGraph `addWidget` integration. The backend works independently of the extra controls. Frontend behavior may vary in future / Nodes 2.0-only builds; test on the ComfyUI version in use.
- Use this node only on trusted ComfyUI instances: anyone with access to the ComfyUI HTTP API can read/change the shared history, like other local ComfyUI data.

## Tests

From this repository's root: `python -m unittest discover -s tests -v`. Frontend adapter checks: `node tests/test_frontend.mjs`.

## Preview without ComfyUI

Run `python3 -m http.server 8000` from this repository's root, then open `http://localhost:8000/preview/`. The preview loads the actual frontend JavaScript and mocks the ComfyUI node and history API in the browser. Preview history is stored in browser local storage.

This checks button placement and dialog interactions. It does not verify ComfyUI rendering, workflow serialization, or Python node execution.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
