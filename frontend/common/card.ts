import m from "mithril";

class CardView {
  view(
    vnode: m.Vnode<{
      cardType: "info" | "warning" | "error";
      footer?: string;
    }>,
  ) {
    const { cardType, footer } = vnode.attrs;
    return m(".kg-card", { class: cardType }, [
      m(".content", vnode.children),
      !!footer ? m(".footer", footer) : null,
    ]);
  }
}

export default CardView;
