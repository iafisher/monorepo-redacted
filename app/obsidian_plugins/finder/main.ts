import { App, Modal, Notice, Plugin, TFile, sanitizeHTMLToDom } from "obsidian";
// @ts-ignore
import { spawn, spawnSync } from "child_process";
import * as path from "path";

interface SnippetMatch {
  text: string;
  start: number;
  end: number;
}

interface NoteItem {
  file: TFile;
  title: string;
  displayName: string;
  matches?: SnippetMatch[];
}

const RESULTS_DISPLAY_LIMIT = 20;

class FinderModal extends Modal {
  private inputEl: HTMLInputElement;
  private resultsEl: HTMLElement;
  private notes: NoteItem[] = [];
  private filteredNotes: NoteItem[] = [];
  private selectedIndex = 0;

  constructor(app: App) {
    super(app);
    this.loadNotes();
  }

  async loadNotes() {
    this.notes = [];
    const files = this.app.vault.getMarkdownFiles();

    for (const file of files) {
      const cache = this.app.metadataCache.getFileCache(file);
      const title =
        cache?.frontmatter?.title ||
        cache?.headings?.find((h) => h.level === 1)?.heading ||
        file.basename;

      this.notes.push({
        file,
        title,
        displayName: `${file.basename} - ${title}`,
      });
    }

    this.filterNotes("");
  }

