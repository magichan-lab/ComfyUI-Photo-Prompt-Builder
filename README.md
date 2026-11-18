# Krea2 Photo Prompt Builder for ComfyUI

[日本語版 README](README.ja.md)

A single ComfyUI node that builds a labeled, nine-section photography prompt and keeps category-specific input history in a local JSON file.

## Installation

After the first Comfy Registry release, install **Krea2 Photo Prompt Builder** through ComfyUI Manager by searching for `photo-prompt-builder`.

For manual installation:

1. Extract the ZIP into `ComfyUI/custom_nodes/` so the folder is `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/`.
2. Restart the ComfyUI Python server, and refresh the browser (Ctrl+Shift+R if needed).
3. Search for **Krea2 Photo Prompt Builder** under `prompt/photo`.
4. Right-click the `text` widget of your `CLIPTextEncode` node and convert it to an input, if the text input port is not already available. Connect the builder's `prompt` output (STRING) to that input.

No pip dependencies beyond ComfyUI's own `aiohttp` are required.

## Comfy Registry publishing

The repository includes `pyproject.toml` metadata and a `.comfyignore` release filter. The Registry package name is `photo-prompt-builder` (distinct from the internal node ID). The proposed first Registry version is `0.1.0`.

1. Use the `magichan` publisher at [Comfy Registry](https://registry.comfy.org/). The same ID is set in `[tool.comfy].PublisherId` in `pyproject.toml`.
2. Review the version and metadata in `pyproject.toml`. Increment `version` for each later release; a published version cannot be changed.
3. Install [Comfy CLI](https://docs.comfy.org/comfy-cli/getting-started), then run `comfy node publish` from the repository root. The CLI asks for a Registry publishing API key. Do not commit the key.

The `.comfyignore` file excludes the local prompt history, test files, preview, and Python bytecode from the Registry archive. Keep `data/prompt_history_template.json` in the package because the node reads it before the first save. See the [official publishing guide](https://docs.comfy.org/registry/publishing) for account and key setup.

The internal ComfyUI node ID is `MagichanLab_Krea2PhotoPromptBuilder`. Workflows saved with the earlier ID `Krea2PhotoPromptBuilder` need their node type changed to the new ID before loading this version. The displayed node name remains **Krea2 Photo Prompt Builder**.

## Inputs

- `subject`: number, age, gender, ethnic background, appearance, build
- `appearance` (Clothing): clothing, accessories
- `hair_makeup` (Hair & Makeup): hairstyle, makeup
- `pose` (Posing): pose, gesture
- `expression` (Expression): expression, gaze
- `environment`: location, background, props, time
- `composition`: framing, camera position, lens, depth of field
- `lighting`: light source, direction, contrast, color temperature
- `finishing`: texture, color grade, mood, photo style

Each has a `use_...` toggle. Disabled sections are retained in the workflow and history, but excluded from output. Blank sections are omitted. The `auto_save_history` toggle controls saving nonempty values **when this node executes**; `history_limit` defaults to 100 per field.

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
- Click the `履歴` button to the right of an input field to open a dialog with a selectable history list. Inspect the full text, apply a value, delete one value, or clear that section's history.
- The node's lower controls use two rows: Photo ID search / `Select Photo ID` / `Rename` / `Delete`, then the Photo ID input for saving / `Save` / `Preview`.
- Click `Save` to save immediately (even when `auto_save_history` is off).
- Manual save assigns one Photo ID to all enabled, nonempty fields. Leave the `photo_id` input blank to use the save time in `yymmddHHMMSS` format, or enter up to 24 letters, digits, and `!#$%*+-./:;=?@_~` characters.
- Photo IDs appear in natural ascending order. Type in the search box to immediately filter IDs by a case-insensitive substring; clear it to show all IDs. The search box only filters the dropdown and does not change the Photo ID used for saving.
- Choose an ID from the node's `Select Photo ID` dropdown to restore its saved combination. Fields without that ID become blank and disabled. Choosing an ID also fills the `photo_id` input, so saving again updates that ID.
- A string can have multiple IDs. Saving an existing ID replaces its earlier associations. Disabled strings remain in ordinary history but receive no ID on that save.
- If an ID is already assigned to different text in the same field, a confirmation dialog lists the affected fields before saving. Cancel leaves the saved combination unchanged. Reusing the same text or adding fields without a conflict needs no confirmation.
- `Rename` changes the selected ID across all fields. The dialog accepts a new ID or can be canceled; blank, invalid, or already used IDs are rejected.
- `Delete` removes the selected ID from all fields while keeping the history strings and current text fields. The selector returns to its unselected state.
- Click `Preview` to inspect/copy the generated prompt without running the sampler.
- Duplicate values are removed, and the most recently saved entry appears first. Histories are independent for all nine categories.
- Tagged strings survive `history_limit`. Deleting or clearing history removes the affected fields from their Photo IDs.
- **History is shared by all builder nodes in the same ComfyUI installation.** Current values/toggles are also saved in each ComfyUI workflow.

## Storage and backup

The history lives at `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/data/prompt_history.json`. It is human-readable UTF-8, written using atomic replacement, and excluded from Git. If the file is missing, the node reads the tracked `data/prompt_history_template.json` until history is saved. Back up `prompt_history.json` before reinstalling the custom node.

For the first update from an older checkout that still tracks `prompt_history.json`, copy it outside the repository, run `git restore data/prompt_history.json` and `git pull`, then copy the backup back to `data/prompt_history.json`. Later updates can use `git pull` directly.

**Google Colab**: Colab's ephemeral runtime deletes the local history when the runtime is reset. To retain it, back up or symlink the `data` directory to persistent Google Drive storage. This project does not automatically mount Drive.

## Notes and limitations

- Each input field has a history button on its right. The dialog shows history as a list, while ComfyUI's built-in widget retains the input value for workflow serialization.
- Generation-triggered autosave runs only when the builder's Python node executes. Cached/unexecuted runs do not update the history; use the manual save action.
- Autosave does not assign Photo IDs. Use manual save to preserve a combination. Two default saves within the same second update the same ID.
- The built-in node inputs are `STRING`, not `CONDITIONING`; use a compatible text encoder downstream.
- The JavaScript UI uses ComfyUI's classic LiteGraph `addWidget` integration. The backend works independently of the extra controls. Frontend behavior may vary in future / Nodes 2.0-only builds; test on the ComfyUI version in use.
- Use this node only on trusted ComfyUI instances: anyone with access to the ComfyUI HTTP API can read/change the shared history, like other local ComfyUI data.

## Tests

From the project parent directory: `python -m unittest discover -s comfyui-photo-prompt-builder/tests -v`.

## Preview without ComfyUI

Run `python3 -m http.server 8000` from this repository's root, then open `http://localhost:8000/preview/`. The preview loads the actual frontend JavaScript and mocks the ComfyUI node and history API in the browser. Preview history is stored in browser local storage.

This checks button placement and dialog interactions. It does not verify ComfyUI rendering, workflow serialization, or Python node execution.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
