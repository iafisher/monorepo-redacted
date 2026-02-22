import feather from "feather-icons";
import m from "mithril";

import "./common.scss";
import Controller from "./controller";

interface Link {
  text: string;
  href: string;
}

class AlertIconView {
  view(vnode: m.Vnode<{ onClick: () => void; count: number }>) {
    return m(".alert", { onclick: () => vnode.attrs.onClick() }, [
      m.trust(
        feather.icons["alert-circle"].toSvg({ width: "18px", height: "18px" }),
      ),
      m("span", "" + vnode.attrs.count),
    ]);
  }
}

class HeaderView {
  view(
    vnode: m.Vnode<{
      controller: Controller;
      title: string;
      links: (Link | null)[];
    }>,
  ) {
    const { controller, title, links } = vnode.attrs;
    const errorCount = controller.errors.length;
    return m(".kg-header", [
      m(
        ".left",
        links.map((link) =>
          !!link ? m("a.link", { href: link.href }, link.text) : null,
        ),
      ),
      m(".title", title),
      m(
        ".right",
        errorCount > 0
          ? m(AlertIconView, {
              onClick: () => {
                controller.showErrors();
              },
              count: errorCount,
            })
          : null,
      ),
    ]);
  }
}

export default HeaderView;
