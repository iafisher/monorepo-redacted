import { FuzzySuggestModal, Notice, Plugin, sanitizeHTMLToDom } from "obsidian";
// @ts-ignore
import { exec } from "child_process";

interface CommandEntry {
  id: string;
  name: string;
  command: string;
}

class ShellCommandModal extends FuzzySuggestModal<CommandEntry> {
  plugin: ShellCommandPlugin;
  onTrigger: (choice: CommandEntry) => void;

  constructor(
    plugin: ShellCommandPlugin,
    onTrigger: (choice: CommandEntry) => void,
  ) {
    super(plugin.app);
    this.plugin = plugin;
    this.onTrigger = onTrigger;
  }

  getItems() {
    return this.plugin.commandsList;
  }

  getItemText(item: CommandEntry) {
    return item.name;
  }

  onChooseItem(item: CommandEntry) {
    this.onTrigger(item);
  }
}

export default class ShellCommandPlugin extends Plugin {
  commandsList: CommandEntry[] = [];

  async onload() {
    this.commandsList = (await this.loadData())?.commandsList || [];

    this.addCommand({
      id: "run-shell-command",
      name: "Run shell command",
      callback: async () => {
        this.selectCommand((choice) => {
          this.runCommand(choice.command);
        });
      },
    });

    this.addSettingTab(new ShellCommandSettingTab(this.app, this));
  }

  selectCommand(onTrigger: (choice: CommandEntry) => void): void {
    const modal = new ShellCommandModal(this, onTrigger);
    modal.open();
  }

  onunload() {
    this.save();
  }

  async runCommand(cmdTemplate: string) {
    // @ts-ignore
    const cwd = this.app.vault.adapter.basePath;
    const activeFile = this.app.workspace.getActiveFile();

    let cmd;
    const pat = /\[\[file\]\]/g;
    if (activeFile !== null) {
      cmd = cmdTemplate.replace(pat, activeFile.path);
    } else {
      if (pat.test(cmdTemplate)) {
        new Notice(
          sanitizeHTMLToDom(
            "<strong>Error:</strong> The command requires an active file, but no file is active.",
          ),
        );
        return;
      } else {
        cmd = cmdTemplate;
      }
    }

    // TODO(2025-07): common environment?
    const env = { KG_MACHINE: "laptop", PGHOST: "homeserver" };
    console.log("Running shell command:", { cmdTemplate, cmd, cwd, env });
    exec(cmd, { cwd, env }, (error: any, stdout: string, stderr: string) => {
      console.log("Shell command exited.", { error });
      console.log("Shell command stdout:", stdout);
      console.log("Shell command stderr:", stderr);
      if (error) {
        // Make Python backtraces scrollable.
        const style = `style="max-height: 500px; overflow: auto;`;
        const document = sanitizeHTMLToDom(
          `<strong>Error:</strong> The command failed with code ${error.code}.<br>Standard error:<br><pre ${style}><code>${stderr}</pre></code>`,
        );
        new Notice(document, 0);
      } else {
        new Notice("The command ran successfully.", 3000);
      }
    });
  }

  save(): void {
    this.saveData({ commandsList: this.commandsList });
  }
}

import { App, PluginSettingTab, Setting } from "obsidian";

class ShellCommandSettingTab extends PluginSettingTab {
  plugin: ShellCommandPlugin;

  constructor(app: App, plugin: ShellCommandPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;

    containerEl.empty();

    new Setting(containerEl)
      .setName("Shell Commands")
      .setDesc("Define shell commands to run from the palette.")
      .addButton((button) => {
        button.setButtonText("Add command").onClick(() => {
          this.plugin.commandsList.push({
            id: Date.now().toString(),
            name: "",
            command: "",
          });
          this.plugin.save();
          this.display();
        });
      });

    this.plugin.commandsList.forEach((cmd, index) => {
      new Setting(containerEl)
        .setName(`Command ${index + 1}`)
        .addText((text) =>
          text
            .setPlaceholder("Name")
            .setValue(cmd.name)
            .onChange((value) => {
              cmd.name = value;
              this.plugin.save();
            }),
        )
        .addText((text) =>
          text
            .setPlaceholder("Shell command")
            .setValue(cmd.command)
            .onChange((value) => {
              cmd.command = value;
              this.plugin.save();
            }),
        )
        .addExtraButton((btn) =>
          btn.setIcon("cross").onClick(() => {
            this.plugin.commandsList.splice(index, 1);
            this.plugin.save();
            this.display();
          }),
        );
    });
  }
}
