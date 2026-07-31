# Template Replacement File Picker And Auto-Parse Design

## Problem

The replacement flow previously required two non-obvious actions: click
"更换模板", then select a file, then click "解析模板". Even after the picker fix,
returning from the native picker appeared to do nothing because parsing did not
start automatically.

## Design

- Clicking "更换模板" enters replacement state and opens the file picker after
  Vue has rendered the upload input.
- Before every picker open, clear the input value so selecting the same XML file
  again still emits a change event.
- Selecting or dropping a valid XML starts preview parsing immediately. While
  parsing, keep the selected filename visible and show an explicit busy state.
- If parsing fails, keep the selected file and expose "重新解析" plus the normal
  file chooser so the user can retry or choose a different XML.
- Keep "确认更换并进入映射" as the only mutating step. Automatic parsing never
  overwrites the current template.
- Returning from the native macOS file picker may trigger the route workspace
  focus refresh. While the mapping dialog is visible, keep the route workspace
  and dialog mounted so the selected file, preview, and confirmation action are
  not replaced by the route loading view.
- Keep the upload drop zone and drag-and-drop path as fallbacks.

## Verification

- Unit test that opening the picker clears the previous value before clicking.
- Unit test that accepting a valid XML invokes preview parsing immediately and
  that invalid extensions are rejected before parsing.
- Browser test with an approved Kmsoft XML: click "更换模板", select a file,
  and verify the replacement preview appears without an extra parse click or a
  commit.
- Regression test that route refresh loading still displays the mounted
  workspace while the template mapping dialog is visible, and displays normal
  loading progress when the dialog is closed.
