import { syntaxTree } from "@codemirror/language";
import { RangeSetBuilder } from "@codemirror/state";
import {
  Decoration,
  DecorationSet,
  EditorView,
  PluginValue,
  ViewPlugin,
  ViewUpdate,
  WidgetType,
} from "@codemirror/view";
import { SyntaxNodeRef } from "@lezer/common";
import {
  MarkdownPostProcessorContext,
  MarkdownRenderChild,
  Plugin,
  editorLivePreviewField,
} from "obsidian";

interface MacroSlice {
  originalText: string;
  invocation: MacroInvocation;
  result: MacroResult;
  from: number;
  to: number;
}

class LivePreviewMacroPluginValue implements PluginValue {
  decorations: DecorationSet;
  private macroSlices: MacroSlice[];

  constructor(view: EditorView) {
    this.macroSlices = [];
    this.decorations = this.buildDecorations(view);
  }

  update(update: ViewUpdate): void {
    if (update.docChanged || update.viewportChanged || update.selectionSet) {
      this.decorations = this.buildDecorations(update.view);
    }
  }

  buildDecorations(view: EditorView): DecorationSet {
    if (!view.state.field(editorLivePreviewField)) {
      return Decoration.none;
    }

    const builder = new RangeSetBuilder<Decoration>();
    this.macroSlices = [];
    this.findMacros(view, this.macroSlices);
    this.processMacros(view, builder);
    return builder.finish();
  }

  findMacros(view: EditorView, macroSlices: MacroSlice[]): void {
    for (let { from, to } of view.visibleRanges) {
      syntaxTree(view.state).iterate({
        from,
        to,
        enter(node: SyntaxNodeRef) {
          if (node.name.startsWith("inline-code")) {
            const text = view.state.sliceDoc(node.from, node.to);
            const invocation = parseMacro(text);
            if (invocation !== null) {
              const result = evaluateMacro(invocation);
              if (!result) {
                return;
              }

              macroSlices.push({
                originalText: text,
                invocation,
                result,
                from: node.from,
                to: node.to,
              });
            }
          }
        },
      });
    }
  }

  processMacros(view: EditorView, builder: RangeSetBuilder<Decoration>): void {
    const cursorHead = view.state.selection.main.head;
    for (let macroSlice of this.macroSlices) {
      if (
        macroSlice.from - 1 <= cursorHead &&
        cursorHead <= macroSlice.to + 1
      ) {
        continue;
      }

      const widget = new MacroWidget(macroSlice);
      builder.add(
        macroSlice.from,
        macroSlice.to,
        Decoration.replace({ widget }),
      );
    }
  }
}

class MacroWidget extends WidgetType {
  private macroSlice: MacroSlice;

  constructor(macroSlice: MacroSlice) {
    super();
    this.macroSlice = macroSlice;
  }

  toDOM(view: EditorView): HTMLElement {
    const info = this.macroSlice.result.info;

    const el = document.createElement(this.macroSlice.result.tag);

    if (info.attr) {
      Object.entries(info.attr).forEach(([key, value]) => {
        // @ts-expect-error
        el.setAttribute(key, value);
      });
    }

    if (info.text) {
      // @ts-expect-error
      el.innerText = info.text;
    }

    return el;
  }
}

export const LivePreviewMacroPlugin = ViewPlugin.fromClass(
  LivePreviewMacroPluginValue,
  {
    decorations: (value: LivePreviewMacroPluginValue) => value.decorations,
  },
);
export interface MacroInvocation {
  name: string;
  args: string[];
}

export function parseMacro(text: string): MacroInvocation | null {
  if (!text.startsWith("{{") || !text.endsWith("}}")) {
    return null;
  }

  const body = text.slice(2, text.length - 2);
  const splitBody = body.split("|");
  return { name: splitBody[0], args: splitBody.slice(1) };
}

type MacroFunction = (args: string[]) => MacroResult | null;

export interface MacroResult {
  tag: keyof HTMLElementTagNameMap;
  info: DomElementInfo;
}

function macroPerson(args: string[]): MacroResult | null {
  let fullName, firstName;
  if (args.length === 1) {
    fullName = args[0];
    firstName = fullName.split(" ")[0];
  } else if (args.length === 2) {
    fullName = args[0];
    firstName = args[1];
  } else {
    warn("person", `expected 1 or 2 args, got ${args.length}`);
    return null;
  }

  return {
    tag: "abbr",
    info: {
      attr: {
        class: "person",
        title: fullName,
      },
      text: firstName,
    },
  };
}

function warn(macroName: string, message: string): void {
  console.warn(`MyMacrosPlugin: ${macroName}: ${message}`);
}

const KNOWN_MACROS = new Map();
KNOWN_MACROS.set("person", macroPerson);

function lookupMacro(name: string): MacroFunction | null {
  return KNOWN_MACROS.get(name);
}

export function evaluateMacro(invocation: MacroInvocation): MacroResult | null {
  const name = invocation.name;
  const macroFunction = lookupMacro(name);
  if (!macroFunction) {
    console.warn(
      `MyMacrosPlugin: saw macro invocation ${name} but did not find macro implementation`,
    );
    return null;
  }

  return macroFunction(invocation.args);
}

export default class MyMacrosPlugin extends Plugin {
  async onload() {
    this.registerEditorExtension(LivePreviewMacroPlugin);
    this.registerMarkdownPostProcessor(markdownPostProcessor);
  }
}

export function markdownPostProcessor(
  element: HTMLElement,
  context: MarkdownPostProcessorContext,
): void {
  const codeElements = element.querySelectorAll("code");
  for (let codeElement of codeElements) {
    const text = codeElement.textContent;
    if (!text) {
      continue;
    }

    const macroInvocation = parseMacro(text);
    if (!macroInvocation) {
      continue;
    }

    const macroResult = evaluateMacro(macroInvocation);
    if (!macroResult) {
      continue;
    }

    context.addChild(new MacroRenderChild(codeElement, macroResult));
  }
}

class MacroRenderChild extends MarkdownRenderChild {
  private result: MacroResult;

  constructor(containerEl: HTMLElement, result: MacroResult) {
    super(containerEl);
    this.result = result;
  }

  onload() {
    const element = this.containerEl.createEl(
      this.result.tag,
      this.result.info,
    );
    this.containerEl.replaceWith(element);
  }
}
