import { App, Modal, Notice, Plugin, TFile, sanitizeHTMLToDom } from "obsidian";
// @ts-ignore
import { exec } from "child_process";

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
  constructor(app: App) {
    super(app);
  }

  titleToFilename(title: string): string {
    // Keep this in sync with `app/obsidian/notes.py`
    title = title.trim();
    if (title === "") {
      return title;
    }

    const now = new Date();
    const year = now.getFullYear();
    const month = ("" + (now.getMonth() + 1)).padStart(2, "0");
    return (
      `${year}-${month}-` +
      title
        .toLowerCase()
        .replace(/\.md$/, "")
        .replace(/[^A-Za-z0-9: -]/g, "")
        .replace(/:\s*/g, "-")
        .replace(/\s*-\s*/g, "-")
        .replace(/\s+/g, "-")
    );
  }

  onOpen() {
    const { contentEl } = this;
    const inputEl = contentEl.createEl("input", {
      type: "text",
      placeholder: "Enter note title...",
    });
    inputEl.style.width = "100%";
    inputEl.style.height = "40px";
    inputEl.style.marginTop = "7px";
    inputEl.style.fontSize = "1.5em";

    const previewEl = contentEl.createEl("div", {
      text: "",
    });
    previewEl.style.width = "100%";
    previewEl.style.marginTop = "10px";
    previewEl.style.padding = "10px";
    previewEl.style.fontSize = "1em";
    previewEl.style.minHeight = "20px";

    inputEl.focus();

    inputEl.addEventListener("input", (e: Event) => {
      const target = e.target as HTMLInputElement;
      const preview = this.titleToFilename(target.value);
      previewEl.textContent = preview;
    });

    inputEl.addEventListener("keydown", async (e: KeyboardEvent) => {
      if (e.key !== "Enter") {
        return;
      }

      e.preventDefault();
      const rawTitle = inputEl.value.trim();
      if (!rawTitle) {
        return;
      }
      await this.createNote(rawTitle);
    });
  }

  async createNote(rawTitle: string) {
    // @ts-ignore
    const cwd = this.app.vault.adapter.basePath;
    const cmd = `/Users/iafisher/.ian/repos/current/bin/obsidian notes create "${rawTitle}"`;
    exec(cmd, { cwd }, (error: any, stdout: string, stderr: string) => {
      console.log("Shell command exited.", { error });
      console.log("Shell command stdout:", stdout);
      console.log("Shell command stderr:", stderr);
      if (error) {
        const document = sanitizeHTMLToDom(
          `<strong>Error:</strong> The command failed with code ${error.code}.<br>Standard error:<br><pre><code>${stderr}</pre></code>`,
        );
        new Notice(document);
      } else {
        // Race condition: Plugin tries to open file before Obsidian registers that it was
        // created.
        //
        // Empirically, waiting 300ms solves the problem.
        const timeoutMillis = 300;
        setTimeout(() => {
          const filePath = stdout.trim();
          const file = this.app.vault.getAbstractFileByPath(filePath);
          if (file instanceof TFile) {
            // always open in new tab
            this.app.workspace.getLeaf("tab").openFile(file);
          } else {
            console.warn("Unable to open file after creation", {
              filePath,
              file,
            });
          }
        }, timeoutMillis);
      }

      this.close();
    });
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}
