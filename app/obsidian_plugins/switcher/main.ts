import { App, Modal, Plugin, TFile } from "obsidian";

interface NoteItem {
  file: TFile;
  title: string;
  aliases: string[];
}

const RESULTS_DISPLAY_LIMIT = 20;

class SwitcherModal extends Modal {
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

      let aliases = cache?.frontmatter?.aliases ?? [];
      if (typeof aliases === "string") {
        aliases = [aliases];
      }

      this.notes.push({
        file,
        title,
        aliases,
      });
    }

    this.filterNotes("");
  }

  onOpen() {
    this.modalEl.style.alignSelf = "start";
    this.modalEl.style.marginTop = "10%";
    this.modalEl.style.width = "600px";

    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("switcher-modal");

    this.inputEl = contentEl.createEl("input", {
      type: "text",
      placeholder: "Find a note...",
    });
    this.inputEl.addClass("switcher-input");

    this.resultsEl = contentEl.createDiv();
    this.resultsEl.addClass("switcher-results");

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
      this.filteredNotes = [...this.notes].sort((a, b) => {
        return b.file.stat.mtime - a.file.stat.mtime;
      });
    } else {
      this.filteredNotes = this.notes.filter((note) => {
        return (
          note.file.basename.toLowerCase().includes(query) ||
          note.title.toLowerCase().includes(query) ||
          note.aliases.some((alias) => alias.toLowerCase().includes(query))
        );
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
        resultEl.addClass("switcher-result");

        if (index === this.selectedIndex) {
          scrollToMe = resultEl;
        }

        const nameEl = resultEl.createDiv();
        nameEl.addClass("switcher-result-title");
        nameEl.textContent = note.title;

        const titleEl = resultEl.createDiv();
        titleEl.addClass("switcher-result-name");
        titleEl.textContent = note.file.path;

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

export default class SwitcherPlugin extends Plugin {
  async onload() {
    this.addCommand({
      id: "open-switcher",
      name: "Open switcher",
      hotkeys: [{ modifiers: ["Mod"], key: "o" }],
      callback: () => {
        new SwitcherModal(this.app).open();
      },
    });
  }
}
