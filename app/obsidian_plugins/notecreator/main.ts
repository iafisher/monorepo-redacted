import { App, Modal, Notice, Plugin, TFile, sanitizeHTMLToDom } from "obsidian";
import { ExecOptions, exec } from "child_process";
import { basename } from "path";

export default class NewNotePlugin extends Plugin {
  async onload() {
    this.addCommand({
      id: "create-new-note-dialog",
      name: "Create new note",
      hotkeys: [{ modifiers: ["Mod", "Alt"], key: "N" }],
      callback: () => {
        new NewNoteModal(this.app).open();
      },
    });
  }
}

class NewNoteModal extends Modal {
  private cwd: string;

  constructor(app: App) {
    super(app);
    // @ts-ignore
    this.cwd = this.app.vault.adapter.basePath;
  }

  onOpen() {
    const { contentEl } = this;
    const gridEl = createInputGrid(contentEl);
    const titleInputEl = createInputElement(gridEl, "Markdown title", "");
    const filenameInputEl = createInputElement(
      gridEl,
      "Filename",
      "(optional)",
    );
    const previewEl = contentEl.createEl("div");

    let inputTimeoutId: any = null;
    const debounceMillis = 200;
    const onInput = async () => {
      if (!!inputTimeoutId) {
        clearTimeout(inputTimeoutId);
      }

      inputTimeoutId = setTimeout(async () => {
        await setPreviewElement(
          this.cwd,
          previewEl,
          titleInputEl.value,
          filenameInputEl.value,
        );
      }, debounceMillis);
    };

    const onKeydown = async (e: KeyboardEvent) => {
      if (e.key !== "Enter") {
        return;
      }

      e.preventDefault();
      const rawTitle = titleInputEl.value.trim();
      if (!rawTitle) {
        return;
      }
      await this.createNote(rawTitle, filenameInputEl.value.trim());
    };

    titleInputEl.addEventListener("input", onInput);
    filenameInputEl.addEventListener("input", onInput);
    titleInputEl.addEventListener("keydown", onKeydown);
    filenameInputEl.addEventListener("keydown", onKeydown);

    titleInputEl.focus();
  }

  async createNote(rawTitle: string, filenameOverride: string) {
    const cmd = makeCommand(this.cwd, rawTitle, filenameOverride, false);
    const options = { cwd: this.cwd };
    const { error, stdout, stderr } = await asyncCommand(cmd, options);
    if (error) {
      showCommandError(error, stderr);
    } else {
      const filePath = stdout.trim();
      this.pollForFile(filePath);
    }

    this.close();
  }

  pollForFile(filePath: string) {
    // Race condition: Plugin tries to open file before Obsidian registers that it was
    // created.
    //
    // Solution: Poll until Obsidian can successfully open the file.
    const startTimeMillis = Date.now();
    const intervalMillis = 100;
    const maxWaitTimeMillis = 3000;
    const app = this.app;
    (function loop() {
      // Awkward: `this` isn't bound correctly in this named function. But it has to be a real
      // function to be able to call itself by name recursively.
      setTimeout(() => {
        const file = app.vault.getAbstractFileByPath(filePath);
        if (file instanceof TFile) {
          // always open in new tab
          app.workspace.getLeaf("tab").openFile(file);
        } else {
          if (Date.now() - startTimeMillis >= maxWaitTimeMillis) {
            console.warn("Unable to open file after creation", {
              filePath,
              file,
            });
          } else {
            loop();
          }
        }
      }, intervalMillis);
    })();
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

function makeCommand(
  cwd: string,
  title: string,
  filenameOverride: string,
  preview: boolean,
): string {
  // TODO(2026-08): This should use the $KG_DIR environment variable. This is accessible as `process.env.KG_DIR`.
  // Problem: The environment in which Obsidian itself is run does not have KG_DIR defined.
  const exe = isTestVault(cwd)
    ? "/Users/iafisher/Code/monorepo/lcl obsidian"
    : "/Users/iafisher/.ian/repos/current/bin/obsidian";
  let cmd = `${exe} notes create -title "${title}" -vault "${cwd}"`;
  if (filenameOverride !== "") {
    cmd += ` -filename-override "${filenameOverride}"`;
  }
  if (preview) {
    cmd += " -preview";
  }
  return cmd;
}

function isTestVault(cwd: string): boolean {
  return basename(cwd) === "test-vault";
}

async function setPreviewElement(
  cwd: string,
  el: HTMLElement,
  title: string,
  filenameOverride: string,
): Promise<void> {
  title = title.trim();
  filenameOverride = filenameOverride.trim();

  if (!title && !filenameOverride) {
    el.innerHTML = "";
    return;
  }

  const cmd = makeCommand(cwd, title, filenameOverride, true);
  const { error, stdout, stderr } = await asyncCommand(cmd, { cwd });
  if (error) {
    showCommandError(error, stderr);
  } else {
    el.innerHTML = "";
    const pre = el.createEl("pre", { text: stdout });
    // Break lines so they don't overflow the modal box.
    pre.style.whiteSpace = "break";
  }
}

async function asyncCommand(
  cmd: string,
  options: ExecOptions,
): Promise<{ error: any; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    exec(cmd, options, (error: any, stdout: string, stderr: string) => {
      resolve({ error, stdout, stderr });
    });
  });
}

function showCommandError(error: any, stderr: string): void {
  console.error("The command failed with an error.", { error, stderr });
  const document = sanitizeHTMLToDom(
    `<strong>Error:</strong> The command failed with code ${error.code}.<br>Standard error:<br><pre><code>${stderr}</pre></code>`,
  );
  new Notice(document);
}

function createInputGrid(parent: HTMLElement): HTMLElement {
  const divEl = parent.createEl("div");
  divEl.style.display = "grid";
  divEl.style.gridTemplateColumns = "auto 1fr";
  divEl.style.columnGap = "12px";
  divEl.style.rowGap = "10px";
  // Give a little extra space from the modal 'X' button.
  divEl.style.marginTop = "7px";
  return divEl;
}

function createInputElement(
  gridParent: HTMLElement,
  label: string,
  placeholder: string,
): HTMLInputElement {
  const labelEl = gridParent.createEl("label");
  labelEl.textContent = label;
  labelEl.style.whiteSpace = "nowrap";
  labelEl.style.alignContent = "center";

  const inputEl = gridParent.createEl("input", { type: "text", placeholder });
  inputEl.style.height = "40px";
  inputEl.style.width = "100%";

  return inputEl;
}