  onOpen() {
    this.modalEl.style.alignSelf = "start";
    this.modalEl.style.marginTop = "10%";
    this.modalEl.style.width = "800px";

    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("finder-modal");

    this.inputEl = contentEl.createEl("input", {
      type: "text",
      placeholder: "Search all notes...",
    });
    this.inputEl.addClass("finder-input");

    this.resultsEl = contentEl.createDiv();
    this.resultsEl.addClass("finder-results");

    this.inputEl.focus();
    this.renderResults();

    this.inputEl.addEventListener("input", () => {
      const query = this.inputEl.value.toLowerCase().trim();
      this.filterNotes(query);
      this.selectedIndex = 0;
      this.renderResults();
    });

    this.inputEl.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        this.selectNext();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this.selectPrevious();
      } else if (e.key === "Enter") {
        e.preventDefault();
        this.openSelectedNote();
      } else if (e.key === "Escape") {
        this.close();
      }
    });
  }

  filterNotes(query: string) {
    if (!query) {
      this.filteredNotes = [];
    } else {
      // Absolute path to the vault on disk (desktop app only)
      const vaultPath =
        (this.app.vault.adapter as any).basePath ??
        (this.app.vault.adapter as any).getBasePath?.() ??
        ".";

      let rg;
      try {
        rg = spawnSync("rg", ["--json", "--ignore-case", query, vaultPath], {
          encoding: "utf-8",
        });
      } catch (err) {
        new Notice(
          sanitizeHTMLToDom(`<strong>Error:</strong> rg failed: ${err}`),
        );
        this.filteredNotes = [];
        return;
      }

      if (rg.status !== 0 || !rg.stdout) {
        this.filteredNotes = [];
        return;
      }

      const snippetMap = new Map<string, SnippetMatch[]>();
      rg.stdout.split(/\r?\n/).forEach((line) => {
        if (!line) return;
        try {
          const obj = JSON.parse(line);
          if (obj.type === "match") {
            const filePath = obj.data.path.text;
            const relPath = path.relative(vaultPath, filePath);
            const snippet = obj.data.lines.text as string;
            const snippetMatch = {
              text: snippet,
              start: obj.data.submatches[0].start,
              end: obj.data.submatches[0].end,
            };
            const r = snippetMap.get(relPath);
            if (r === undefined) {
              snippetMap.set(relPath, [snippetMatch]);
            } else {
              r.push(snippetMatch);
            }
          }
        } catch {
          // Ignore malformed JSON lines (shouldn't happen)
        }
      });

      this.filteredNotes = this.notes
        .filter((n) => snippetMap.has(n.file.path))
        .map((n) => {
          const matches = snippetMap.get(n.file.path);
          return { ...n, matches };
        });
    }
  }

  renderResults() {
    this.resultsEl.empty();

    let scrollToMe: HTMLElement | null = null;
    this.filteredNotes
      .slice(0, RESULTS_DISPLAY_LIMIT)
      .forEach((note, index) => {
        const resultEl = this.resultsEl.createDiv();
        resultEl.addClass("finder-result");

        if (index === this.selectedIndex) {
          scrollToMe = resultEl;
        }

        const nameEl = resultEl.createDiv();
        nameEl.addClass("finder-result-title");
        nameEl.textContent = note.title;

        const titleEl = resultEl.createDiv();
        titleEl.addClass("finder-result-name");
        titleEl.textContent = note.file.path;

        for (const match of note.matches ?? []) {
          const snippetEl = resultEl.createDiv();
          snippetEl.addClass("finder-result-snippet");
          const beforeEl = snippetEl.createEl("span");
          let snippetStart = 0;
          if (match.start > 40) {
            snippetStart = match.start - 40;
            beforeEl.addClass("truncated");
          }
          // `rg` returns offsets in terms of bytes rather than characters.
          beforeEl.textContent = sliceByteOffsets(
            match.text,
            snippetStart,
            match.start,
          );
          const matchEl = snippetEl.createEl("span");
          matchEl.addClass("match");
          matchEl.textContent = sliceByteOffsets(
            match.text,
            match.start,
            match.end,
          );
          const afterEl = snippetEl.createEl("span");
          afterEl.textContent = sliceByteOffsets(match.text, match.end);
        }

        resultEl.addEventListener("click", () => {
          this.selectedIndex = index;
          this.openSelectedNote();
        });
      });

    // NOTE: This must come *after* we've fully rendered the content -- don't
    // put it in the `forEach` loop!
    if (scrollToMe !== null) {
      // TODO(2025-07): The type cast here shouldn't be necessary...
      (scrollToMe as HTMLElement).addClass("selected");
      this.scrollToSelected(scrollToMe);
    }
  }

  scrollToSelected(selectedEl: HTMLElement) {
    const container = this.resultsEl;
    const containerRect = container.getBoundingClientRect();
    const elementRect = selectedEl.getBoundingClientRect();

    const elementTop =
      elementRect.top - containerRect.top + container.scrollTop;
    const elementBottom = elementTop + selectedEl.offsetHeight;
    const containerTop = container.scrollTop;
    const containerBottom = containerTop + container.clientHeight;

    if (elementTop < containerTop) {
      container.scrollTop = elementTop;
    } else if (elementBottom > containerBottom) {
      container.scrollTop = elementBottom - container.clientHeight;
    }
  }

  selectNext() {
    const maxIndex = Math.min(
      this.filteredNotes.length - 1,
      RESULTS_DISPLAY_LIMIT - 1,
    );
    if (this.selectedIndex < maxIndex) {
      this.selectedIndex++;
      this.renderResults();
    }
  }

  selectPrevious() {
    if (this.selectedIndex > 0) {
      this.selectedIndex--;
      this.renderResults();
    }
  }

  openSelectedNote() {
    if (
      this.filteredNotes.length > 0 &&
      this.selectedIndex < this.filteredNotes.length
    ) {
      const note = this.filteredNotes[this.selectedIndex];
      // always open in new tab
      this.app.workspace.getLeaf("tab").openFile(note.file);
      this.close();
    }
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }
}

function sliceByteOffsets(s: string, start: number, end?: number): string {
  return new TextDecoder().decode(
    new TextEncoder().encode(s).subarray(start, end),
  );
}

export default class FinderPlugin extends Plugin {
  async onload() {
    this.addCommand({
      id: "open-finder",
      name: "Open finder",
      hotkeys: [{ modifiers: ["Mod", "Shift"], key: "f" }],
      callback: () => {
        new FinderModal(this.app).open();
      },
    });
  }
}
