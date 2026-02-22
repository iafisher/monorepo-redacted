import m from "mithril";

import "./common.scss";

class ModalView {
  private onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      this.onClose();
    }
  };

  private onClose: () => void = () => {};

  oncreate(vnode: m.VnodeDOM<{ onClose: () => void }>) {
    this.onClose = vnode.attrs.onClose;
    document.addEventListener("keydown", this.onKeyDown);
  }

  onremove() {
    document.removeEventListener("keydown", this.onKeyDown);
  }

  view(vnode: m.Vnode<{ onClose: () => void }>) {
    return [
      m(".kg-modal-backdrop", {
        onclick: () => vnode.attrs.onClose(),
      }),
      m(".kg-modal", vnode.children),
    ];
  }
}

class ModalController {
  public isShowing: boolean;
  private modalContainer: HTMLElement | null = null;

  constructor() {
    this.isShowing = false;
  }

  show(content: m.Children) {
    if (!this.modalContainer) {
      this.modalContainer = document.createElement("div");
      this.modalContainer.id = "kg-modal-container";
      document.body.appendChild(this.modalContainer);
    }

    m.mount(this.modalContainer, {
      view: () =>
        m(
          ModalView,
          {
            onClose: () => this.hide(),
          },
          content,
        ),
    });
    this.isShowing = true;
  }

  hide() {
    if (this.modalContainer) {
      m.mount(this.modalContainer, null);
      this.isShowing = false;
    }
  }
}

export default ModalController;
