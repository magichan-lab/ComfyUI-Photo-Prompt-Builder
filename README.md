# Krea2 Photo Prompt Builder for ComfyUI

[日本語版 README](README.ja.md)

A single ComfyUI node that builds a labeled, nine-section photography prompt and keeps category-specific input history in a local JSON file.

## Installation

1. Extract the ZIP into `ComfyUI/custom_nodes/` so the folder is `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/`.
2. Restart the ComfyUI Python server, and refresh the browser (Ctrl+Shift+R if needed).
3. Search for **Krea2 Photo Prompt Builder** under `prompt/photo`.
4. Right-click the `text` widget of your `CLIPTextEncode` node and convert it to an input, if the text input port is not already available. Connect the builder's `prompt` output (STRING) to that input.

No pip dependencies beyond ComfyUI's own `aiohttp` are required.

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
- Click `History: <section> ▾` to open a selectable history dropdown, inspect the full text, apply a value, delete one value, or clear a section's history.
- Click `Save current values to history` to save immediately (even when `auto_save_history` is off).
- Click `Preview combined prompt` to inspect/copy the generated prompt without running the sampler.
- Duplicate values are removed, and the most recently saved entry appears first. Histories are independent for all nine categories.
- **History is shared by all builder nodes in the same ComfyUI installation.** Current values/toggles are also saved in each ComfyUI workflow.

## Storage and backup

The history lives at `ComfyUI/custom_nodes/comfyui-photo-prompt-builder/data/prompt_history.json`. It is human-readable UTF-8 and written using atomic replacement. Back this file up before reinstalling or upgrading the custom node.

**Google Colab**: Colab's ephemeral runtime deletes the local history when the runtime is reset. To retain it, back up or symlink the `data` directory to persistent Google Drive storage. This project does not automatically mount Drive.

## Notes and limitations

- A history menu is an in-node button that opens a dropdown dialog, rather than a separate always-visible combo widget. This avoids disrupting ComfyUI's serialization of built-in input widgets.
- Generation-triggered autosave runs only when the builder's Python node executes. Cached/unexecuted runs do not update the history; use the manual save action.
- The built-in node inputs are `STRING`, not `CONDITIONING`; use a compatible text encoder downstream.
- The JavaScript UI uses ComfyUI's classic LiteGraph `addWidget` integration. The backend works independently of the extra controls. Frontend behavior may vary in future / Nodes 2.0-only builds; test on the ComfyUI version in use.
- Use this node only on trusted ComfyUI instances: anyone with access to the ComfyUI HTTP API can read/change the shared history, like other local ComfyUI data.

## Tests

From the project parent directory: `python -m unittest discover -s comfyui-photo-prompt-builder/tests -v`.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
