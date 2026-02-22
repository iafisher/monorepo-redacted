import m from "mithril";

import CardView from "./card";
import ModalController from "./modal";
import { formatTimestamp } from "./utils";

interface ErrorInfo {
  error: string;
  timestamp: Date;
}

class ErrorView {
  view(vnode: m.Vnode<{ errorInfo: ErrorInfo }>) {
    const { errorInfo } = vnode.attrs;
    return m(
      CardView,
      { cardType: "error", footer: formatTimestamp(errorInfo.timestamp) },
      vnode.attrs.errorInfo.error,
    );
  }
}

class Controller {
  public errors: ErrorInfo[];
  private modalController: ModalController;

  constructor() {
    this.errors = [];
    this.modalController = new ModalController();
  }

  pushError(error: string): void {
    console.error(`kg-controller: ${error}`);
    this.errors.push({ error, timestamp: new Date() });
    m.redraw();
  }

  showErrors(): void {
    this.modalController.show(
      m(
        ".kg-errors",
        this.errors.map((errorInfo: ErrorInfo) => m(ErrorView, { errorInfo })),
      ),
    );
  }
}

export default Controller;
